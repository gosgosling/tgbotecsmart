import os
import logging
from datetime import datetime, timedelta, time as dt_time
import pytz
import sys
import threading
import http.server
import socketserver
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from database import User, Schedule, get_session, init_schedule
from utils import parse_date, format_date, get_current_moscow_time, get_weekday

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout  # Явно указываем вывод в stdout
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
CHECK_SERVER_PORT = int(os.environ.get('PORT', 8080))
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

# Создаем HTTP-сервер для проверки доступности
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            status_info = {
                'status': 'ok',
                'message': 'Bot is running',
                'time': datetime.now().isoformat(),
                'webhook_enabled': USE_WEBHOOK,
                'webhook_url': WEBHOOK_URL if USE_WEBHOOK else None
            }
            
            self.wfile.write(json.dumps(status_info).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        # Переопределяем логирование, чтобы оно шло через наш логгер
        logger.info(f"Health check: {self.address_string()} - {format % args}")

# Функция для запуска HTTP-сервера
def start_health_check_server():
    try:
        health_handler = HealthCheckHandler
        health_check_server = socketserver.TCPServer(("0.0.0.0", CHECK_SERVER_PORT), health_handler)
        logger.info(f"Запущен HTTP-сервер для проверки доступности на порту {CHECK_SERVER_PORT}")
        health_check_server.serve_forever()
    except Exception as e:
        logger.error(f"Ошибка при запуске HTTP-сервера проверки доступности: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start."""
    try:
        logger.info(f"[ДИАГНОСТИКА] Начало обработки команды /start от пользователя {update.effective_user.id}")
        
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        logger.info(f"[ДИАГНОСТИКА] Данные пользователя: id={user.id}, username={user.username}, first_name={user.first_name}")
        
        # Проверка, если пользователь уже зарегистрирован
        logger.info(f"[ДИАГНОСТИКА] Попытка получения сессии базы данных")
        try:
            session = get_session()
            logger.info(f"[ДИАГНОСТИКА] Сессия базы данных получена успешно")
        except Exception as db_error:
            logger.error(f"[ДИАГНОСТИКА] Ошибка при получении сессии базы данных: {db_error}")
            await update.message.reply_text(
                "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
            )
            return ConversationHandler.END
        
        try:
            logger.info(f"[ДИАГНОСТИКА] Поиск пользователя с chat_id={chat_id} в базе")
            existing_user = session.query(User).filter(User.chat_id == chat_id).first()
            logger.info(f"[ДИАГНОСТИКА] Результат поиска: {existing_user is not None}")
        except Exception as query_error:
            logger.error(f"[ДИАГНОСТИКА] Ошибка при поиске пользователя: {query_error}")
            session.close()
            await update.message.reply_text(
                "Произошла ошибка при доступе к базе данных. Пожалуйста, попробуйте позже."
            )
            return ConversationHandler.END
        
        if existing_user:
            # Если пользователь существует, просто приветствуем его
            logger.info(f"[ДИАГНОСТИКА] Пользователь {chat_id} уже существует в базе данных")
            try:
                await update.message.reply_text(
                    f"Привет, {user.first_name}! Рады видеть вас снова в боте обратной связи."
                )
                logger.info(f"[ДИАГНОСТИКА] Сообщение приветствия отправлено существующему пользователю")
            except Exception as msg_error:
                logger.error(f"[ДИАГНОСТИКА] Ошибка при отправке сообщения: {msg_error}")
            
            # Сбросим статус пользователя, если он был в процессе регистрации
            try:
                existing_user.is_active = True
                session.commit()
                logger.info(f"[ДИАГНОСТИКА] Статус пользователя обновлен в базе данных")
            except Exception as db_error:
                logger.error(f"[ДИАГНОСТИКА] Ошибка при обновлении статуса пользователя: {db_error}")
                session.rollback()
            finally:
                session.close()
                logger.info(f"[ДИАГНОСТИКА] Сессия базы данных закрыта")
            
            return ConversationHandler.END
        
        # Создаем нового пользователя
        logger.info(f"[ДИАГНОСТИКА] Создание нового пользователя с chat_id={chat_id}")
        try:
            new_user = User(
                chat_id=chat_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            session.add(new_user)
            session.commit()
            logger.info(f"[ДИАГНОСТИКА] Новый пользователь успешно добавлен в базу данных")
        except Exception as db_error:
            logger.error(f"[ДИАГНОСТИКА] Ошибка при создании нового пользователя: {db_error}")
            session.rollback()
            try:
                await update.message.reply_text(
                    "Произошла ошибка при регистрации. Пожалуйста, попробуйте позже."
                )
            except Exception:
                pass
            session.close()
            return ConversationHandler.END
        finally:
            session.close()
            logger.info(f"[ДИАГНОСТИКА] Сессия базы данных закрыта после создания пользователя")
        
        # Отправляем приветствие
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
    message = update.message.text
    user = update.effective_user
    
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
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения менеджеру: {e}")


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


def main() -> None:
    """Запуск бота."""
    try:
        # Инициализация расписания в базе данных
        logger.info("Инициализация расписания...")
        init_schedule()
        
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
        
        scheduler.start()
        logger.info("Планировщик запущен")
        
        # Создание приложения бота
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("Приложение бота создано")
        
        # Настройка обработчика регистрации
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                CHOOSING_GROUP: [CallbackQueryHandler(group_choice, pattern="^group_")],
                ENTERING_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_date_entered)]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            per_message=True  # Исправление предупреждения PTBUserWarning
        )
        
        # Добавление обработчиков
        application.add_handler(conv_handler)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_message))
        logger.info("Обработчики добавлены")
        
        # Запускаем HTTP-сервер для проверки доступности в отдельном потоке
        if USE_WEBHOOK:
            threading.Thread(target=start_health_check_server, daemon=True).start()
        
        # Запускаем бота в зависимости от режима (вебхук или polling)
        if USE_WEBHOOK:
            logger.info(f"Запуск в режиме вебхука на порту {PORT}, URL: {WEBHOOK_URL}")
            # Запускаем бота с вебхуком
            application.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=f"bot{TELEGRAM_TOKEN}",
                webhook_url=WEBHOOK_URL
            )
        else:
            logger.info("Запуск в режиме опроса (polling)")
            # Запускаем бота в режиме опроса
            application.run_polling()
            
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске бота: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main() 