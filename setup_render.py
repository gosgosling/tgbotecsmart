#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import logging
import requests
import time
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
logger.info("Переменные окружения загружены")

# Получение данных из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
DATABASE_URL = os.getenv('DATABASE_URL')
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')

# Проверяем обязательные переменные
if not TELEGRAM_TOKEN:
    logger.error("Ошибка: TELEGRAM_TOKEN не найден в переменных окружения")
    sys.exit(1)

if not DATABASE_URL:
    logger.error("Ошибка: DATABASE_URL не найден в переменных окружения")
    sys.exit(1)

# Логируем основные переменные
logger.info(f"Токен: {TELEGRAM_TOKEN[:5]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"URL базы данных: {DATABASE_URL.split('://', 1)[0]}://****")
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
                    error_time = datetime.fromtimestamp(last_error_date).strftime('%Y-%m-%d %H:%M:%S')
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

def run_setup():
    """Запускает полную настройку проекта на Render."""
    logger.info("=== ЗАПУСК НАСТРОЙКИ ПРОЕКТА НА RENDER ===")
    
    # 1. Проверяем соединение с базой данных
    if not check_database_connection():
        logger.error("❌ Критическая ошибка: не удалось подключиться к базе данных. Остановка настройки.")
        return False
    
    # 2. Проверяем доступность API Telegram
    if not check_telegram_api():
        logger.error("❌ Критическая ошибка: не удалось подключиться к API Telegram. Остановка настройки.")
        return False
    
    # 3. Проверяем текущий статус вебхука
    webhook_info = check_webhook_status()
    
    # 4. Устанавливаем или обновляем вебхук, если необходимо
    if not webhook_info or not webhook_info.get('url') or (WEBHOOK_URL and webhook_info.get('url') != WEBHOOK_URL):
        logger.info("Требуется обновление вебхука.")
        if not set_webhook():
            logger.error("❌ Не удалось установить вебхук. Проверьте конфигурацию.")
            return False
    else:
        logger.info("✅ Вебхук уже настроен правильно.")
    
    # 5. Проверяем вебхук после установки
    time.sleep(2)  # Даем время на применение изменений
    check_webhook_status()
    
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