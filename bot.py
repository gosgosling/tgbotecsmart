"""
Основной файл бота обратной связи.
Отвечает за инициализацию бота, регистрацию обработчиков и запуск бота.
"""

import logging
import sys
import os
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler
from dotenv import load_dotenv

# Импортируем модуль базы данных и конфигурацию
import database
from config import Config

# Импортируем обработчики команд
from handlers import start_command, process_feedback, send_feedback_request, feedback_handler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO if not Config.DEBUG else logging.DEBUG,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# Инициализация базы данных
def setup_database():
    """Инициализирует базу данных и проверяет подключение"""
    try:
        # Инициализируем базу данных
        success = database.init_db()
        if not success:
            logger.error("Ошибка при инициализации базы данных")
            return False
        
        # Проверка подключения к БД через безопасный вызов
        try:
            if not database.check_database_connection():
                logger.error("Не удалось подключиться к базе данных")
                return False
        except AttributeError:
            # Если функция check_database_connection отсутствует
            logger.warning("Функция check_database_connection не найдена в модуле database")
            # Выполняем проверку подключения прямо здесь
            try:
                session = database.SessionLocal()
                result = session.execute(database.text("SELECT 1")).scalar()
                session.close()
                logger.info("✅ Соединение с базой данных установлено успешно")
            except Exception as e:
                logger.error(f"❌ Ошибка при проверке соединения с базой данных: {e}")
                return False
        
        logger.info("База данных успешно инициализирована")
        return True
    except Exception as e:
        logger.error(f"Неожиданная ошибка при настройке базы данных: {e}", exc_info=True)
        return False

def main():
    """Основная функция запуска бота"""
    try:
        # Загружаем переменные окружения
        load_dotenv()
        
        # Проверяем настройки
        logger.info(f"Токен бота задан: {'Да' if Config.TELEGRAM_TOKEN else 'Нет'}")
        logger.info(f"ID администратора задан: {'Да' if Config.ADMIN_CHAT_ID else 'Нет'}")
        logger.info(f"URL базы данных: {Config.DATABASE_URL.split('://')[0]}")
        logger.info(f"Режим отладки: {'Включен' if Config.DEBUG else 'Выключен'}")
        
        # Создаем директорию для логов, если она отсутствует
        os.makedirs('logs', exist_ok=True)
        
        # Инициализируем базу данных
        if not setup_database():
            logger.error("Не удалось настроить базу данных. Завершение работы бота.")
            return
        
        # Создаем экземпляр бота
        logger.info("Создание экземпляра бота...")
        application = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()
        
        # Регистрируем обработчики команд
        logger.info("Регистрация обработчиков команд...")
        application.add_handler(start_command)
        
        # Добавляем обработчик для получения обратной связи
        application.add_handler(feedback_handler)
        
        # Настройка списка команд бота
        logger.info("Настройка команд бота...")
        application.bot.set_my_commands([
            ("start", "Начать работу с ботом"),
            ("help", "Получить помощь по использованию бота")
        ])
        logger.info("Команды бота настроены")
        
        # Запускаем бота в режиме polling
        logger.info("Запуск бота в режиме polling...")
        application.run_polling(allowed_updates=["message", "callback_query"])
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 