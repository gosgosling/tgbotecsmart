import os
import sys
import requests
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Получение токена бота
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    print("Ошибка: TELEGRAM_TOKEN не найден в переменных окружения")
    sys.exit(1)

# Запрос URL для вебхука
webhook_url = input("Введите URL вашего сервиса на Render (например, https://feedback-bot.onrender.com): ")
if not webhook_url:
    print("Ошибка: URL не может быть пустым")
    sys.exit(1)

# Убираем слеш в конце URL, если он есть
webhook_url = webhook_url.rstrip('/')

# Формируем полный URL для вебхука
full_webhook_url = f"{webhook_url}/bot{TELEGRAM_TOKEN}"

# URL для установки вебхука
telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"

# Параметры запроса
params = {
    "url": full_webhook_url,
    "drop_pending_updates": True
}

print(f"Устанавливаем вебхук на URL: {full_webhook_url}")

# Отправка запроса к Telegram API
try:
    response = requests.post(telegram_url, params=params)
    response.raise_for_status()
    
    # Вывод ответа
    data = response.json()
    if data.get("ok"):
        print("Вебхук успешно установлен!")
        print(f"Описание: {data.get('description', '')}")
    else:
        print(f"Ошибка при установке вебхука: {data.get('description', 'Неизвестная ошибка')}")
        
except requests.exceptions.RequestException as e:
    print(f"Ошибка при отправке запроса: {e}")
    sys.exit(1)

# Проверка статуса вебхука
try:
    check_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
    response = requests.get(check_url)
    response.raise_for_status()
    
    data = response.json()
    if data.get("ok"):
        webhook_info = data.get("result", {})
        print("\nИнформация о вебхуке:")
        print(f"URL: {webhook_info.get('url', 'Не установлен')}")
        print(f"Ожидающие обновления: {webhook_info.get('pending_update_count', 0)}")
        print(f"Последняя ошибка: {webhook_info.get('last_error_message', 'Нет ошибок')}")
        print(f"Максимальные соединения: {webhook_info.get('max_connections', 'Не указано')}")
    else:
        print(f"Ошибка при получении информации о вебхуке: {data.get('description', 'Неизвестная ошибка')}")
        
except requests.exceptions.RequestException as e:
    print(f"Ошибка при отправке запроса проверки: {e}") 