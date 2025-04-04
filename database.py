import os
import logging
from datetime import datetime, time
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Настройка логирования
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение URL базы данных
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///feedback_bot.db')

# Проверка на PostgreSQL URL от Render (который начинается с postgres://)
# SQLAlchemy 2.0+ требует postgresql:// вместо postgres://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    logger.info("URL базы данных преобразован из postgres:// в postgresql://")

logger.info(f"Используется база данных: {DATABASE_URL.split('://')[0]}")

# Создание движка SQLAlchemy
try:
    logger.info(f"Создание движка SQLAlchemy для подключения к БД: {DATABASE_URL.split('://')[0]}")
    engine = create_engine(DATABASE_URL, echo=False)
    Base = declarative_base()
    Session = sessionmaker(bind=engine)
    logger.info("Движок SQLAlchemy создан успешно")
except Exception as e:
    logger.error(f"Критическая ошибка при создании движка SQLAlchemy: {e}")
    # Не будем здесь применять sys.exit, т.к. это приведет к падению всего приложения
    # Вместо этого обработаем ошибки в функциях ниже


class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    group_type = Column(String, nullable=True)  # 'weekday' или 'weekend'
    start_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"User(id={self.id}, chat_id={self.chat_id}, username={self.username})"


class Schedule(Base):
    __tablename__ = 'schedules'
    
    id = Column(Integer, primary_key=True)
    group_type = Column(String, nullable=False)  # 'weekday' или 'weekend'
    day_of_week = Column(Integer, nullable=False)  # 0-6 (понедельник-воскресенье)
    end_time = Column(Time, nullable=False)
    
    def __repr__(self):
        return f"Schedule(id={self.id}, group_type={self.group_type}, day={self.day_of_week}, end_time={self.end_time})"


# Создание таблиц в базе данных
def create_tables():
    logger.info("Создание таблиц в базе данных...")
    try:
        Base.metadata.create_all(engine)
        logger.info("Таблицы успешно созданы")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


# Инициализация расписания по умолчанию
def init_schedule():
    """Инициализирует расписание по умолчанию и возвращает True в случае успеха."""
    logger.info("Инициализация расписания...")
    
    # Проверяем соединение с базой данных
    if not check_database_connection():
        logger.error("Не удалось инициализировать расписание: база данных недоступна")
        return False
    
    try:
        session = Session()
    except Exception as e:
        logger.error(f"Не удалось создать сессию для инициализации расписания: {e}")
        return False
    
    try:
        # Проверяем, есть ли уже расписание
        schedule_count = session.query(Schedule).count()
        logger.info(f"Найдено записей в расписании: {schedule_count}")
        
        if schedule_count == 0:
            # Расписание для будних дней (Пн-Пт, 18:00)
            for day in range(0, 5):  # 0-4 (Пн-Пт)
                session.add(Schedule(group_type='weekday', day_of_week=day, end_time=time(18, 0)))
            
            # Расписание для выходных (Сб, 14:00)
            session.add(Schedule(group_type='weekend', day_of_week=5, end_time=time(14, 0)))  # 5 - Суббота
            
            session.commit()
            logger.info("Расписание успешно инициализировано")
        else:
            logger.info("Расписание уже существует, инициализация не требуется")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при инициализации расписания: {e}")
        import traceback
        logger.error(traceback.format_exc())
        session.rollback()
        return False
    finally:
        session.close()


# Добавим функцию для проверки соединения с базой данных
def check_database_connection():
    """Проверяет соединение с базой данных."""
    logger.info("Проверка соединения с базой данных...")
    try:
        # Простой запрос для проверки соединения
        connection = engine.connect()
        connection.close()
        logger.info("Соединение с базой данных успешно установлено")
        return True
    except Exception as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def get_session():
    """Получить сессию базы данных."""
    try:
        session = Session()
        # Проверяем работоспособность сессии
        session.execute("SELECT 1")
        return session
    except Exception as e:
        logger.error(f"Ошибка при создании сессии: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Если ошибка связана с базой данных, вернем None, иначе пробросим исключение
        raise


# При импорте модуля, проверяем подключение к БД и создаем таблицы
DB_READY = check_database_connection() and create_tables() 
# Флаг DB_READY будем использовать в основном коде для проверки готовности БД 