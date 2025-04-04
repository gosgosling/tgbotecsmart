#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import logging
import requests
import time
import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("setup_render")

# Загрузка переменных окружения
load_dotenv()

# Получение важных переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///feedback_bot.db')
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')
RENDER_EXTERNAL_HOSTNAME = os.getenv('RENDER_EXTERNAL_HOSTNAME')

# Проверка наличия обязательных переменных
if not TELEGRAM_TOKEN:
    logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Переменная TELEGRAM_TOKEN не задана!")
    sys.exit(1)

if not DATABASE_URL:
    logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Переменная DATABASE_URL не задана!")
    sys.exit(1)

# Маскировка токена для логов
def mask_token(token):
    if not token:
        return None
    return token[:4] + "..." + token[-4:] if len(token) > 8 else "***"

logger.info(f"Проверка настройки для Render...")
logger.info(f"TELEGRAM_TOKEN: {mask_token(TELEGRAM_TOKEN)}")
logger.info(f"DATABASE_URL: {'sqlite:///...' if 'sqlite' in DATABASE_URL else DATABASE_URL.split('@')[0] + '@***'}")
logger.info(f"WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"RENDER_EXTERNAL_URL: {RENDER_EXTERNAL_URL}")
logger.info(f"RENDER_EXTERNAL_HOSTNAME: {RENDER_EXTERNAL_HOSTNAME}")

def check_database_connection():
    """Проверяет соединение с базой данных."""
    logger.info("Проверка соединения с базой данных...")
    
    try:
        # Проверка на PostgreSQL URL от Render (который начинается с postgres://)
        # SQLAlchemy 2.0+ требует postgresql:// вместо postgres://
        db_url = DATABASE_URL
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
            logger.info("URL базы данных преобразован из postgres:// в postgresql://")
        
        # Создание движка SQLAlchemy
        engine = create_engine(db_url, echo=False)
        
        # Проверка соединения
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar()
            
            if result == 1:
                logger.info("✅ Соединение с базой данных успешно установлено!")
                return True
            else:
                logger.error("❌ Соединение с базой данных установлено, но проверочный запрос вернул неправильный результат.")
                return False
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке соединения с базой данных: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def check_telegram_api():
    """Проверяет доступность API Telegram и информацию о боте."""
    logger.info("Проверка доступности API Telegram...")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            bot_info = data.get("result", {})
            logger.info(f"✅ API Telegram доступен")
            logger.info(f"Имя бота: {bot_info.get('first_name')}")
            logger.info(f"Имя пользователя: @{bot_info.get('username')}")
            logger.info(f"ID бота: {bot_info.get('id')}")
            logger.info(f"Поддержка Webhook: {bot_info.get('can_join_groups', 'Неизвестно')}")
            return True
        else:
            logger.error(f"❌ Ошибка при проверке API Telegram: {data.get('description', 'Неизвестная ошибка')}")
            return False
            
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при подключении к API Telegram: {e}")
        return False

def check_webhook_status():
    """Проверяет текущий статус вебхука."""
    logger.info("Проверка текущего статуса вебхука...")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            webhook_info = data.get("result", {})
            
            current_url = webhook_info.get('url', 'Не установлен')
            
            logger.info(f"=== СТАТУС ВЕБХУКА ===")
            logger.info(f"URL: {current_url}")
            logger.info(f"Вебхук активен: {'Да' if current_url else 'Нет'}")
            
            if current_url and WEBHOOK_URL and current_url != WEBHOOK_URL:
                logger.warning(f"⚠️ ВНИМАНИЕ: Текущий URL вебхука ({current_url}) не соответствует URL в .env файле ({WEBHOOK_URL})")
            
            if webhook_info.get('last_error_message'):
                logger.error(f"❌ Последняя ошибка: {webhook_info.get('last_error_message')}")
                
                # Конвертация UNIX timestamp в читаемую дату
                last_error_date = webhook_info.get('last_error_date')
                if last_error_date:
                    error_time = datetime.datetime.fromtimestamp(last_error_date).strftime('%Y-%m-%d %H:%M:%S')
                    logger.error(f"⏰ Время ошибки: {error_time}")
            else:
                logger.info("✅ Ошибок вебхука не обнаружено")
                
            logger.info(f"Ожидающие обновления: {webhook_info.get('pending_update_count', 0)}")
            logger.info(f"Максимальные соединения: {webhook_info.get('max_connections', 'Не указано')}")
            
            return webhook_info
        else:
            logger.error(f"❌ Ошибка при получении информации о вебхуке: {data.get('description', 'Неизвестная ошибка')}")
            return None
            
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при подключении к API Telegram: {e}")
        return None

def set_webhook():
    """Устанавливает или обновляет вебхук для бота."""
    # Определяем URL для вебхука
    webhook_url = WEBHOOK_URL
    
    # Если WEBHOOK_URL не указан в .env, пробуем использовать URL, предоставленный Render
    if not webhook_url and RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/bot{TELEGRAM_TOKEN}"
        logger.info(f"Использую URL из RENDER_EXTERNAL_URL: {webhook_url}")
    elif not webhook_url and RENDER_EXTERNAL_HOSTNAME:
        webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/bot{TELEGRAM_TOKEN}"
        logger.info(f"Использую URL из RENDER_EXTERNAL_HOSTNAME: {webhook_url}")
    
    if not webhook_url:
        logger.error("❌ Не удалось определить URL для вебхука. Укажите WEBHOOK_URL в .env файле.")
        return False
    
    logger.info(f"Установка вебхука по URL: {webhook_url}")
    
    # Параметры для установки вебхука
    params = {
        "url": webhook_url,
        "drop_pending_updates": True,
        "max_connections": 100
    }
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    
    try:
        response = requests.post(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            logger.info(f"✅ Вебхук успешно установлен по URL: {webhook_url}")
            logger.info(f"Ответ от API: {data.get('description', '')}")
            return True
        else:
            logger.error(f"❌ Ошибка при установке вебхука: {data.get('description', 'Неизвестная ошибка')}")
            return False
            
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при подключении к API Telegram: {e}")
        return False

def create_tables_if_not_exist():
    """Создает таблицы в базе данных, если они не существуют."""
    logger.info("Проверка и создание таблиц в базе данных...")
    
    try:
        # Проверка на PostgreSQL URL от Render (который начинается с postgres://)
        # SQLAlchemy 2.0+ требует postgresql:// вместо postgres://
        db_url = DATABASE_URL
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
            logger.info("URL базы данных преобразован из postgres:// в postgresql://")
        
        # Создание движка SQLAlchemy
        engine = create_engine(db_url, echo=False)
        
        # Импортируем классы моделей
        try:
            from database import Base, User, Schedule
            logger.info("Модели данных импортированы успешно")
            
            # Создаем таблицы
            Base.metadata.create_all(engine)
            logger.info("Таблицы созданы или уже существуют")
            
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
                logger.info(f"Доступные таблицы: {tables}")
                
                if 'users' in tables and 'schedules' in tables:
                    logger.info("✅ Необходимые таблицы существуют")
                    return True
                else:
                    logger.warning("⚠️ Некоторые необходимые таблицы отсутствуют")
                    return False
                
        except ImportError as e:
            logger.error(f"❌ Ошибка при импорте моделей данных: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при создании таблиц: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке и создании таблиц: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_webhook_with_message():
    """Тестирует вебхук путем отправки тестового сообщения на Telegram API."""
    if not WEBHOOK_URL:
        logger.warning("⚠️ URL вебхука не задан, тестирование невозможно.")
        return False
    
    logger.info(f"Тестирование вебхука на URL: {WEBHOOK_URL}")
    
    # Формируем тестовое сообщение (обновление), которое будет отправлено на вебхук
    test_update = {
        "update_id": int(time.time()),
        "message": {
            "message_id": int(time.time()) % 10000,
            "from": {
                "id": 12345,
                "is_bot": False,
                "first_name": "Тестовый",
                "last_name": "Пользователь",
                "username": "test_user"
            },
            "chat": {
                "id": 12345,
                "first_name": "Тестовый",
                "last_name": "Пользователь",
                "username": "test_user",
                "type": "private"
            },
            "date": int(time.time()),
            "text": "/ping",
            "entities": [
                {
                    "offset": 0,
                    "length": 5,
                    "type": "bot_command"
                }
            ]
        }
    }
    
    try:
        # Отправляем POST-запрос на вебхук
        response = requests.post(WEBHOOK_URL, json=test_update, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Вебхук успешно принял тестовое сообщение. Статус: {response.status_code}")
            logger.info(f"Ответ: {response.text[:100]}...")
            return True
        else:
            logger.error(f"❌ Вебхук вернул ошибку. Статус: {response.status_code}")
            logger.error(f"Ответ: {response.text[:200]}...")
            return False
            
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при тестировании вебхука: {e}")
        return False

def run_setup():
    """Запускает полную настройку проекта на Render."""
    logger.info("=== ЗАПУСК НАСТРОЙКИ ПРОЕКТА НА RENDER ===")
    
    # 1. Проверяем соединение с базой данных
    if not check_database_connection():
        logger.error("❌ Критическая ошибка: не удалось подключиться к базе данных. Остановка настройки.")
        return False
    
    # 2. Создаем таблицы, если они не существуют
    if not create_tables_if_not_exist():
        logger.warning("⚠️ Не удалось создать все необходимые таблицы. Продолжаем настройку с ограниченной функциональностью.")
    
    # 3. Проверяем доступность API Telegram
    if not check_telegram_api():
        logger.error("❌ Критическая ошибка: не удалось подключиться к API Telegram. Остановка настройки.")
        return False
    
    # 4. Проверяем текущий статус вебхука
    webhook_info = check_webhook_status()
    
    # 5. Устанавливаем или обновляем вебхук, если необходимо
    if not webhook_info or not webhook_info.get('url') or (WEBHOOK_URL and webhook_info.get('url') != WEBHOOK_URL):
        logger.info("Требуется обновление вебхука.")
        if not set_webhook():
            logger.error("❌ Не удалось установить вебхук. Проверьте конфигурацию.")
            return False
    else:
        logger.info("✅ Вебхук уже настроен правильно.")
    
    # 6. Проверяем вебхук после установки
    time.sleep(2)  # Даем время на применение изменений
    check_webhook_status()
    
    # 7. Тестируем вебхук путем отправки тестового сообщения
    if WEBHOOK_URL:
        test_webhook_with_message()
    
    logger.info("=== НАСТРОЙКА ПРОЕКТА ЗАВЕРШЕНА ===")
    return True

if __name__ == "__main__":
    success = run_setup()
    if success:
        logger.info("✅ Настройка проекта завершена успешно!")
        sys.exit(0)
    else:
        logger.error("❌ При настройке проекта возникли ошибки.")
        sys.exit(1) 