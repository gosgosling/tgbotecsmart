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
engine = create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)


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
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {e}")
        raise


# Инициализация расписания по умолчанию
def init_schedule():
    logger.info("Инициализация расписания...")
    session = Session()
    
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
    except Exception as e:
        logger.error(f"Ошибка при инициализации расписания: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def get_session():
    """Получить сессию базы данных."""
    return Session()


# При импорте модуля, создаем таблицы
create_tables() 