"""
Обработчик команды /start.
Отвечает за регистрацию пользователя и выбор группы.
"""

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ContextTypes, 
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

from database import check_user_exists, create_new_user
from utils.helpers import parse_date, get_date_string
from config import Config

# Настройка логирования
logger = logging.getLogger(__name__)

# Состояния диалога
CHOOSING_GROUP, ENTERING_START_DATE = range(2)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик команды /start.
    Приветствует пользователя и предлагает выбрать группу.
    """
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запустил команду /start")
    
    # Проверяем, зарегистрирован ли пользователь
    if check_user_exists(user.id):
        await update.message.reply_text(
            f"Привет, {user.first_name}! Вы уже зарегистрированы. "
            "Чтобы оставить обратную связь о занятии, просто напишите мне сообщение."
        )
        return ConversationHandler.END
    
    # Если пользователь новый, предлагаем выбрать группу
    await update.message.reply_text(
        f"Добро пожаловать, {user.first_name}! "
        "Пожалуйста, укажите, в какую группу вы ходите:"
    )
    
    # Отправляем варианты групп
    keyboard = []
    for group, description in Config.GROUPS.items():
        keyboard.append([f"{description} ({group})"])
    
    await update.message.reply_text(
        "Выберите один из вариантов:",
        reply_markup={"keyboard": keyboard, "one_time_keyboard": True}
    )
    
    return CHOOSING_GROUP

async def group_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор группы и запрашивает дату начала занятий.
    """
    text = update.message.text
    user = update.effective_user
    
    # Парсим выбранную группу
    group_info = None
    for group, description in Config.GROUPS.items():
        if f"{description} ({group})" == text:
            group_info = group
            break
    
    if not group_info:
        await update.message.reply_text(
            "Пожалуйста, выберите группу из предложенных вариантов."
        )
        return CHOOSING_GROUP
    
    # Сохраняем выбор группы в контексте пользователя
    context.user_data['group'] = group_info
    # Определяем день недели для группы
    context.user_data['group_day'] = 0 if group_info == 'weekday' else 5  # 0 - пн, 5 - сб
    
    logger.info(f"Пользователь {user.id} выбрал группу: {group_info}")
    
    # Запрашиваем дату начала занятий
    await update.message.reply_text(
        "Отлично! Теперь укажите дату начала вашего курса в формате ДД.ММ.ГГГГ\n"
        "Например: 01.09.2023"
    )
    
    return ENTERING_START_DATE

async def start_date_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает ввод даты начала занятий и завершает регистрацию.
    """
    text = update.message.text
    user = update.effective_user
    
    # Парсим дату
    try:
        start_date = parse_date(text)
        if not start_date:
            raise ValueError("Неверный формат даты")
    except ValueError:
        await update.message.reply_text(
            "Пожалуйста, введите дату в формате ДД.ММ.ГГГГ, например: 01.09.2023"
        )
        return ENTERING_START_DATE
    
    # Получаем данные из контекста
    group = context.user_data.get('group')
    group_day = context.user_data.get('group_day')
    
    # Преобразуем дату в строку для логирования
    date_str = get_date_string(start_date)
    
    # Логирование перед созданием пользователя
    logger.info(f"Попытка создания пользователя: ID={user.id}, имя={user.first_name}, "
                f"группа={group}, день={group_day}, дата={date_str}")
    
    # Создаем пользователя в базе данных
    success = create_new_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        group=group,
        group_day=group_day,
        start_date=start_date
    )
    
    if success:
        logger.info(f"Пользователь {user.id} успешно зарегистрирован. Группа: {group}, дата начала: {date_str}")
        await update.message.reply_text(
            f"Отлично! Вы успешно зарегистрированы в группе {Config.GROUPS[group]}.\n"
            f"Дата начала курса: {date_str}.\n\n"
            "После каждого занятия я буду просить вас оставить обратную связь. "
            "Вы также можете в любой момент отправить мне сообщение с отзывом."
        )
    else:
        logger.error(f"Ошибка при регистрации пользователя {user.id}")
        await update.message.reply_text(
            "К сожалению, произошла ошибка при регистрации. "
            "Пожалуйста, попробуйте еще раз позже или обратитесь к администратору."
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет текущий диалог.
    """
    user = update.effective_user
    logger.info(f"Пользователь {user.id} отменил регистрацию")
    
    await update.message.reply_text(
        "Регистрация отменена. Вы можете начать заново, отправив команду /start"
    )
    
    return ConversationHandler.END

# Создаем обработчик диалога регистрации
start_command_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start_command)],
    states={
        CHOOSING_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, group_choice)],
        ENTERING_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_date_entered)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
) 