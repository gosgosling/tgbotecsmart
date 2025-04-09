"""
Конфигурационный файл для бота обратной связи.
Загружает настройки из переменных окружения.
"""

import os
import logging
from dotenv import load_dotenv

# Настройка логирования
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

class Config:
    """Класс конфигурации бота"""
    
    # Токен бота Telegram
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TELEGRAM_TOKEN:
        logger.warning("Не задан токен бота Telegram (TELEGRAM_TOKEN)")
    
    # ID администратора (для пересылки обратной связи)
    ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID не указан в переменных окружения. Обратная связь не будет пересылаться администратору.")
    
    # URL базы данных
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///feedback_bot.db')
    
    # Проверка URL базы данных
    if DATABASE_URL.startswith('sqlite:///'):
        # Проверка на существование файла для SQLite
        db_file = DATABASE_URL.replace('sqlite:///', '')
        if not os.path.exists(db_file) and db_file != ':memory:':
            logger.info(f"Файл базы данных SQLite '{db_file}' не существует и будет создан автоматически")
    elif DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://')
        logger.info("URL базы данных преобразован из postgres:// в postgresql://")
    
    # Режим отладки
    DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
    
    # Настройки групп
    GROUPS = {
        'weekday': 'Будни (пн-пт)',
        'weekend': 'Выходные (сб)'
    }
    
    # Дни недели
    WEEKDAYS = {
        0: 'Понедельник',
        1: 'Вторник',
        2: 'Среда',
        3: 'Четверг',
        4: 'Пятница',
        5: 'Суббота',
        6: 'Воскресенье'
    }

# Статус готовности базы данных
DB_READY = False

logger.info("Конфигурация загружена")
logger.debug(f"Бот использует токен: {Config.TELEGRAM_TOKEN[:5]}...{Config.TELEGRAM_TOKEN[-5:] if Config.TELEGRAM_TOKEN and len(Config.TELEGRAM_TOKEN) > 10 else '***'}")
logger.debug(f"База данных: {Config.DATABASE_URL.split('://')[0]}")
logger.debug(f"Режим отладки: {'включен' if Config.DEBUG else 'выключен'}") 