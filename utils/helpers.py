"""
Вспомогательные функции для работы с датой и временем.
"""
import logging
import re
from datetime import datetime
import pytz

import config

logger = logging.getLogger(__name__)


def get_current_moscow_time() -> datetime:
    """
    Возвращает текущее время в московском часовом поясе.
    
    Returns:
        datetime: Текущее время в Москве
    """
    return datetime.now(pytz.timezone('Europe/Moscow'))


def get_weekday() -> int:
    """
    Возвращает текущий день недели (0 - понедельник, 6 - воскресенье).
    
    Returns:
        int: Номер дня недели
    """
    # Получаем день недели (где понедельник - 0, воскресенье - 6)
    return get_current_moscow_time().weekday()


def parse_date(date_string: str) -> datetime:
    """
    Преобразует строку с датой в формате ДД.ММ.ГГГГ в объект datetime.
    
    Args:
        date_string: Строка с датой в формате ДД.ММ.ГГГГ
    
    Returns:
        datetime: Дата в формате datetime или None, если строка имеет неверный формат
    """
    try:
        # Пытаемся распарсить дату в формате ДД.ММ.ГГГГ
        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_string):
            return datetime.strptime(date_string, '%d.%m.%Y')
        # Пытаемся распарсить дату в формате ГГГГ-ММ-ДД
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_string):
            return datetime.strptime(date_string, '%Y-%m-%d')
        else:
            logger.warning(f"Неверный формат даты: {date_string}")
            return None
    except ValueError as e:
        logger.warning(f"Ошибка при парсинге даты {date_string}: {e}")
        return None


def format_date(date: datetime) -> str:
    """
    Форматирует объект datetime в строку формата DD.MM.YYYY.
    
    Args:
        date: Объект datetime
        
    Returns:
        str: Дата в формате DD.MM.YYYY
    """
    if date is None:
        return ""
    
    try:
        return date.strftime("%d.%m.%Y")
    
    except Exception as e:
        logger.error(f"Ошибка при форматировании даты {date}: {e}")
        return ""


def is_valid_date_format(date_str: str) -> bool:
    """
    Проверяет, соответствует ли строка формату даты DD.MM.YYYY.
    
    Args:
        date_str: Строка с датой
        
    Returns:
        bool: True, если формат правильный, иначе False
    """
    # Проверка на соответствие формату DD.MM.YYYY
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_str):
        return False
    
    try:
        # Проверка на корректность даты
        day, month, year = map(int, date_str.split('.'))
        datetime(year=year, month=month, day=day)
        return True
    
    except ValueError:
        return False


def get_date_string(date: datetime) -> str:
    """
    Возвращает дату в формате ДД.ММ.ГГГГ.
    
    Args:
        date: Объект datetime
    
    Returns:
        str: Дата в формате ДД.ММ.ГГГГ
    """
    if not date:
        return "Не указано"
    return date.strftime('%d.%m.%Y')


def get_current_weekday() -> int:
    """
    Возвращает текущий день недели (0-6, где 0 - понедельник).
    
    Returns:
        int: День недели (0-6)
    """
    return datetime.now().weekday() 