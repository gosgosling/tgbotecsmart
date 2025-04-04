#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import logging
import requests
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения из .env
load_dotenv()

# Получение токена из окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    logger.error("Ошибка: токен Telegram не найден в переменных окружения.")
    sys.exit(1)

# Получение URL веб-хука из окружения
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Получение ID чата менеджера из окружения
MANAGER_CHAT_ID = os.getenv('MANAGER_CHAT_ID')

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
            print(f"\n✅ API Telegram доступен")
            print(f"👤 Имя бота: {bot_info.get('first_name')}")
            print(f"👤 Имя пользователя: @{bot_info.get('username')}")
            print(f"👤 ID бота: {bot_info.get('id')}")
            print(f"👤 Поддержка Webhook: {bot_info.get('can_join_groups', 'Неизвестно')}")
            return True
        else:
            print(f"\n❌ Ошибка при проверке API Telegram: {data.get('description', 'Неизвестная ошибка')}")
            return False
            
    except requests.RequestException as e:
        print(f"\n❌ Ошибка при подключении к API Telegram: {e}")
        logger.error(f"Ошибка при подключении к API Telegram: {e}")
        return False

def get_webhook_info():
    """Получает и отображает информацию о текущем вебхуке."""
    print("\n📊 Проверка текущего статуса вебхука...")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            webhook_info = data.get("result", {})
            
            current_url = webhook_info.get('url', 'Не установлен')
            
            print(f"\n=== СТАТУС ВЕБХУКА ===")
            print(f"🔗 URL: {current_url}")
            print(f"✅ Вебхук активен: {'Да' if current_url else 'Нет'}")
            
            if current_url and WEBHOOK_URL and current_url != WEBHOOK_URL:
                print(f"⚠️ ВНИМАНИЕ: Текущий URL вебхука ({current_url}) не соответствует URL в .env файле ({WEBHOOK_URL})")
            
            if webhook_info.get('last_error_message'):
                print(f"❌ Последняя ошибка: {webhook_info.get('last_error_message')}")
                
                # Конвертация UNIX timestamp в читаемую дату
                last_error_date = webhook_info.get('last_error_date')
                if last_error_date:
                    error_time = datetime.fromtimestamp(last_error_date).strftime('%Y-%m-%d %H:%M:%S')
                    print(f"⏰ Время ошибки: {error_time}")
            else:
                print("✅ Ошибок вебхука не обнаружено")
                
            print(f"📝 Ожидающие обновления: {webhook_info.get('pending_update_count', 0)}")
            print(f"🔄 Максимальные соединения: {webhook_info.get('max_connections', 'Не указано')}")
            
            # Информация о разрешенных IP
            allowed_updates = webhook_info.get('allowed_updates', [])
            if allowed_updates:
                print(f"📋 Разрешенные обновления: {', '.join(allowed_updates)}")
            else:
                print("📋 Разрешенные обновления: Все типы")
                
            return webhook_info
        else:
            print(f"\n❌ Ошибка при получении информации о вебхуке: {data.get('description', 'Неизвестная ошибка')}")
            return None
            
    except requests.RequestException as e:
        print(f"\n❌ Ошибка при подключении к API Telegram: {e}")
        logger.error(f"Ошибка при подключении к API Telegram: {e}")
        return None

def delete_webhook():
    """Удаляет текущий вебхук."""
    confirmation = input("\n⚠️ Вы уверены, что хотите удалить вебхук? (да/нет): ").lower()
    if confirmation != "да":
        print("Операция отменена.")
        return False
    
    print("\n🗑 Удаление вебхука...")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            print("✅ Вебхук успешно удален!")
            return True
        else:
            print(f"❌ Ошибка при удалении вебхука: {data.get('description', 'Неизвестная ошибка')}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Ошибка при подключении к API Telegram: {e}")
        logger.error(f"Ошибка при подключении к API Telegram: {e}")
        return False

def check_url_availability(url):
    """Проверяет доступность указанного URL."""
    if not url:
        print("\n❌ URL не указан. Невозможно проверить доступность.")
        return False
    
    print(f"\n🔍 Проверка доступности URL: {url}")
    
    try:
        # Используем увеличенный timeout для внешних сервисов, особенно для Render
        response = requests.get(url, timeout=30)
        
        print(f"📊 Статус код: {response.status_code}")
        print(f"📝 Содержимое ответа: {response.text[:100]}..." if len(response.text) > 100 else f"📝 Содержимое ответа: {response.text}")
        
        if response.status_code < 400:
            print("✅ URL доступен!")
            return True
        else:
            print(f"❌ URL недоступен (статус код: {response.status_code})")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Ошибка при подключении к URL: {e}")
        logger.error(f"Ошибка при подключении к URL: {e}")
        return False

def check_render_service():
    """Проверяет доступность сервиса Render, если URL относится к Render."""
    if not WEBHOOK_URL:
        print("\n❌ URL вебхука не установлен в переменных окружения.")
        return False
    
    if "onrender.com" not in WEBHOOK_URL:
        print("\n⚠️ URL вебхука не является сервисом Render. Пропускаем проверку.")
        return True
    
    print(f"\n🔍 Проверка доступности сервиса Render...")
    
    # Извлекаем базовый URL сервиса на Render
    base_url = '/'.join(WEBHOOK_URL.split('/')[:3])
    ping_url = f"{base_url}/ping"
    
    print(f"🔗 Проверка пинг-эндпоинта: {ping_url}")
    
    for attempt in range(1, 4):
        try:
            print(f"Попытка {attempt}...")
            response = requests.get(ping_url, timeout=30)
            
            print(f"📊 Статус код: {response.status_code}")
            print(f"📝 Содержимое ответа: {response.text[:100]}..." if len(response.text) > 100 else f"📝 Содержимое ответа: {response.text}")
            
            if response.status_code < 400:
                print("✅ Сервис Render доступен!")
                
                # Проверяем статус бота, если это наш собственный эндпоинт /ping
                try:
                    data = response.json()
                    if "timestamp" in data and "status" in data:
                        print(f"✅ Бот активен на Render! Статус: {data.get('status')}")
                        print(f"⏰ Время последнего отклика: {data.get('timestamp')}")
                except:
                    # Если не можем распарсить JSON, просто продолжаем
                    pass
                
                return True
            else:
                print(f"❌ Сервис Render недоступен (статус код: {response.status_code})")
                
                if attempt < 3:
                    print("⏳ Ожидание 5 секунд перед повторной попыткой...")
                    time.sleep(5)
                
        except requests.RequestException as e:
            print(f"❌ Ошибка при подключении к сервису Render: {e}")
            
            if attempt < 3:
                print("⏳ Ожидание 5 секунд перед повторной попыткой...")
                time.sleep(5)
    
    print("\n⚠️ Сервис Render может быть в спящем режиме. Это нормально для бесплатных планов.")
    print("⚠️ При первом запросе сервис может запускаться до 30 секунд.")
    
    return False

def set_webhook():
    """Устанавливает вебхук по указанному URL."""
    if not WEBHOOK_URL:
        # Если URL не указан в .env, запрашиваем у пользователя
        webhook_url = input("\n🔗 Введите URL вебхука (или нажмите Enter, чтобы использовать прежний URL): ").strip()
        if not webhook_url:
            print("❌ URL не указан. Невозможно установить вебхук.")
            return False
    else:
        webhook_url = WEBHOOK_URL
        print(f"\n🔗 Используем URL из .env файла: {webhook_url}")
    
    # Проверяем доступность URL перед установкой вебхука
    if not check_url_availability(webhook_url):
        confirmation = input("\n⚠️ URL недоступен. Продолжить установку вебхука? (да/нет): ").lower()
        if confirmation != "да":
            print("Операция отменена.")
            return False
    
    print(f"\n🔄 Установка вебхука по URL: {webhook_url}")
    
    # Параметры для установки вебхука
    params = {
        "url": webhook_url,
        "drop_pending_updates": True,
        "max_connections": 100,
        "allowed_updates": json.dumps(["message", "callback_query", "my_chat_member"])
    }
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    
    try:
        response = requests.post(url, data=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            print(f"✅ Вебхук успешно установлен по URL: {webhook_url}")
            print(f"📝 Ответ от API: {data.get('description', '')}")
            
            # Проверяем обновленную информацию о вебхуке
            time.sleep(1)  # Небольшая задержка для применения изменений
            get_webhook_info()
            
            return True
        else:
            print(f"❌ Ошибка при установке вебхука: {data.get('description', 'Неизвестная ошибка')}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Ошибка при подключении к API Telegram: {e}")
        logger.error(f"Ошибка при подключении к API Telegram: {e}")
        return False

def send_test_message():
    """Отправляет тестовое сообщение, чтобы проверить работу бота."""
    # Запрашиваем ID чата, если он не указан
    chat_id = MANAGER_CHAT_ID if MANAGER_CHAT_ID else input("\n👤 Введите ID чата для отправки тестового сообщения: ").strip()
    
    if not chat_id:
        print("❌ ID чата не указан. Невозможно отправить сообщение.")
        return False
    
    print(f"\n📝 Отправка тестового сообщения в чат с ID: {chat_id}")
    
    message_text = f"🤖 Тестовое сообщение от бота!\n⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, data=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            print("✅ Тестовое сообщение успешно отправлено!")
            return True
        else:
            print(f"❌ Ошибка при отправке сообщения: {data.get('description', 'Неизвестная ошибка')}")
            
            # Подробная диагностика ошибки
            if "chat not found" in data.get('description', '').lower():
                print("⚠️ Причина: Бот не может отправить сообщение в указанный чат. Возможно, пользователь не инициировал чат с ботом.")
                print("🔍 Решение: Пользователь должен отправить сообщение боту или добавить бота в группу.")
            
            return False
            
    except requests.RequestException as e:
        print(f"❌ Ошибка при подключении к API Telegram: {e}")
        logger.error(f"Ошибка при подключении к API Telegram: {e}")
        return False

def check_updates():
    """Получает последние обновления для бота (только в режиме Long Polling)."""
    # Проверяем статус вебхука - если активен, нельзя использовать getUpdates
    webhook_info = get_webhook_info()
    
    if webhook_info and webhook_info.get('url'):
        print("\n⚠️ Вебхук активен! Невозможно получить обновления через getUpdates.")
        print("⚠️ Сначала удалите вебхук, чтобы использовать эту функцию.")
        
        confirmation = input("\n⚠️ Хотите удалить вебхук для получения обновлений? (да/нет): ").lower()
        if confirmation != "да":
            print("Операция отменена.")
            return False
        
        if not delete_webhook():
            print("❌ Не удалось удалить вебхук. Невозможно получить обновления.")
            return False
    
    print("\n📥 Получение последних обновлений для бота...")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?limit=10&timeout=30"
    
    try:
        print("⏳ Ожидание обновлений (до 30 секунд)...")
        response = requests.get(url, timeout=60)  # Увеличенный timeout для long polling
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            updates = data.get("result", [])
            
            if not updates:
                print("📭 Обновлений не найдено. Отправьте боту сообщение и повторите проверку.")
                return True
            
            print(f"\n📋 Получено обновлений: {len(updates)}")
            
            for i, update in enumerate(updates, 1):
                print(f"\n--- Обновление {i} ---")
                print(f"🆔 ID обновления: {update.get('update_id')}")
                
                if 'message' in update:
                    message = update['message']
                    print(f"💬 Тип: Сообщение")
                    print(f"👤 От пользователя: {message.get('from', {}).get('first_name')} (ID: {message.get('from', {}).get('id')})")
                    print(f"📝 Текст: {message.get('text', '[Нет текста]')}")
                    print(f"⏰ Время: {datetime.fromtimestamp(message.get('date')).strftime('%Y-%m-%d %H:%M:%S')}")
                
                elif 'callback_query' in update:
                    callback = update['callback_query']
                    print(f"💬 Тип: Callback Query")
                    print(f"👤 От пользователя: {callback.get('from', {}).get('first_name')} (ID: {callback.get('from', {}).get('id')})")
                    print(f"📝 Данные: {callback.get('data', '[Нет данных]')}")
            
            return True
        else:
            print(f"❌ Ошибка при получении обновлений: {data.get('description', 'Неизвестная ошибка')}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Ошибка при подключении к API Telegram: {e}")
        logger.error(f"Ошибка при подключении к API Telegram: {e}")
        return False

def run_diagnostics():
    """Запускает полную диагностику бота и вебхука."""
    print("\n🔍 Запуск полной диагностики бота и вебхука...\n")
    
    # 1. Проверка доступности API Telegram
    if not check_telegram_api():
        print("❌ Критическая ошибка: API Telegram недоступен. Дальнейшая диагностика невозможна.")
        return
    
    # 2. Проверка статуса вебхука
    webhook_info = get_webhook_info()
    
    # 3. Проверка доступности Render сервиса
    check_render_service()
    
    # 4. Тестовое сообщение
    if MANAGER_CHAT_ID:
        confirm = input("\n⚠️ Хотите отправить тестовое сообщение? (да/нет): ").lower()
        if confirm == "да":
            send_test_message()
    
    # 5. Получение обновлений (если вебхук не активен)
    if webhook_info and not webhook_info.get('url'):
        confirm = input("\n⚠️ Хотите проверить последние обновления для бота? (да/нет): ").lower()
        if confirm == "да":
            check_updates()
    
    print("\n✅ Диагностика завершена!")

def main():
    """Главная функция программы."""
    parser = argparse.ArgumentParser(description='Инструмент для диагностики и настройки вебхука Telegram бота')
    
    # Определяем возможные действия
    parser.add_argument('--diagnose', action='store_true', help='Запустить полную диагностику')
    parser.add_argument('--check', action='store_true', help='Проверить текущий статус вебхука')
    parser.add_argument('--delete', action='store_true', help='Удалить текущий вебхук')
    parser.add_argument('--set', action='store_true', help='Установить вебхук')
    parser.add_argument('--test-message', action='store_true', help='Отправить тестовое сообщение')
    parser.add_argument('--updates', action='store_true', help='Проверить последние обновления')
    parser.add_argument('--render', action='store_true', help='Проверить доступность сервиса Render')
    
    # Разбор аргументов командной строки
    args = parser.parse_args()
    
    # Проверяем наличие аргументов
    has_args = any(vars(args).values())
    
    # Если нет аргументов, показываем меню
    if not has_args:
        while True:
            print("\n=== ДИАГНОСТИКА TELEGRAM БОТА ===")
            print("1. Запустить полную диагностику")
            print("2. Проверить текущий статус вебхука")
            print("3. Удалить текущий вебхук")
            print("4. Установить вебхук")
            print("5. Отправить тестовое сообщение")
            print("6. Проверить последние обновления")
            print("7. Проверить доступность сервиса Render")
            print("0. Выход")
            
            choice = input("\nВыберите действие (0-7): ")
            
            if choice == "0":
                break
            elif choice == "1":
                run_diagnostics()
            elif choice == "2":
                get_webhook_info()
            elif choice == "3":
                delete_webhook()
            elif choice == "4":
                set_webhook()
            elif choice == "5":
                send_test_message()
            elif choice == "6":
                check_updates()
            elif choice == "7":
                check_render_service()
            else:
                print("❌ Неверный выбор. Пожалуйста, попробуйте снова.")
    else:
        # Выполняем действия согласно аргументам
        if args.diagnose:
            run_diagnostics()
        if args.check:
            get_webhook_info()
        if args.delete:
            delete_webhook()
        if args.set:
            set_webhook()
        if args.test_message:
            send_test_message()
        if args.updates:
            check_updates()
        if args.render:
            check_render_service()

if __name__ == "__main__":
    main() 