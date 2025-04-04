import os
import logging
import sys
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение токена бота
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    logger.error("Токен Telegram не найден в переменных окружения!")
    sys.exit(1)

logger.info(f"Используется токен: {TELEGRAM_TOKEN[:5]}...{TELEGRAM_TOKEN[-5:]}")

async def start_handler(update, context):
    """Простой обработчик команды /start для тестирования."""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} отправил команду /start")
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! Это тестовый режим бота в режиме опроса.\n"
        "Бот получил вашу команду /start и отвечает на нее.\n\n"
        "Если вы видите это сообщение, значит бот настроен правильно и может отправлять сообщения.\n"
        "Теперь вы можете настроить вебхук для основного режима работы."
    )

async def echo(update, context):
    """Эхо-обработчик для тестирования получения и отправки сообщений."""
    logger.info(f"Получено сообщение: {update.message.text}")
    
    await update.message.reply_text(
        f"Я получил ваше сообщение: {update.message.text}\n\n"
        "Если вы видите этот ответ, значит бот работает корректно в режиме опроса."
    )

def main():
    """Запуск бота в режиме опроса (polling)."""
    logger.info("Запуск бота в режиме опроса (polling) для тестирования")
    
    try:
        # Создание приложения бота
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("Приложение бота создано")
        
        # Добавление обработчиков
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
        logger.info("Обработчики добавлены")
        
        # Запуск бота в режиме опроса
        logger.info("Запуск в режиме опроса (polling)")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске бота: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main() 