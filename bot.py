import os
import logging
from datetime import datetime, timedelta, time as dt_time
import pytz
import sys
import threading
import json
import requests
import http.server
import socketserver
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from sqlalchemy import text

from database import User, Schedule, get_session, init_schedule, DB_READY, add_manager, get_manager_by_telegram_id, get_all_managers, add_feedback_request, check_and_schedule_feedback_requests, check_database_connection, safe_execute_query
from utils import parse_date, format_date, get_current_moscow_time, get_weekday

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Изменено на DEBUG для более подробных логов
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
logger.info("Переменные окружения загружены")

# Константы для разговорного интерфейса
CHOOSING_GROUP, ENTERING_START_DATE = range(2)

# Токен бота и ID чата менеджера из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
MANAGER_CHAT_ID = os.getenv('MANAGER_CHAT_ID')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///feedback_bot.db')

if not TELEGRAM_TOKEN:
    logger.error("Токен Telegram не найден в переменных окружения!")
    sys.exit(1)

logger.info(f"Используется токен: {TELEGRAM_TOKEN[:5]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"ID менеджера: {MANAGER_CHAT_ID}")
logger.info(f"URL базы данных: {DATABASE_URL.split('://')[0]}://**********")

# Инициализация глобального планировщика
scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Moscow'))

# Получаем переменные окружения для вебхука (для Render)
PORT = int(os.environ.get('PORT', 10000))
# На Render мы можем использовать только один порт, указанный в переменной PORT
# Поэтому отдельный сервер проверки доступности не будет работать
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')

logger.info(f"PORT: {PORT}")
logger.info(f"WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"RENDER_EXTERNAL_URL: {RENDER_EXTERNAL_URL}")
logger.info(f"RENDER_EXTERNAL_HOSTNAME: {RENDER_EXTERNAL_HOSTNAME}")

# Создаем WEBHOOK_URL из RENDER_EXTERNAL_URL, если он определен и WEBHOOK_URL не задан
if RENDER_EXTERNAL_URL and not WEBHOOK_URL:
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/bot{TELEGRAM_TOKEN}"
elif RENDER_EXTERNAL_HOSTNAME and not WEBHOOK_URL:
    WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}/bot{TELEGRAM_TOKEN}"

# Проверяем, работаем ли в режиме вебхука или локально
USE_WEBHOOK = bool(WEBHOOK_URL)
logger.info(f"Режим вебхука: {'Включен' if USE_WEBHOOK else 'Отключен'}")
if USE_WEBHOOK:
    logger.info(f"Используемый URL вебхука: {WEBHOOK_URL}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start, предназначенный для регистрации нового пользователя."""
    try:
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        logger.info(f"[ДИАГНОСТИКА] Обработка команды /start от пользователя @{user.username or 'без имени'} (ID: {user.id})")
        
        # Проверяем соединение с базой данных перед выполнением операций
        if not check_database_connection():
            logger.error("[ДИАГНОСТИКА] База данных недоступна, возвращаем базовое приветствие")
            await update.message.reply_text(
                f"Здравствуйте, {user.first_name}! В настоящее время сервис недоступен из-за проблем с базой данных. "
                "Пожалуйста, попробуйте позже."
            )
            return ConversationHandler.END
        
        # Получаем сессию в безопасном режиме
        try:
            logger.info(f"[ДИАГНОСТИКА] Получение сессии базы данных для пользователя {chat_id}")
            session = get_session()
        except Exception as session_error:
            logger.error(f"[ДИАГНОСТИКА] Критическая ошибка при создании сессии базы данных: {session_error}")
            await update.message.reply_text(
                f"Здравствуйте, {user.first_name}! К сожалению, произошла ошибка при соединении с базой данных. "
                "Пожалуйста, попробуйте позже."
            )
            return ConversationHandler.END
        
        # Проверяем, есть ли пользователь уже в базе данных
        try:
            # Используем безопасное выполнение запроса
            def check_user_exists(s):
                try:
                    # Проверяем наличие функции text в текущем контексте
                    if 'text' not in globals() and 'text' not in locals():
                        logger.info("[ДИАГНОСТИКА] Импортируем text из SQLAlchemy (отсутствует в текущем контексте)")
                        from sqlalchemy import text as sql_text
                        query = sql_text("SELECT id, is_active FROM users WHERE chat_id = :chat_id")
                    else:
                        # Используем text() для защиты от SQL инъекций и соответствия требованиям SQLAlchemy 2.0
                        logger.info("[ДИАГНОСТИКА] Используем существующий импорт text")
                        query = text("SELECT id, is_active FROM users WHERE chat_id = :chat_id")
                    
                    logger.info(f"[ДИАГНОСТИКА] Выполняем запрос: {query} с параметрами chat_id={chat_id}")
                    result = s.execute(query, {"chat_id": chat_id}).fetchone()
                    logger.info(f"[ДИАГНОСТИКА] Результат запроса: {result}")
                    return result
                except NameError as e:
                    # Обрабатываем ошибку отсутствия функции text
                    logger.error(f"[ДИАГНОСТИКА] Ошибка импорта 'text': {e}")
                    logger.error(f"[ДИАГНОСТИКА] Пытаемся импортировать text явно")
                    from sqlalchemy import text as sql_text
                    query = sql_text("SELECT id, is_active FROM users WHERE chat_id = :chat_id")
                    result = s.execute(query, {"chat_id": chat_id}).fetchone()
                    return result
                except Exception as e:
                    logger.error(f"[ДИАГНОСТИКА] Ошибка при проверке пользователя: {e}")
                    import traceback
                    logger.error(f"[ДИАГНОСТИКА] Трассировка ошибки: {traceback.format_exc()}")
                    # Проверяем доступность таблицы users
                    try:
                        # Определяем тип базы данных
                        if DATABASE_URL and 'sqlite' in DATABASE_URL.lower():
                            # SQLite
                            tables_query = text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                        else:
                            # PostgreSQL
                            tables_query = text("SELECT table_name FROM information_schema.tables WHERE table_name='users'")
                        
                        tables = s.execute(tables_query).fetchall()
                        logger.info(f"[ДИАГНОСТИКА] Доступные таблицы: {tables}")
                        
                        # Проверка структуры таблицы users
                        try:
                            if tables:
                                if DATABASE_URL and 'sqlite' in DATABASE_URL.lower():
                                    # SQLite
                                    structure_query = text("PRAGMA table_info(users)")
                                else:
                                    # PostgreSQL
                                    structure_query = text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='users'")
                                
                                columns = s.execute(structure_query).fetchall()
                                logger.info(f"[ДИАГНОСТИКА] Структура таблицы users: {columns}")
                        except Exception as struct_error:
                            logger.error(f"[ДИАГНОСТИКА] Ошибка при проверке структуры таблицы: {struct_error}")
                    except Exception as table_error:
                        logger.error(f"[ДИАГНОСТИКА] Ошибка при проверке таблиц: {table_error}")
                    return None
            
            existing_user = safe_execute_query(session, check_user_exists)
            
            # Если запрос вернул None из-за ошибки
            if existing_user is None and session.is_active:
                logger.error(f"[ДИАГНОСТИКА] Ошибка при проверке существования пользователя")
                await update.message.reply_text(
                    f"Здравствуйте, {user.first_name}! Произошла ошибка при проверке вашей регистрации. "
                    "Пожалуйста, попробуйте позже."
                )
                session.close()
                return ConversationHandler.END
            
            logger.info(f"[ДИАГНОСТИКА] Результат проверки существования пользователя: {existing_user}")
        except Exception as query_error:
            logger.error(f"[ДИАГНОСТИКА] Ошибка при выполнении запроса проверки пользователя: {query_error}")
            
            try:
                await update.message.reply_text(
                    f"Здравствуйте, {user.first_name}! Произошла ошибка при проверке вашей регистрации. "
                    "Пожалуйста, попробуйте позже."
                )
            except Exception as reply_error:
                logger.error(f"[ДИАГНОСТИКА] Не удалось отправить сообщение пользователю: {reply_error}")
            
            try:
                session.close()
            except:
                pass
                
            return ConversationHandler.END
        
        # Пользователь уже существует
        if existing_user:
            logger.info(f"[ДИАГНОСТИКА] Пользователь {chat_id} уже существует в базе данных, обновление статуса")
            
            # Если пользователь был неактивен, обновляем его статус
            if not existing_user[1]:  # is_active = False
                try:
                    # Используем безопасное выполнение запроса для обновления
                    def update_user_status(s):
                        try:
                            # Проверяем наличие функции text в текущем контексте
                            if 'text' not in globals() and 'text' not in locals():
                                from sqlalchemy import text as sql_text
                                query = sql_text("UPDATE users SET is_active = :is_active WHERE chat_id = :chat_id")
                            else:
                                query = text("UPDATE users SET is_active = :is_active WHERE chat_id = :chat_id")
                                
                            s.execute(query, {"is_active": True, "chat_id": chat_id})
                            s.commit()
                        except NameError as e:
                            # Обрабатываем ошибку отсутствия функции text
                            logger.error(f"[ДИАГНОСТИКА] Ошибка импорта 'text': {e}")
                            from sqlalchemy import text as sql_text
                            query = sql_text("UPDATE users SET is_active = :is_active WHERE chat_id = :chat_id")
                            s.execute(query, {"is_active": True, "chat_id": chat_id})
                            s.commit()
                        except Exception as e:
                            logger.error(f"[ДИАГНОСТИКА] Ошибка при обновлении статуса пользователя: {e}")
                            s.rollback()
                            raise
                    
                    safe_execute_query(session, update_user_status)
                    logger.info(f"[ДИАГНОСТИКА] Статус пользователя обновлен в базе данных")
                except Exception as db_error:
                    logger.error(f"[ДИАГНОСТИКА] Ошибка при обновлении статуса пользователя: {db_error}")
                    try:
                        session.rollback()
                    except:
                        pass
            
            # Отправляем сообщение уже существующему пользователю
            try:
                await update.message.reply_text(
                    f"С возвращением, {user.first_name}! Вы уже зарегистрированы в системе. "
                    "Используйте /help для получения информации о доступных командах."
                )
                logger.info(f"[ДИАГНОСТИКА] Отправлено приветственное сообщение существующему пользователю {chat_id}")
            except Exception as e:
                logger.error(f"[ДИАГНОСТИКА] Ошибка при отправке сообщения существующему пользователю: {e}")
            
            try:
                session.close()
                logger.info(f"[ДИАГНОСТИКА] Сессия базы данных закрыта")
            except:
                pass
                
            return ConversationHandler.END
        
        # Создаем нового пользователя, используя безопасное выполнение запроса
        logger.info(f"[ДИАГНОСТИКА] Создание нового пользователя с chat_id={chat_id}")
        try:
            def create_new_user(s):
                try:
                    # В этой функции мы используем ORM модель User, поэтому text() не требуется
                    new_user = User(
                        chat_id=chat_id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name
                    )
                    s.add(new_user)
                    s.commit()
                    return True
                except Exception as e:
                    logger.error(f"[ДИАГНОСТИКА] Ошибка при создании нового пользователя: {e}")
                    try:
                        s.rollback()
                    except:
                        pass
                    return False
            
            user_created = safe_execute_query(session, create_new_user)
            
            if not user_created:
                logger.error(f"[ДИАГНОСТИКА] Не удалось создать пользователя")
                await update.message.reply_text(
                    "Произошла ошибка при регистрации. Пожалуйста, попробуйте позже."
                )
                try:
                    session.close()
                except:
                    pass
                return ConversationHandler.END
                
            logger.info(f"[ДИАГНОСТИКА] Новый пользователь успешно добавлен в базу данных")
        except Exception as db_error:
            logger.error(f"[ДИАГНОСТИКА] Ошибка при создании нового пользователя: {db_error}")
            try:
                session.rollback()
            except:
                pass
                
            try:
                await update.message.reply_text(
                    "Произошла ошибка при регистрации. Пожалуйста, попробуйте позже."
                )
            except Exception:
                pass
                
            try:
                session.close()
            except:
                pass
                
            return ConversationHandler.END
        
        try:
            session.close()
            logger.info(f"[ДИАГНОСТИКА] Сессия базы данных закрыта после создания пользователя")
        except Exception as close_error:
            logger.error(f"[ДИАГНОСТИКА] Ошибка при закрытии сессии: {close_error}")
        
        # Отправляем приветствие и кнопки выбора группы
        logger.info(f"[ДИАГНОСТИКА] Отправка приветствия и кнопок выбора группы пользователю {chat_id}")
        try:
            await update.message.reply_text(
                f"Здравствуйте, {user.first_name}! Добро пожаловать в бот обратной связи компании.\n\n"
                "Пожалуйста, выберите вашу группу занятий:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Группа будни", callback_data="group_weekday")],
                    [InlineKeyboardButton("Группа выходного дня", callback_data="group_weekend")]
                ])
            )
            logger.info(f"[ДИАГНОСТИКА] Приветствие с кнопками успешно отправлено")
        except Exception as msg_error:
            logger.error(f"[ДИАГНОСТИКА] Ошибка при отправке приветствия: {msg_error}")
            try:
                await update.message.reply_text(
                    "Произошла ошибка при отправке кнопок. Пожалуйста, попробуйте команду /start снова."
                )
            except Exception:
                pass
            return ConversationHandler.END
        
        return CHOOSING_GROUP
    except Exception as e:
        logger.error(f"[ДИАГНОСТИКА] Необработанная ошибка в обработчике start: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Попытка отправить сообщение пользователю даже при ошибке
        try:
            await update.message.reply_text(
                "Произошла ошибка при обработке команды. Пожалуйста, попробуйте позже или свяжитесь с администратором."
            )
        except Exception as msg_error:
            logger.error(f"[ДИАГНОСТИКА] Невозможно отправить сообщение об ошибке: {msg_error}")
        
        return ConversationHandler.END


async def group_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора группы."""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    chat_id = update.effective_chat.id
    
    # Сохраняем выбор в контексте
    if choice == "group_weekday":
        group_type = "weekday"
        group_name = "Группа будни"
    else:
        group_type = "weekend"
        group_name = "Группа выходного дня"
    
    context.user_data["group_type"] = group_type
    
    # Обновляем информацию о пользователе в базе
    session = get_session()
    user = session.query(User).filter(User.chat_id == chat_id).first()
    if user:
        user.group_type = group_type
        session.commit()
    session.close()
    
    # Запрашиваем дату начала занятий
    await query.edit_message_text(
        f"Вы выбрали: {group_name}\n\n"
        "Пожалуйста, введите дату начала занятий в формате ДД.ММ.ГГГГ (например, 01.09.2023):"
    )
    
    return ENTERING_START_DATE


async def start_date_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик ввода даты начала занятий."""
    date_text = update.message.text
    start_date = parse_date(date_text)
    
    if not start_date:
        await update.message.reply_text(
            "Пожалуйста, введите дату в правильном формате (ДД.ММ.ГГГГ):"
        )
        return ENTERING_START_DATE
    
    # Сохраняем дату начала в базе
    chat_id = update.effective_chat.id
    session = get_session()
    user = session.query(User).filter(User.chat_id == chat_id).first()
    
    if user:
        user.start_date = start_date
        session.commit()
    session.close()
    
    group_type = context.user_data.get("group_type", "weekday")
    group_name = "Группа будни" if group_type == "weekday" else "Группа выходного дня"
    
    await update.message.reply_text(
        f"Спасибо! Вы успешно зарегистрированы.\n\n"
        f"Группа: {group_name}\n"
        f"Дата начала занятий: {format_date(start_date)}\n\n"
        "После окончания каждого занятия вы будете получать запрос на обратную связь. "
        "Ваши отзывы помогут нам улучшить качество занятий."
    )
    
    return ConversationHandler.END


async def feedback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик получения сообщения с обратной связью."""
    try:
        message = update.message.text
        user = update.effective_user
        
        logger.info(f"Получена обратная связь от пользователя {user.id}: {message[:50]}...")
        
        # Отправляем благодарность пользователю
        await update.message.reply_text(
            "Спасибо за вашу обратную связь! Ваше мнение очень важно для нас."
        )
        
        # Отправляем сообщение менеджеру
        if MANAGER_CHAT_ID:
            try:
                manager_message = (
                    f"Новая обратная связь от пользователя:\n"
                    f"Имя: {user.first_name} {user.last_name or ''}\n"
                    f"Username: @{user.username or 'нет'}\n"
                    f"ID: {user.id}\n\n"
                    f"Сообщение:\n{message}"
                )
                await context.bot.send_message(
                    chat_id=MANAGER_CHAT_ID,
                    text=manager_message
                )
                logger.info(f"Обратная связь от пользователя {user.id} отправлена менеджеру")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения менеджеру: {e}")
    except Exception as e:
        logger.error(f"Ошибка при обработке обратной связи: {e}")
        try:
            await update.message.reply_text(
                "Произошла ошибка при обработке вашего сообщения. Пожалуйста, попробуйте позже."
            )
        except Exception:
            pass


async def send_feedback_request(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет запрос на обратную связь пользователю после занятия."""
    job = context.job
    chat_id = job.data
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="Занятие завершилось! Пожалуйста, поделитесь вашими впечатлениями и обратной связью о сегодняшнем занятии. Это поможет нам стать лучше!"
    )


def check_and_schedule_feedback_requests():
    """Проверяет расписание и назначает отправку запросов на обратную связь."""
    session = get_session()
    current_time = get_current_moscow_time()
    weekday = get_weekday()
    
    # Получаем все расписания на текущий день недели
    schedules = session.query(Schedule).filter(Schedule.day_of_week == weekday).all()
    
    for schedule in schedules:
        # Получаем пользователей соответствующей группы
        users = session.query(User).filter(
            User.group_type == schedule.group_type,
            User.is_active == True,
            User.start_date <= current_time
        ).all()
        
        for user in users:
            # Время окончания занятия сегодня
            class_end_time = datetime.combine(
                current_time.date(),
                schedule.end_time,
                tzinfo=current_time.tzinfo
            )
            
            # Если время окончания занятия уже прошло, не отправляем уведомление
            if current_time > class_end_time:
                continue
            
            # Планируем отправку запроса на обратную связь
            job_name = f"feedback_request_{user.chat_id}_{current_time.date()}"
            
            # Проверяем, не запланирована ли уже эта задача
            if job_name not in [job.id for job in scheduler.get_jobs()]:
                scheduler.add_job(
                    send_feedback_request_to_user,
                    'date',
                    run_date=class_end_time,
                    args=[user.chat_id],
                    id=job_name
                )
                logger.info(f"Запланирован запрос обратной связи для пользователя {user.chat_id} в {class_end_time}")
    
    session.close()


async def send_feedback_request_to_user(chat_id):
    """Функция для отправки запроса на обратную связь конкретному пользователю."""
    try:
        bot = Application.get_current().bot
        
        await bot.send_message(
            chat_id=chat_id,
            text="Занятие завершилось! Пожалуйста, поделитесь вашими впечатлениями и обратной связью о сегодняшнем занятии. Это поможет нам стать лучше!"
        )
        logger.info(f"Отправлен запрос обратной связи пользователю {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке запроса обратной связи: {e}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет регистрацию и завершает разговор."""
    await update.message.reply_text(
        "Регистрация отменена. Чтобы начать снова, используйте команду /start."
    )
    return ConversationHandler.END


async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для проверки доступности бота через URL."""
    logger.info(f"Получен запрос на проверку доступности от {update.effective_user.id if update.effective_user else 'неизвестного пользователя'}")
    
    status_info = {
        'status': 'ok',
        'message': 'Bot is running',
        'time': datetime.now().isoformat(),
        'webhook_enabled': USE_WEBHOOK,
        'webhook_url': WEBHOOK_URL if USE_WEBHOOK else None
    }
    
    await update.message.reply_text(
        f"Бот работает!\n\nВремя сервера: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Режим вебхука: {'Включен' if USE_WEBHOOK else 'Отключен'}"
    )


async def start_simple(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Упрощенная версия обработчика команды /start без ConversationHandler и базы данных."""
    try:
        user = update.effective_user
        logger.info(f"Вызвана упрощенная команда /start_simple от пользователя {user.id}")
        
        # Простой ответ без использования базы данных
        await update.message.reply_text(
            f"Привет, {user.first_name}! Это упрощенная версия команды /start.\n\n"
            "Если вы видите это сообщение, значит бот получает и обрабатывает команды.\n"
            "Для продолжения регистрации используйте команду /start."
        )
        logger.info(f"Отправлен упрощенный ответ пользователю {user.id}")
    except Exception as e:
        logger.error(f"Ошибка в упрощенном обработчике start_simple: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        try:
            await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except Exception:
            pass


# Добавим универсальный обработчик для логирования всех входящих обновлений
async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует все входящие обновления для диагностики."""
    try:
        logger.info(f"=== ПОЛУЧЕНО ОБНОВЛЕНИЕ ===")
        logger.info(f"Update ID: {update.update_id}")
        
        # Проверяем тип обновления
        if update.message:
            logger.info(f"Тип: Сообщение")
            logger.info(f"От пользователя: {update.effective_user.id} (@{update.effective_user.username or 'нет'})")
            logger.info(f"Чат ID: {update.effective_chat.id}")
            
            if update.message.text:
                logger.info(f"Текст: {update.message.text}")
                
            if update.message.entities:
                for entity in update.message.entities:
                    if entity.type == 'bot_command':
                        command = update.message.text[entity.offset:entity.offset+entity.length]
                        logger.info(f"Обнаружена команда: {command}")
        
        elif update.callback_query:
            logger.info(f"Тип: Callback Query")
            logger.info(f"От пользователя: {update.effective_user.id}")
            logger.info(f"Данные: {update.callback_query.data}")
        
        else:
            logger.info(f"Другой тип обновления: {update}")
            
    except Exception as e:
        logger.error(f"Ошибка при логировании обновления: {e}")


async def webhook_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверяет и отображает статус вебхука."""
    try:
        logger.info(f"Запрошена информация о статусе вебхука")
        
        webhook_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
        
        try:
            response = requests.get(webhook_url)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("ok"):
                webhook_info = data.get("result", {})
                
                message = "📊 **Информация о вебхуке**\n\n"
                message += f"URL: {webhook_info.get('url', 'Не установлен')}\n"
                message += f"Используется: {'Да' if webhook_info.get('url') else 'Нет'}\n"
                message += f"Последняя ошибка: {webhook_info.get('last_error_message', 'Нет ошибок')}\n"
                message += f"Ожидающие обновления: {webhook_info.get('pending_update_count', 0)}\n"
                message += f"Максимальные соединения: {webhook_info.get('max_connections', 'Не указано')}\n"
                
                await update.message.reply_text(message)
                logger.info(f"Информация о вебхуке отправлена пользователю")
            else:
                await update.message.reply_text(f"Ошибка при получении информации о вебхуке: {data.get('description', 'Неизвестная ошибка')}")
                logger.error(f"Ошибка при запросе getWebhookInfo: {data.get('description')}")
                
        except Exception as e:
            await update.message.reply_text(f"Ошибка при проверке вебхука: {e}")
            logger.error(f"Исключение при проверке вебхука: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка в обработчике webhook_status: {e}")


# Функция для автоматической проверки статуса вебхука
def check_webhook_status():
    """Проверяет текущий статус вебхука и логирует результаты."""
    logger.info("Проверка статуса вебхука...")
    
    if not USE_WEBHOOK:
        logger.info("Режим вебхука не активирован, проверка не требуется")
        return
    
    webhook_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
    
    try:
        response = requests.get(webhook_url)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            webhook_info = data.get("result", {})
            
            logger.info(f"=== СТАТУС ВЕБХУКА ===")
            logger.info(f"URL: {webhook_info.get('url', 'Не установлен')}")
            logger.info(f"Используется: {'Да' if webhook_info.get('url') else 'Нет'}")
            
            if webhook_info.get('last_error_message'):
                logger.error(f"Последняя ошибка вебхука: {webhook_info.get('last_error_message')}")
                logger.error(f"Время ошибки: {webhook_info.get('last_error_date')}")
            else:
                logger.info("Ошибок вебхука не обнаружено")
                
            logger.info(f"Ожидающие обновления: {webhook_info.get('pending_update_count', 0)}")
            
            # Проверка соответствия URL
            if WEBHOOK_URL and webhook_info.get('url') != WEBHOOK_URL:
                logger.warning(f"Несоответствие URL вебхука: текущий {webhook_info.get('url')}, ожидаемый {WEBHOOK_URL}")
        else:
            logger.error(f"Ошибка при получении информации о вебхуке: {data.get('description', 'Неизвестная ошибка')}")
            
    except Exception as e:
        logger.error(f"Исключение при проверке вебхука: {e}")


async def start_reliable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Надежная обработка команды /start без сложной логики и зависимости от базы данных."""
    try:
        user = update.effective_user
        logger.info(f"Пользователь @{user.username} (ID: {user.id}) отправил команду /start")
        
        welcome_message = (
            f"Привет, {user.first_name}! 👋\n\n"
            "Я бот для сбора обратной связи от студентов. "
            "С моей помощью вы можете регистрировать студентов и получать от них отзывы.\n\n"
            "🔹 Нажмите /help чтобы узнать о доступных командах\n"
            "🔹 Используйте /ping чтобы проверить работу бота\n"
            "🔹 Используйте /webhook_status для проверки статуса вебхука"
        )
        
        await update.message.reply_text(welcome_message)
        logger.info(f"Приветственное сообщение отправлено пользователю {user.id}")
        
        # Пробуем выполнить штатную логику регистрации, но не критично, если не сработает
        try:
            # Создаем обещание для асинхронного выполнения оригинального обработчика
            context.application.create_task(start(update, context))
            logger.info("Запущена стандартная обработка команды /start")
        except Exception as e:
            logger.warning(f"Не удалось запустить стандартную обработку команды /start: {e}")
            # Не прерываем выполнение, т.к. основное сообщение уже отправлено
    
    except Exception as e:
        logger.error(f"Ошибка в надежном обработчике команды /start: {e}")
        try:
            await update.message.reply_text(
                "Извините, произошла ошибка при обработке команды. "
                "Пожалуйста, попробуйте еще раз или обратитесь к администратору."
            )
        except:
            pass  # Если не удалось отправить сообщение об ошибке, просто логируем и продолжаем


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает справочную информацию по доступным командам."""
    try:
        help_text = (
            "📚 *Доступные команды:*\n\n"
            "/start - Запуск бота и регистрация\n"
            "/register - Полная регистрация с выбором группы и даты\n"
            "/help - Показать это сообщение\n"
            "/ping - Проверить работу бота\n"
            "/webhook_status - Проверить статус вебхука\n\n"
            "Для отправки обратной связи просто напишите сообщение боту."
        )
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
        logger.info(f"Отправлена справочная информация пользователю {update.effective_user.id}")
    
    except Exception as e:
        logger.error(f"Ошибка при отправке справочной информации: {e}")
        try:
            await update.message.reply_text(
                "Произошла ошибка при отображении справки. Пожалуйста, попробуйте позже."
            )
        except:
            pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок для перехвата и логирования исключений."""
    logger.error("Произошла ошибка при обработке обновления")
    
    # Получаем информацию об ошибке
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    
    # Логируем ошибку с полным трейсбеком
    logger.error(f"Исключение: {context.error}\n{tb_string}")
    
    # Уведомляем пользователя, если возможно
    if update and hasattr(update, "effective_message") and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Извините, произошла ошибка при обработке вашего запроса. "
                "Администратор уведомлен о проблеме."
            )
        except:
            logger.error("Не удалось отправить сообщение об ошибке пользователю")
    
    # Отправляем информацию об ошибке менеджеру, если указан ID чата
    if MANAGER_CHAT_ID:
        try:
            error_message = f"⚠️ *Ошибка в боте:*\n`{context.error}`"
            
            # Добавляем информацию о пользователе, если доступна
            if update and hasattr(update, "effective_user") and update.effective_user:
                user = update.effective_user
                error_message += f"\n\n👤 *Пользователь:* {user.first_name} (@{user.username or 'нет'}, ID: {user.id})"
            
            # Добавляем сообщение пользователя, если доступно
            if update and hasattr(update, "effective_message") and update.effective_message:
                msg = update.effective_message
                if msg.text:
                    error_message += f"\n\n📝 *Сообщение:* `{msg.text[:100]}`"
            
            # Отправляем сокращенный стек вызовов
            stack_trace = "\n".join(tb_list[-5:])  # Последние 5 строк стека
            error_message += f"\n\n🔍 *Часть стека вызовов:*\n`{stack_trace[:300]}...`"
            
            await context.bot.send_message(
                chat_id=MANAGER_CHAT_ID,
                text=error_message,
                parse_mode="Markdown"
            )
            logger.info("Сообщение об ошибке отправлено менеджеру")
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке менеджеру: {e}")


def setup_application(application):
    """Подготавливает приложение бота с обработкой ошибок."""
    try:
        # Добавляем обработчик для логирования всех обновлений
        application.add_handler(MessageHandler(filters.ALL, log_all_updates), group=-1)
        logger.info("Добавлен обработчик для логирования всех обновлений")
        
        # Добавляем надежный обработчик для команды /start (будет работать всегда)
        application.add_handler(CommandHandler("start", start_reliable))
        logger.info("Добавлен надежный обработчик для команды /start")
        
        # Добавляем обработчик для простой команды /start
        application.add_handler(CommandHandler("start_basic", start_simple))
        logger.info("Добавлен обработчик для команды /start_basic")
        
        # Добавляем ConversationHandler для основной логики
        try:
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("register", start)],  # Используем другую команду, чтобы избежать конфликта
                states={
                    CHOOSING_GROUP: [CallbackQueryHandler(group_choice, pattern="^group_")],
                    ENTERING_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_date_entered)]
                },
                fallbacks=[CommandHandler("cancel", cancel)],
                name="registration_conversation",
                per_message=True
            )
            application.add_handler(conv_handler)
            logger.info("Добавлен ConversationHandler для регистрации")
        except Exception as e:
            logger.error(f"Ошибка при настройке ConversationHandler: {e}")
            # Продолжаем настройку других обработчиков
        
        # Добавляем обработчик для текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_message))
        logger.info("Добавлен обработчик для текстовых сообщений")
        
        # Добавляем обработчик для команды /ping
        application.add_handler(CommandHandler("ping", ping_handler))
        logger.info("Добавлен обработчик для /ping")
        
        # Добавляем обработчик для проверки статуса вебхука
        application.add_handler(CommandHandler("webhook_status", webhook_status))
        logger.info("Добавлен обработчик для проверки статуса вебхука")
        
        # Добавляем обработчик для команды /help
        application.add_handler(CommandHandler("help", help_command))
        logger.info("Добавлен обработчик для /help")
        
        # Настраиваем обработчик ошибок
        application.add_error_handler(error_handler)
        logger.info("Добавлен обработчик ошибок")
        
        return application
    except Exception as e:
        logger.error(f"Критическая ошибка при настройке приложения: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


def setup_scheduler():
    """Настраивает планировщик задач и добавляет задачи проверки расписания."""
    try:
        # Создаем планировщик
        scheduler = BackgroundScheduler()
        logger.info("Планировщик создан")
        
        # Проверяем, инициализировано ли расписание
        logger.info("Инициализация расписания...")
        schedule_initialized = init_schedule()
        
        if not schedule_initialized:
            logger.warning("Инициализация расписания не удалась. Функциональность может быть ограничена.")
            return scheduler, False
        
        # Текущее время для проверки
        now = datetime.now(pytz.timezone('Europe/Moscow'))
        logger.info(f"Текущее время системы: {now}")
        
        # Настройка планировщика для проверки расписаний каждые 10 минут
        scheduler.add_job(
            check_and_schedule_feedback_requests,
            IntervalTrigger(minutes=10),
            id='check_schedule'
        )
        
        # Также выполняем проверку при запуске через 30 секунд
        scheduler.add_job(
            check_and_schedule_feedback_requests,
            'date',
            run_date=now + timedelta(seconds=30),
            id='initial_check'
        )
        
        logger.info("Планировщик настроен с задачами")
        return scheduler, True
    
    except Exception as e:
        logger.error(f"Ошибка при настройке планировщика: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return BackgroundScheduler(), False


def start_health_check_server(port=8080):
    """Запускает HTTP-сервер для проверки работоспособности системы.
    
    Если Flask доступен, использует его, иначе использует встроенный HTTP-сервер.
    Поддерживает эндпоинты:
    - /ping - возвращает JSON-ответ о статусе сервера
    - /health - более подробную информацию о состоянии системы
    """
    # Проверка доступности Flask
    flask_available = False
    try:
        import flask
        flask_available = True
        logger.info("Flask доступен и будет использован для сервера проверки здоровья")
    except ImportError:
        logger.info("Flask не доступен, будет использован встроенный HTTP-сервер")
    
    # Используем Flask, если он доступен
    if flask_available:
        try:
            from flask import Flask, jsonify
            
            app = Flask(__name__)
            
            @app.route('/ping')
            def ping():
                return jsonify({
                    'status': 'ok',
                    'message': 'Бот работает',
                    'timestamp': datetime.now().isoformat()
                }), 200
            
            @app.route('/health')
            def health():
                # Проверка состояния бота
                bot_status = {
                    'status': 'ok',
                    'message': 'Бот запущен и работает',
                    'timestamp': datetime.now().isoformat(),
                    'webhook_mode': bool(os.getenv('WEBHOOK_URL')),
                    'database': check_database_health()
                }
                return jsonify(bot_status), 200
            
            # Запускаем в отдельном потоке
            threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port, debug=False), daemon=True).start()
            logger.info(f"Flask-сервер для проверки работоспособности запущен на порту {port}")
            
        except Exception as e:
            logger.error(f"Ошибка при запуске Flask-сервера для проверки работоспособности: {e}")
            logger.error(traceback.format_exc())
    
    # Если Flask недоступен или произошла ошибка, используем встроенный сервер
    else:
        class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/ping':
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    
                    response = {
                        'status': 'ok',
                        'message': 'Бот работает',
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                
                elif self.path == '/health':
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    
                    # Проверка состояния бота
                    bot_status = {
                        'status': 'ok',
                        'message': 'Бот запущен и работает',
                        'timestamp': datetime.now().isoformat(),
                        'webhook_mode': bool(os.getenv('WEBHOOK_URL')),
                        'database': check_database_health()
                    }
                    
                    self.wfile.write(json.dumps(bot_status).encode('utf-8'))
                
                else:
                    self.send_response(404)
                    self.end_headers()
        
        def run_simple_server():
            try:
                server = http.server.HTTPServer(('0.0.0.0', port), HealthCheckHandler)
                logger.info(f"HTTP-сервер для проверки работоспособности (simple) запущен на порту {port}")
                server.serve_forever()
            except Exception as e:
                logger.error(f"Ошибка при запуске HTTP-сервера для проверки работоспособности: {e}")
                logger.error(traceback.format_exc())
        
        # Запускаем в отдельном потоке
        threading.Thread(target=run_simple_server, daemon=True).start()

def check_database_health():
    """Проверяет состояние подключения к базе данных."""
    try:
        # Проверка соединения с БД
        db_connected = check_database_connection()
        
        # Проверка наличия таблиц
        tables_exist = False
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(DATABASE_URL, echo=False)
            
            with engine.connect() as connection:
                # Используем соответствующий запрос в зависимости от типа базы данных
                if 'sqlite' in DATABASE_URL:
                    # SQLite
                    result = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                else:
                    # PostgreSQL
                    result = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
                
                tables = [row[0] for row in result]
                tables_exist = len(tables) > 0
                
        except Exception as e:
            logger.error(f"Ошибка при проверке таблиц в базе данных: {e}")
        
        return {
            'connected': db_connected,
            'tables_exist': tables_exist,
            'ready': DB_READY
        }
        
    except Exception as e:
        logger.error(f"Ошибка при проверке здоровья базы данных: {e}")
        logger.error(traceback.format_exc())
        return {
            'connected': False,
            'tables_exist': False,
            'ready': False,
            'error': str(e)
        }

def create_db_tables():
    """Создает таблицы в базе данных, если они не существуют."""
    import traceback
    logging.info("Проверка и создание таблиц в базе данных...")
    
    try:
        # Проверка на PostgreSQL URL от Render (который начинается с postgres://)
        # SQLAlchemy 2.0+ требует postgresql:// вместо postgres://
        db_url = DATABASE_URL
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
            logging.info("URL базы данных преобразован из postgres:// в postgresql://")
            
        # Создание движка SQLAlchemy
        from sqlalchemy import create_engine
        engine = create_engine(db_url, echo=False)
        
        # Импортируем базовый класс и создаем таблицы
        from database import Base
        Base.metadata.create_all(engine)
        logging.info("Таблицы созданы или уже существуют")
        
        # Проверяем, существуют ли таблицы
        with engine.connect() as connection:
            # Используем соответствующий запрос в зависимости от типа базы данных
            if 'sqlite' in db_url:
                # SQLite
                result = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            else:
                # PostgreSQL
                result = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
            
            tables = [row[0] for row in result]
            logging.info(f"Доступные таблицы: {tables}")
            
            if len(tables) > 0:
                logging.info("✅ Таблицы существуют в базе данных")
                return True
            else:
                logging.warning("⚠️ Таблицы не найдены в базе данных")
                return False
        
    except Exception as e:
        logging.error(f"❌ Ошибка при проверке и создании таблиц: {e}")
        logging.error(traceback.format_exc())
        return False

def setup_logging():
    """Настраивает логгирование для бота."""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.INFO)
    
    # Уровень логгирования основного логгера
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Проверяем режим отладки
    if os.getenv('DEBUG', 'False').lower() == 'true':
        logger.setLevel(logging.DEBUG)
        logger.debug("Включен режим отладки, установлен уровень логгирования DEBUG")
    
    return logger

def main() -> None:
    """Запуск бота."""
    # Получение глобальных переменных
    global DB_READY, DATABASE_URL

    # Загрузка переменных окружения и настройка логгирования
    load_dotenv()  # Читаем .env файл
    setup_logging()
    
    # Проверка и настройка базы данных
    logging.info("Проверка соединения с базой данных...")
    if DATABASE_URL.startswith('postgres://'):
        # Исправляем URL для совместимости с SQLAlchemy 2.0+
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        logging.info("URL базы данных преобразован из postgres:// в postgresql://")
    
    # Создаем таблицы в базе данных, если они не существуют
    create_db_tables()
    
    # Устанавливаем флаг готовности базы данных
    DB_READY = True
    
    # Получаем токен и создаем экземпляр приложения
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logging.error("Токен не найден. Укажите TELEGRAM_TOKEN в .env файле.")
        sys.exit(1)
    
    # Проверка запуска в режиме вебхука или локального поллинга
    webhook_url = os.getenv('WEBHOOK_URL')
    
    # Создание и настройка приложения
    application = ApplicationBuilder().token(token).build()
    setup_application(application)
    
    # Запуск сервера для проверки здоровья системы
    try:
        start_health_check_server()
    except Exception as e:
        logging.error(f"Не удалось запустить сервер проверки здоровья: {e}")
    
    # Запуск бота
    if webhook_url:
        # Режим вебхука (для Render)
        logging.info(f"Запускаем бота в режиме вебхука на {webhook_url}")
        port = int(os.getenv('PORT', 8443))
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=f"/{token}",
            webhook_url=webhook_url
        )
    else:
        # Режим поллинга (для локальной разработки)
        logging.info("Запускаем бота в режиме поллинга (локальная разработка)")
        application.run_polling()


if __name__ == "__main__":
    main() 