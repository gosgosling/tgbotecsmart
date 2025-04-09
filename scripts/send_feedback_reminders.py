#!/usr/bin/env python
"""
Скрипт для отправки запросов на обратную связь пользователям.
Запускается по расписанию для отправки уведомлений в конце дня занятий.
"""
import os
import sys
import logging
from datetime import datetime
import asyncio
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder

# Добавляем путь к корню проекта для корректного импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_active_users_by_day
from handlers import send_feedback_request
from config import Config
from utils.helpers import get_current_weekday

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/reminders.log", encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

async def send_reminders():
    """
    Отправляет запросы на обратную связь активным пользователям для текущего дня недели.
    """
    # Загружаем переменные окружения
    load_dotenv()
    
    # Проверяем наличие токена
    if not Config.TELEGRAM_TOKEN:
        logger.error("Не указан токен Telegram в переменных окружения")
        return False
    
    # Получаем текущий день недели
    current_day = get_current_weekday()
    logger.info(f"Текущий день недели: {current_day}")
    
    # Получаем активных пользователей для текущего дня
    users = get_active_users_by_day(current_day)
    
    if not users:
        logger.info(f"Нет активных пользователей для дня недели {current_day}")
        return True
    
    logger.info(f"Найдено {len(users)} активных пользователей для дня недели {current_day}")
    
    # Создаем экземпляр бота
    application = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()
    
    # Отправляем запросы на обратную связь
    success_count = 0
    failure_count = 0
    
    for user in users:
        # Отправляем запрос пользователю
        if await send_feedback_request(application, user.user_id):
            success_count += 1
        else:
            failure_count += 1
    
    logger.info(f"Отправлено запросов: {success_count} успешно, {failure_count} с ошибкой")
    
    return True

if __name__ == "__main__":
    logger.info("Запуск скрипта отправки запросов на обратную связь")
    asyncio.run(send_reminders()) 