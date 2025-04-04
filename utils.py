import datetime
import pytz

# Московское время
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_current_moscow_time():
    """Получить текущее московское время."""
    return datetime.datetime.now(MOSCOW_TZ)

def get_current_date():
    """Получить текущую дату в московском часовом поясе."""
    return get_current_moscow_time().date()

def get_weekday():
    """Получить текущий день недели (0-6, где 0 - понедельник)."""
    return get_current_moscow_time().weekday()

def parse_date(date_str):
    """Преобразовать строку с датой в объект datetime."""
    try:
        # Формат: DD.MM.YYYY
        date_parts = date_str.strip().split('.')
        if len(date_parts) == 3:
            day, month, year = map(int, date_parts)
            return datetime.datetime(year, month, day, tzinfo=MOSCOW_TZ)
        return None
    except (ValueError, IndexError):
        return None

def format_date(date):
    """Форматировать дату в виде строки DD.MM.YYYY."""
    if isinstance(date, datetime.datetime):
        return date.strftime('%d.%m.%Y')
    return str(date) 