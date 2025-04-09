"""
Модуль для работы с базой данных.
Определяет модели данных и функции для инициализации базы.
"""
import os
import logging
import sys
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, text, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import traceback

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

logger.info(f"Используется база данных: {DATABASE_URL.split('://')[0]}")

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем движок SQLAlchemy
try:
    logger.info(f"Создание движка SQLAlchemy для подключения к БД: {DATABASE_URL.split('://')[0]}")
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Движок SQLAlchemy создан успешно")
except Exception as e:
    logger.error(f"Критическая ошибка при создании движка SQLAlchemy: {e}")
    # Даже если произошла ошибка, мы определим Session, чтобы избежать ошибок импорта
    SessionLocal = sessionmaker()

# Определение таблиц
class User(Base):
    """Пользователь бота."""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    group_type = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<User(id={self.id}, chat_id={self.chat_id}, username={self.username})>"


class Feedback(Base):
    """
    Модель для хранения обратной связи от пользователей.
    """
    __tablename__ = 'feedback'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Feedback(id={self.id}, user_id={self.user_id}, created_at={self.created_at})>"


def get_engine():
    """
    Создает и возвращает объект SQLAlchemy Engine.
    """
    logger.info(f"Подключение к базе данных: {DATABASE_URL.split('://')[0]}")
    return create_engine(DATABASE_URL)


def init_db():
    """
    Инициализирует базу данных: создает таблицы и настраивает сессию.
    """
    try:
        # Создаем движок базы данных
        engine = get_engine()
        
        # Создаем таблицы, если они не существуют
        Base.metadata.create_all(engine)
        
        # Настраиваем фабрику сессий
        SessionLocal.configure(bind=engine)
        
        logger.info("База данных инициализирована успешно")
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        return False


def check_user_exists(user_id: int) -> bool:
    """
    Проверяет, существует ли пользователь с указанным ID в базе данных.
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        bool: True, если пользователь существует, иначе False
    """
    try:
        session = SessionLocal()
        
        # Проверяем наличие пользователя
        result = session.execute(
            text("SELECT 1 FROM users WHERE chat_id = :user_id"),
            {"user_id": user_id}
        ).scalar() is not None

        logger.debug(f"Проверка существования пользователя {user_id}: {result}")
        
        return result
    
    except Exception as e:
        logger.error(f"Ошибка при проверке существования пользователя {user_id}: {e}")
        return False
    
    finally:
        session.close()


def create_new_user(user_id: int, username: str, first_name: str, last_name: str, 
                    group: str, group_day: int, start_date: datetime) -> bool:
    """
    Создает нового пользователя в базе данных.
    
    Args:
        user_id: ID пользователя в Telegram
        username: Имя пользователя в Telegram
        first_name: Имя пользователя
        last_name: Фамилия пользователя
        group: Группа пользователя
        group_day: День недели занятий (0-6)
        start_date: Дата начала занятий
        
    Returns:
        bool: True, если пользователь успешно создан, иначе False
    """
    try:
        session = SessionLocal()
        
        # Обработка параметров для избежания ошибок
        if isinstance(start_date, str):
            # Если дата пришла в виде строки, преобразуем её в объект datetime
            try:
                if "." in start_date:  # Формат ДД.ММ.ГГГГ
                    start_date = datetime.strptime(start_date, '%d.%m.%Y')
                else:  # Другие возможные форматы
                    start_date = datetime.strptime(start_date.split('.')[0], '%Y-%m-%d %H:%M:%S')
            except (ValueError, IndexError):
                # Если не удалось, используем текущую дату
                logger.warning(f"Невозможно преобразовать строку даты '{start_date}' в формат datetime. Используется текущая дата.")
                start_date = datetime.now()
                
        # Проверка на None значения и установка дефолтных значений
        if username is None:
            username = ""
        if first_name is None:
            first_name = "Пользователь"
        if last_name is None:
            last_name = ""
            
        # Детальное логирование параметров
        logger.info(f"Создание пользователя с параметрами: user_id={user_id}, username={username}, "
                    f"first_name={first_name}, last_name={last_name}, group={group}, "
                    f"start_date={start_date}")
        
        # Создаем нового пользователя
        new_user = User(
            chat_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            group_type=group,
            start_date=start_date
        )
        
        session.add(new_user)
        session.commit()
        
        logger.info(f"Создан новый пользователь: {user_id}, группа: {group}")
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при создании пользователя {user_id}: {e}")
        session.rollback()
        return False
    
    finally:
        session.close()


def update_user_status(user_id: int, is_active: bool) -> bool:
    """
    Обновляет статус активности пользователя.
    
    Args:
        user_id: ID пользователя в Telegram
        is_active: Новый статус активности
        
    Returns:
        bool: True, если статус успешно обновлен, иначе False
    """
    try:
        session = SessionLocal()
        
        # Обновляем статус активности
        result = session.execute(
            text("UPDATE users SET is_active = :is_active WHERE chat_id = :user_id"),
            {"is_active": is_active, "user_id": user_id}
        )
        
        session.commit()
        
        if result.rowcount > 0:
            logger.info(f"Статус пользователя {user_id} обновлен на: {is_active}")
            return True
        else:
            logger.warning(f"Пользователь {user_id} не найден при обновлении статуса")
            return False
    
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса пользователя {user_id}: {e}")
        session.rollback()
        return False
    
    finally:
        session.close()


def save_feedback(user_id: int, message: str) -> bool:
    """
    Сохраняет обратную связь от пользователя в базе данных.
    
    Args:
        user_id: ID пользователя в Telegram
        message: Текст обратной связи
        
    Returns:
        bool: True, если обратная связь успешно сохранена, иначе False
    """
    try:
        session = SessionLocal()
        
        # Создаем новую запись обратной связи
        new_feedback = Feedback(
            user_id=user_id,
            message=message
        )
        
        session.add(new_feedback)
        session.commit()
        
        logger.info(f"Сохранена обратная связь от пользователя {user_id}")
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при сохранении обратной связи от пользователя {user_id}: {e}")
        session.rollback()
        return False
    
    finally:
        session.close()


def get_active_users_by_day(day: int) -> list:
    """
    Возвращает список активных пользователей для указанного дня недели.
    
    Args:
        day: День недели (0-6)
        
    Returns:
        list: Список пользователей
    """
    try:
        session = SessionLocal()
        
        # Получаем пользователей для указанного дня недели
        users = session.query(User).filter(
            User.is_active == True,
            User.group_day == day
        ).all()
        
        return users
    
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей для дня {day}: {e}")
        return []
    
    finally:
        session.close()


def check_database_connection() -> bool:
    """
    Проверяет соединение с базой данных.
    
    Returns:
        bool: True, если соединение установлено успешно, иначе False
    """
    try:
        session = SessionLocal()
        # Пытаемся выполнить простой запрос
        result = session.execute(text("SELECT 1")).scalar()
        logger.info("✅ Соединение с базой данных установлено успешно")
        return True
    
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке соединения с базой данных: {e}")
        logger.error(f"Traceback (most recent call last):\n{traceback.format_exc()}")
        return False
    
    finally:
        session.close()

# Если модуль запущен напрямую, инициализируем базу данных
if __name__ == "__main__":
    logger.info("Запуск инициализации базы данных")
    if init_db():
        logger.info("База данных успешно инициализирована")
        
        # Проверка наличия таблиц
        try:
            # Создаем инспектор для проверки схемы базы данных
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            logger.info(f"Созданные таблицы: {', '.join(tables)}")
            
            # Проверяем структуру таблиц
            for table in tables:
                columns = inspector.get_columns(table)
                column_names = [column['name'] for column in columns]
                logger.info(f"Структура таблицы '{table}': {', '.join(column_names)}")
        except Exception as e:
            logger.error(f"Ошибка при проверке структуры базы данных: {e}")
            
        logger.info("Проверка базы данных завершена. Бот готов к запуску.") 