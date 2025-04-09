"""
Обработчик обратной связи от пользователей.
Отвечает за обработку сообщений с обратной связью и отправку запросов на обратную связь.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from database import check_user_exists, save_feedback
from config import Config

# Настройка логирования
logger = logging.getLogger(__name__)

async def process_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает сообщения с обратной связью от пользователей.
    Сохраняет отзыв в базе данных и пересылает его администратору.
    """
    user = update.effective_user
    message_text = update.message.text
    
    logger.info(f"Получено сообщение от пользователя {user.id}: {message_text[:50]}...")
    
    # Проверяем, зарегистрирован ли пользователь
    if not check_user_exists(user.id):
        logger.warning(f"Пользователь {user.id} не зарегистрирован, но отправил сообщение")
        await update.message.reply_text(
            "Похоже, вы еще не зарегистрированы. Пожалуйста, используйте команду /start для регистрации."
        )
        return
    
    # Сохраняем обратную связь в базе данных
    if save_feedback(user.id, message_text):
        logger.info(f"Обратная связь от пользователя {user.id} сохранена успешно")
    else:
        logger.error(f"Ошибка при сохранении обратной связи от пользователя {user.id}")
    
    # Пересылаем обратную связь администратору
    if Config.ADMIN_CHAT_ID:
        user_info = f"Пользователь: {user.first_name}"
        if user.last_name:
            user_info += f" {user.last_name}"
        if user.username:
            user_info += f" (@{user.username})"
        
        admin_message = f"📝 Получена обратная связь!\n\n{user_info}\nID: {user.id}\n\n{message_text}"
        
        try:
            await context.bot.send_message(
                chat_id=Config.ADMIN_CHAT_ID,
                text=admin_message
            )
            logger.info(f"Обратная связь от пользователя {user.id} переслана администратору")
        except Exception as e:
            logger.error(f"Ошибка при пересылке обратной связи администратору: {e}")
    else:
        logger.warning("ID администратора не задан, обратная связь не была переслана")
    
    # Благодарим пользователя за обратную связь
    await update.message.reply_text(
        "Спасибо за вашу обратную связь! Она поможет нам улучшить курс."
    )

async def send_feedback_request(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """
    Отправляет запрос на обратную связь пользователю.
    
    Args:
        context: Контекст обработчика
        chat_id: ID чата пользователя
        
    Returns:
        bool: True, если запрос успешно отправлен, иначе False
    """
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Привет! Как прошло сегодняшнее занятие?\n\n"
                "Пожалуйста, поделитесь своими впечатлениями, замечаниями или предложениями. "
                "Ваша обратная связь очень важна для нас!"
            )
        )
        logger.info(f"Запрос на обратную связь отправлен пользователю {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке запроса на обратную связь пользователю {chat_id}: {e}")
        return False

# Создаем обработчик текстовых сообщений
feedback_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, process_feedback) 