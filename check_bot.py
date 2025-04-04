import requests
import sys
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Получение токена бота
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    print("Ошибка: TELEGRAM_TOKEN не найден в переменных окружения")
    sys.exit(1)

def check_webhook():
    """Проверка статуса вебхука."""
    webhook_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
    
    try:
        response = requests.get(webhook_url)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            webhook_info = data.get("result", {})
            
            print("=== Информация о вебхуке ===")
            print(f"URL: {webhook_info.get('url', 'Не установлен')}")
            print(f"Используется: {'Да' if webhook_info.get('url') else 'Нет'}")
            print(f"Последняя ошибка: {webhook_info.get('last_error_message', 'Нет ошибок')}")
            print(f"Последняя ошибка время: {webhook_info.get('last_error_date', 'Нет ошибок')}")
            print(f"Ожидающие обновления: {webhook_info.get('pending_update_count', 0)}")
            print(f"Максимальные соединения: {webhook_info.get('max_connections', 'Не указано')}")
            
            # Проверка наличия ошибок
            if webhook_info.get('last_error_message'):
                print("\n⚠️ ВНИМАНИЕ: Обнаружена ошибка вебхука!")
                print(f"Ошибка: {webhook_info.get('last_error_message')}")
                
                if "wrong response from the webhook" in webhook_info.get('last_error_message', ''):
                    print("\nВозможные причины:")
                    print("1. Ваш сервер не отвечает правильно на запросы Telegram")
                    print("2. URL вебхука неверный или сервер недоступен")
                    print("3. В обработчике вебхука происходит ошибка")
                    
                print("\nРекомендации:")
                print("1. Проверьте, что ваш сервер запущен и доступен")
                print("2. Убедитесь, что URL вебхука правильный")
                print("3. Проверьте логи на наличие ошибок")
            
            # URL не установлен
            if not webhook_info.get('url'):
                print("\n⚠️ ВНИМАНИЕ: URL вебхука не установлен!")
                print("Бот работает в режиме опроса (polling) или вебхук не настроен")
                print("\nРекомендации:")
                print("1. Установите вебхук с помощью скрипта set_webhook.py")
                print("2. Или вручную через API: /setWebhook?url=<URL>")
            
            return webhook_info
            
        else:
            print(f"Ошибка: {data.get('description', 'Неизвестная ошибка')}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при выполнении запроса: {e}")
        return None

def check_bot_info():
    """Проверка информации о боте."""
    bot_info_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
    
    try:
        response = requests.get(bot_info_url)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            bot_info = data.get("result", {})
            
            print("\n=== Информация о боте ===")
            print(f"ID: {bot_info.get('id')}")
            print(f"Имя: {bot_info.get('first_name')}")
            print(f"Username: @{bot_info.get('username')}")
            print(f"Может присоединяться к группам: {'Да' if bot_info.get('can_join_groups') else 'Нет'}")
            print(f"Может читать все сообщения: {'Да' if bot_info.get('can_read_all_group_messages') else 'Нет'}")
            print(f"Поддерживает встроенные запросы: {'Да' if bot_info.get('supports_inline_queries') else 'Нет'}")
            
            return bot_info
            
        else:
            print(f"Ошибка: {data.get('description', 'Неизвестная ошибка')}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при выполнении запроса: {e}")
        return None

def check_updates():
    """Проверка последних обновлений."""
    updates_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?limit=5"
    
    try:
        response = requests.get(updates_url)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            updates = data.get("result", [])
            
            if not updates:
                print("\n=== Последние обновления ===")
                print("Нет доступных обновлений. Возможные причины:")
                print("1. Бот работает в режиме вебхука (getUpdates не работает при активном вебхуке)")
                print("2. Никто не взаимодействовал с ботом")
                print("3. Все обновления уже обработаны")
                return []
            
            print("\n=== Последние обновления ===")
            print(f"Найдено {len(updates)} обновлений")
            
            for update in updates:
                update_id = update.get('update_id')
                message = update.get('message', {})
                callback_query = update.get('callback_query', {})
                
                if message:
                    from_user = message.get('from', {})
                    chat = message.get('chat', {})
                    text = message.get('text', '<нет текста>')
                    
                    print(f"\nID обновления: {update_id}")
                    print(f"Тип: сообщение")
                    print(f"От: {from_user.get('first_name')} (@{from_user.get('username', 'нет')})")
                    print(f"Чат ID: {chat.get('id')}")
                    print(f"Текст: {text}")
                
                elif callback_query:
                    from_user = callback_query.get('from', {})
                    data = callback_query.get('data', '<нет данных>')
                    
                    print(f"\nID обновления: {update_id}")
                    print(f"Тип: callback_query")
                    print(f"От: {from_user.get('first_name')} (@{from_user.get('username', 'нет')})")
                    print(f"Данные: {data}")
            
            return updates
            
        else:
            print(f"Ошибка: {data.get('description', 'Неизвестная ошибка')}")
            if "Conflict" in data.get('description', ''):
                print("Конфликт: Бот уже использует webhook. Нельзя получить обновления через getUpdates.")
                print("Для решения: удалите вебхук или используйте его для работы с ботом.")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при выполнении запроса: {e}")
        return None

def check_render_service(url):
    """Проверка доступности сервиса на Render."""
    ping_url = f"{url.rstrip('/')}/ping"
    
    try:
        print(f"\n=== Проверка доступности сервиса на {ping_url} ===")
        response = requests.get(ping_url, timeout=10)
        
        print(f"Статус-код: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"Статус: {data.get('status')}")
                print(f"Сообщение: {data.get('message')}")
                print(f"Время: {data.get('time')}")
                print(f"Вебхук включен: {data.get('webhook_enabled')}")
                print(f"URL вебхука: {data.get('webhook_url')}")
                return True
            except:
                print("Ответ не является JSON")
                print(f"Содержимое: {response.text[:100]}")
                return False
        else:
            print(f"Неуспешный ответ: {response.text[:100]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при выполнении запроса: {e}")
        return False

def main():
    print("==== Инструмент проверки бота Telegram ====")
    
    # Проверка информации о боте
    bot_info = check_bot_info()
    
    if not bot_info:
        print("Не удалось получить информацию о боте. Проверьте токен.")
        sys.exit(1)
    
    # Проверка вебхука
    webhook_info = check_webhook()
    
    # Проверка обновлений
    updates = check_updates()
    
    # Проверка сервиса на Render
    if webhook_info and webhook_info.get('url'):
        webhook_base_url = webhook_info.get('url').split('/bot')[0]
        check_render_service(webhook_base_url)
    else:
        url = input("\nВведите URL вашего сервиса для проверки (например, https://feedback-bot.onrender.com): ")
        if url:
            check_render_service(url)
    
    print("\n==== Диагностика завершена ====")

if __name__ == "__main__":
    main() 