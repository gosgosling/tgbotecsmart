import os
import logging
from datetime import datetime, timedelta, time as dt_time
import pytz
import sys

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
    """Обработчик команды /start."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Проверка, если пользователь уже зарегистрирован
    session = get_session()
    existing_user = session.query(User).filter(User.chat_id == chat_id).first()
    
    if existing_user:
        # Если пользователь существует, просто приветствуем его
        await update.message.reply_text(
            f"Привет, {user.first_name}! Рады видеть вас снова в боте обратной связи."
        )
        # Сбросим статус пользователя, если он был в процессе регистрации
        existing_user.is_active = True
        session.commit()
        session.close()
        return ConversationHandler.END
    
    # Создаем нового пользователя
    new_user = User(
        chat_id=chat_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    session.add(new_user)
    session.commit()
    session.close()
    
    # Отправляем приветствие
    await update.message.reply_text(
        f"Здравствуйте, {user.first_name}! Добро пожаловать в бот обратной связи компании.\n\n"
        "Пожалуйста, выберите вашу группу занятий:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Группа будни", callback_data="group_weekday")],
            [InlineKeyboardButton("Группа выходного дня", callback_data="group_weekend")]
        ])
    )
    
    return CHOOSING_GROUP


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