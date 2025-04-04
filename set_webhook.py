import os
import sys
import requests
import time
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Получение токена бота
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    print("Ошибка: TELEGRAM_TOKEN не найден в переменных окружения")
    sys.exit(1)

def check_current_webhook():
    """Проверяет текущий статус вебхука."""
    webhook_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
    
    try:
        response = requests.get(webhook_url)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            webhook_info = data.get("result", {})
            
            print("=== Текущая информация о вебхуке ===")
            print(f"URL: {webhook_info.get('url', 'Не установлен')}")
            
            return webhook_info
        else:
            print(f"Ошибка при получении информации о вебхуке: {data.get('description', 'Неизвестная ошибка')}")
            return None
    except Exception as e:
        print(f"Ошибка при проверке вебхука: {e}")
        return None

def delete_webhook():
    """Удаляет текущий вебхук."""
    delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
    
    try:
        response = requests.post(delete_url)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            print("Текущий вебхук успешно удален")
            return True
        else:
            print(f"Ошибка при удалении вебхука: {data.get('description', 'Неизвестная ошибка')}")
            return False
    except Exception as e:
        print(f"Ошибка при удалении вебхука: {e}")
        return False

def check_service_availability(url):
    """Проверяет доступность сервиса на Render перед установкой вебхука."""
    # Формируем URL для проверки доступности
    ping_url = f"{url.rstrip('/')}/ping"
    # Альтернативный URL с командой для бота
    bot_ping_url = None
    
    if TELEGRAM_TOKEN in url:
        # Если URL содержит токен, возможно, это полный URL для вебхука
        # Создаем отдельный URL для команды /ping для бота
        base_url = url.split(f"/bot{TELEGRAM_TOKEN}")[0]
        bot_ping_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id=YOUR_CHAT_ID&text=/ping"
    
    print(f"Проверка доступности сервиса на {ping_url}...")
    print("Это может занять некоторое время, если сервис на Render находится в спящем режиме.")
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"Попытка {attempt}/{max_attempts}...")
            response = requests.get(ping_url, timeout=30)
            
            if response.status_code == 200:
                print("Сервис доступен и отвечает корректно!")
                print(f"Ответ: {response.text[:100]}...")
                return True
            else:
                print(f"Сервис вернул код ответа {response.status_code}")
                
            if attempt < max_attempts:
                wait_time = 10 # секунд
                print(f"Ожидание {wait_time} секунд перед следующей попыткой...")
                time.sleep(wait_time)
                
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при проверке доступности: {e}")
            
            if attempt < max_attempts:
                wait_time = 10 # секунд
                print(f"Ожидание {wait_time} секунд перед следующей попыткой...")
                time.sleep(wait_time)
    
    print("\n⚠️ Предупреждение: Сервис недоступен через /ping!")
    if bot_ping_url:
        print(f"\nПопробуйте проверить доступность бота через команду /ping:")
        print(f"URL: {bot_ping_url}")
        print("Замените YOUR_CHAT_ID на ваш Chat ID и откройте этот URL в браузере.")
    
    print("\nУстановка вебхука может не сработать, если сервис недоступен.")
    
    proceed = input("Продолжить установку вебхука, несмотря на недоступность сервиса? (y/n): ")
    return proceed.lower() == 'y'

def set_webhook(webhook_url):
    """Устанавливает вебхук для бота."""
    set_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    
    # Формируем полный URL для вебхука
    full_webhook_url = f"{webhook_url.rstrip('/')}/bot{TELEGRAM_TOKEN}"
    
    params = {
        "url": full_webhook_url,
        "drop_pending_updates": True,  # Удаляем накопившиеся обновления
        "max_connections": 40  # Максимальное количество соединений
    }
    
    print(f"\nУстанавливаем вебхук на URL: {full_webhook_url}")
    
    try:
        response = requests.post(set_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok"):
            print("\n✅ Вебхук успешно установлен!")
            print(f"Описание: {data.get('description', '')}")
            return True
        else:
            print(f"\n❌ Ошибка при установке вебхука: {data.get('description', 'Неизвестная ошибка')}")
            return False
    except Exception as e:
        print(f"\n❌ Ошибка при отправке запроса: {e}")
        return False

def main():
    print("==== Инструмент установки вебхука Telegram ====\n")
    
    # Проверка текущего вебхука
    current_webhook = check_current_webhook()
    
    if current_webhook and current_webhook.get('url'):
        print(f"\nОбнаружен уже установленный вебхук: {current_webhook.get('url')}")
        choice = input("Хотите удалить текущий вебхук и установить новый? (y/n): ")
        
        if choice.lower() != 'y':
            print("Операция отменена.")
            sys.exit(0)
        
        # Удаление текущего вебхука
        delete_webhook()
    
    # Запрос URL для нового вебхука
    webhook_url = input("\nВведите базовый URL вашего сервиса на Render (например, https://feedback-bot.onrender.com): ")
    
    if not webhook_url:
        print("Ошибка: URL не может быть пустым")
        sys.exit(1)
    
    # Проверяем доступность сервиса
    if not check_service_availability(webhook_url):
        print("Операция отменена.")
        sys.exit(1)
    
    # Устанавливаем вебхук
    if set_webhook(webhook_url):
        # Проверяем установленный вебхук
        print("\nПроверка установленного вебхука...")
        time.sleep(2)  # Даем время на обработку запроса
        check_current_webhook()
        
        print("\n==== Установка вебхука завершена ====")
        print("Теперь ваш бот должен получать обновления через вебхук.")
        print("Если возникнут проблемы, проверьте логи на Render и используйте скрипт check_bot.py для диагностики.")
    else:
        print("\n==== Установка вебхука не удалась ====")
        print("Рекомендации:")
        print("1. Убедитесь, что URL сервиса правильный и он доступен")
        print("2. Проверьте логи на Render на наличие ошибок")
        print("3. Попробуйте запустить бота в режиме опроса для отладки")

if __name__ == "__main__":
    main() 