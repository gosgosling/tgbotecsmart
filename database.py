import os
import logging
import sys
from datetime import datetime, time
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Time, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
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

# Создание базовых объектов SQLAlchemy
Base = declarative_base()

# Создание движка SQLAlchemy
try:
    logger.info(f"Создание движка SQLAlchemy для подключения к БД: {DATABASE_URL.split('://')[0]}")
    engine = create_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(bind=engine)
    logger.info("Движок SQLAlchemy создан успешно")
except Exception as e:
    logger.error(f"Критическая ошибка при создании движка SQLAlchemy: {e}")
    # Даже если произошла ошибка, мы определим Session, чтобы избежать ошибок импорта
    Session = sessionmaker()

# Определяем глобальную переменную для отслеживания статуса базы данных
DB_READY = False

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
        def count_schedules(s):
            return s.query(Schedule).count()
        
        schedule_count = safe_execute_query(session, count_schedules)
        if schedule_count is None:  # Ошибка при выполнении запроса
            logger.error("Ошибка при подсчете записей в расписании")
            session.close()
            return False
            
        logger.info(f"Найдено записей в расписании: {schedule_count}")
        
        if schedule_count == 0:
            # Расписание для будних дней (Пн-Пт, 18:00)
            for day in range(0, 5):  # 0-4 (Пн-Пт)
                session.add(Schedule(group_type='weekday', day_of_week=day, end_time=time(18, 0)))
            
            # Расписание для выходных (Сб, 14:00)
            session.add(Schedule(group_type='weekend', day_of_week=5, end_time=time(14, 0)))  # 5 - Суббота
            
            try:
                session.commit()
                logger.info("Расписание успешно инициализировано")
            except Exception as e:
                logger.error(f"Ошибка при сохранении расписания: {e}")
                session.rollback()
                return False
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


def check_database_connection():
    """Проверяет соединение с базой данных и логирует его статус."""
    logger.info("Проверка соединения с базой данных...")
    try:
        # Получаем сессию через прямое создание, чтобы избежать рекурсии
        session = Session()
        
        # Пробуем выполнить простой запрос
        result = session.execute(text("SELECT 1")).scalar()
        
        # Обязательно закрываем сессию после использования
        session.close()
        
        if result == 1:
            logger.info("✅ Соединение с базой данных успешно установлено!")
            # Используем глобальную переменную без объявления global внутри функции
            DB_READY = True
            return True
        else:
            logger.error("❌ Соединение с базой данных установлено, но проверочный запрос вернул неправильный результат.")
            DB_READY = False
            return False
    
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке соединения с базой данных: {e}")
        import traceback
        logger.error(traceback.format_exc())
        DB_READY = False
        return False


def get_session():
    """Получить сессию базы данных."""
    try:
        session = Session()
        # Проверяем работоспособность сессии с правильным синтаксисом для SQLAlchemy 2.0
        session.execute(text("SELECT 1"))
        return session
    except Exception as e:
        logger.error(f"Ошибка при создании сессии: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Если ошибка связана с базой данных, вернем None, иначе пробросим исключение
        raise


# Добавим функцию для безопасного выполнения запросов
def safe_execute_query(session, query_func):
    """Безопасно выполняет запрос к базе данных с обработкой ошибок."""
    try:
        return query_func(session)
    except Exception as e:
        logger.error(f"Ошибка при выполнении запроса: {e}")
        import traceback
        logger.error(traceback.format_exc())
        session.rollback()
        return None


# При импорте модуля, проверяем подключение к БД и создаем таблицы
# Инициализируем DB_READY, не используя функцию, которая пытается его изменить
try:
    # Проверка соединения с базой данных
    session = Session()
    result = session.execute(text("SELECT 1")).scalar()
    session.close()
    
    # Создание таблиц
    DB_READY = create_tables()
    
    logger.info(f"Статус готовности базы данных: {'готова' if DB_READY else 'не готова'}")
except Exception as e:
    logger.error(f"Ошибка при инициализации базы данных: {e}")
    DB_READY = False


def add_manager(chat_id, username=None, first_name=None, last_name=None):
    """Добавляет нового менеджера в базу данных."""
    try:
        session = get_session()
        
        # Проверяем, существует ли уже менеджер с таким chat_id
        existing_manager = session.query(User).filter(User.chat_id == chat_id).first()
        
        if existing_manager:
            # Если менеджер уже существует, обновляем его данные
            existing_manager.username = username
            existing_manager.first_name = first_name
            existing_manager.last_name = last_name
            existing_manager.is_active = True
            session.commit()
            logger.info(f"Обновлены данные менеджера с chat_id={chat_id}")
            session.close()
            return True
        
        # Создаем нового менеджера
        new_manager = User(
            chat_id=chat_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_active=True
        )
        
        session.add(new_manager)
        session.commit()
        logger.info(f"Добавлен новый менеджер с chat_id={chat_id}")
        session.close()
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении менеджера: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            session.rollback()
            session.close()
        except:
            pass
        return False


def get_manager_by_telegram_id(chat_id):
    """Получает менеджера по telegram ID (chat_id)."""
    try:
        session = get_session()
        manager = session.query(User).filter(User.chat_id == chat_id).first()
        session.close()
        return manager
    except Exception as e:
        logger.error(f"Ошибка при получении менеджера по chat_id={chat_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            session.close()
        except:
            pass
        return None


def get_all_managers():
    """Получает список всех активных менеджеров."""
    try:
        session = get_session()
        managers = session.query(User).filter(User.is_active == True).all()
        session.close()
        return managers
    except Exception as e:
        logger.error(f"Ошибка при получении списка менеджеров: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            session.close()
        except:
            pass
        return []


def add_feedback_request(chat_id, message):
    """Сохраняет запрос на обратную связь в базе данных.
    
    В текущей реализации просто возвращает True, поскольку нет таблицы для хранения запросов.
    Можно расширить в будущем, добавив соответствующую таблицу.
    """
    try:
        # Проверяем, существует ли пользователь
        session = get_session()
        user = session.query(User).filter(User.chat_id == chat_id).first()
        
        if not user:
            logger.warning(f"Попытка добавить запрос на обратную связь для несуществующего пользователя: {chat_id}")
            session.close()
            return False
        
        # Здесь можно было бы сохранить запрос в отдельной таблице
        # В текущей реализации просто логируем событие
        logger.info(f"Получен запрос на обратную связь от пользователя {chat_id}: {message[:50]}...")
        
        session.close()
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении запроса на обратную связь: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            session.close()
        except:
            pass
        return False


def check_and_schedule_feedback_requests():
    """Проверяет расписание и назначает отправку запросов на обратную связь.
    
    Эта функция вызывается планировщиком каждые 10 минут.
    Она проверяет, есть ли группы, для которых нужно отправить запрос на обратную связь.
    """
    try:
        logger.info("Выполняется проверка расписания для отправки запросов на обратную связь")
        
        # Получаем текущее время в Москве
        from utils import get_current_moscow_time, get_weekday
        now = get_current_moscow_time()
        current_day = get_weekday()  # 0-6 (Пн-Вс)
        current_time = now.time()
        
        logger.info(f"Текущее время (Москва): {now}, день недели: {current_day}, время: {current_time}")
        
        # Получаем расписание для текущего дня
        session = get_session()
        
        def get_schedules_for_today(s):
            return s.query(Schedule).filter(Schedule.day_of_week == current_day).all()
        
        schedules = safe_execute_query(session, get_schedules_for_today)
        
        if not schedules:
            logger.info(f"Нет расписаний для дня недели {current_day}")
            session.close()
            return True  # Успешное выполнение, просто нет расписаний
        
        logger.info(f"Найдено {len(schedules)} расписаний для дня недели {current_day}")
        
        # Список пользователей, которым нужно отправить запросы
        users_to_notify = []
        
        # Проверяем расписания
        for schedule in schedules:
            end_time = schedule.end_time
            group_type = schedule.group_type
            
            # Если текущее время близко к времени окончания занятия (в пределах 10 минут после)
            time_diff = (datetime.combine(now.date(), current_time) - 
                        datetime.combine(now.date(), end_time)).total_seconds() / 60
            
            if 0 <= time_diff <= 10:
                logger.info(f"Время для отправки запросов на обратную связь группе {group_type}")
                
                # Получаем пользователей этой группы
                def get_users_in_group(s):
                    return s.query(User).filter(
                        User.group_type == group_type,
                        User.is_active == True
                    ).all()
                
                users = safe_execute_query(session, get_users_in_group)
                
                if not users:
                    logger.info(f"Нет активных пользователей в группе {group_type}")
                    continue
                
                logger.info(f"Найдено {len(users)} пользователей в группе {group_type}")
                
                # Добавляем в список пользователей для уведомления
                for user in users:
                    users_to_notify.append(user.chat_id)
                    logger.info(f"Запланирована отправка запроса на обратную связь пользователю {user.chat_id}")
        
        session.close()
        logger.info(f"Проверка расписания завершена. Найдено {len(users_to_notify)} пользователей для уведомления.")
        
        # Возвращаем список пользователей, которым нужно отправить запросы
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при проверке расписания: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            session.close()
        except:
            pass
        
        # Возвращаем информацию о том, что произошла ошибка
        return False 