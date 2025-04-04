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
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

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

if not TELEGRAM_TOKEN:
    logger.error("Токен Telegram не найден в переменных окружения!")
    sys.exit(1)

logger.info(f"Используется токен: {TELEGRAM_TOKEN[:5]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"ID менеджера: {MANAGER_CHAT_ID}")

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
                # Используем text() для защиты от SQL инъекций и соответствия требованиям SQLAlchemy 2.0
                query = text("SELECT id, is_active FROM users WHERE chat_id = :chat_id")
                result = s.execute(query, {"chat_id": chat_id}).fetchone()
                return result
            
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
                        query = text("UPDATE users SET is_active = :is_active WHERE chat_id = :chat_id")
                        s.execute(query, {"is_active": True, "chat_id": chat_id})
                        s.commit()
                    
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
                new_user = User(
                    chat_id=chat_id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name
                )
                s.add(new_user)
                s.commit()
                return True
            
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


def setup_application():
    """Подготавливает приложение бота с обработкой ошибок."""
    try:
        # Создаем и настраиваем экземпляр приложения
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("Приложение создано")
        
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
    """
    Запускает простой HTTP-сервер для проверки работоспособности бота.
    Этот сервер будет отвечать на запросы /ping и используется для проверки
    работоспособности сервиса на платформах, таких как Render.
    
    Args:
        port (int): Порт для запуска HTTP-сервера. По умолчанию 8080.
    """
    # Импортируем threading здесь, чтобы он был доступен везде в функции
    import threading
    
    try:
        # Пробуем использовать Flask, если он доступен
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/ping', methods=['GET'])
        def ping():
            """Простой эндпоинт для проверки работоспособности сервиса."""
            status = "активен" if DB_READY else "активен, но база данных недоступна"
            return jsonify({
                'status': status,
                'message': 'Бот телеграм запущен и работает',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'webhook_enabled': USE_WEBHOOK,
                'webhook_url': WEBHOOK_URL if USE_WEBHOOK else None
            })
        
        # Запускаем Flask в отдельном потоке
        def run_flask_app():
            try:
                app.run(host='0.0.0.0', port=port)
            except Exception as e:
                logger.error(f"Ошибка при запуске HTTP-сервера для проверки работоспособности: {e}")
        
        # Запускаем в фоновом режиме
        thread = threading.Thread(target=run_flask_app)
        thread.daemon = True  # Поток будет автоматически завершен при закрытии основного потока
        thread.start()
        logger.info(f"HTTP-сервер для проверки работоспособности (Flask) запущен на порту {port}")
    
    except ImportError:
        # Если Flask не установлен, используем встроенный HTTP-сервер
        logger.warning("Flask не установлен, используем встроенный http.server для проверки работоспособности")
        
        class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
            def _set_headers(self):
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
            
            def do_GET(self):
                if self.path == '/ping':
                    self._set_headers()
                    status = "активен" if DB_READY else "активен, но база данных недоступна"
                    response = {
                        'status': status,
                        'message': 'Бот телеграм запущен и работает',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'webhook_enabled': USE_WEBHOOK,
                        'webhook_url': WEBHOOK_URL if USE_WEBHOOK else None
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
        
        def run_simple_server():
            try:
                server = http.server.HTTPServer(('0.0.0.0', port), HealthCheckHandler)
                logger.info(f"HTTP-сервер для проверки работоспособности (simple) запущен на порту {port}")
                server.serve_forever()
            except Exception as e:
                logger.error(f"Ошибка при запуске простого HTTP-сервера: {e}")
        
        thread = threading.Thread(target=run_simple_server)
        thread.daemon = True
        thread.start()
        logger.info(f"HTTP-сервер для проверки работоспособности запущен на порту {port}")
    
    except Exception as e:
        logger.error(f"Невозможно запустить HTTP-сервер для проверки работоспособности: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main() -> None:
    """Запуск бота."""
    try:
        logger.info(f"Запуск бота в {'webhook' if USE_WEBHOOK else 'polling'} режиме")
        
        # Проверка соединения с базой данных и инициализация расписания
        if check_database_connection():
            scheduler, should_run_scheduler = setup_scheduler()
            
            if should_run_scheduler:
                logger.info("Запуск планировщика")
                scheduler.start()
                logger.info("Планировщик запущен")
            else:
                logger.warning("Планировщик не запущен из-за проблем с базой данных")
        
        # Проверяем статус вебхука перед запуском
        check_webhook_status()
        
        # Создание и настройка приложения
        application = setup_application()
        logger.info("Приложение настроено и готово к запуску")
        
        # Запуск сервера проверки работоспособности
        logger.info("Запуск сервера проверки работоспособности")
        start_health_check_server(port=8080)
        
        if USE_WEBHOOK:
            # Для Render обеспечиваем корректный путь без повторения токена
            if WEBHOOK_URL and "onrender.com" in WEBHOOK_URL:
                # Извлекаем базовый URL без пути
                base_url = '/'.join(WEBHOOK_URL.split('/')[:3])
                
                # Получаем только последнюю часть пути (предполагается, что это токен)
                path_parts = WEBHOOK_URL.split('/')
                if len(path_parts) > 3:
                    webhook_path = '/' + '/'.join(path_parts[3:])
                    logger.info(f"Используем путь вебхука: {webhook_path}")
                else:
                    webhook_path = f"/bot{TELEGRAM_TOKEN}"
                    logger.info(f"Используем стандартный путь вебхука: {webhook_path}")
                
                # Запуск бота с вебхуком, используя правильный путь
                logger.info(f"Запуск веб-сервера на порту {PORT} с путем вебхука {webhook_path}")
                application.run_webhook(
                    listen="0.0.0.0",
                    port=PORT,
                    url_path=webhook_path,
                    webhook_url=WEBHOOK_URL
                )
            else:
                # Стандартный случай запуска вебхука
                webhook_path = f"/bot{TELEGRAM_TOKEN}"
                logger.info(f"Запуск веб-сервера на порту {PORT} с путем вебхука {webhook_path}")
                
                application.run_webhook(
                    listen="0.0.0.0",
                    port=PORT,
                    url_path=webhook_path,
                    webhook_url=WEBHOOK_URL
                )
        else:
            # Запуск через long polling
            logger.info("Запуск через long polling")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main() 