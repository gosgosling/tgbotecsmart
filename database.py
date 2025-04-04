import os
from datetime import datetime, time
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///feedback_bot.db')
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
Base.metadata.create_all(engine)

# Инициализация расписания по умолчанию
def init_schedule():
    session = Session()
    
    # Проверяем, есть ли уже расписание
    if session.query(Schedule).count() == 0:
        # Расписание для будних дней (Пн-Пт, 18:00)
        for day in range(0, 5):  # 0-4 (Пн-Пт)
            session.add(Schedule(group_type='weekday', day_of_week=day, end_time=time(18, 0)))
        
        # Расписание для выходных (Сб, 14:00)
        session.add(Schedule(group_type='weekend', day_of_week=5, end_time=time(14, 0)))  # 5 - Суббота
        
        session.commit()
    
    session.close()


def get_session():
    return Session() 