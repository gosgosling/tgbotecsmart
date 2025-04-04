# Бот обратной связи компании

Бот для Telegram, который позволяет пользователям оставлять обратную связь после занятий.

## Функциональность

- Приветствие при первом запуске бота
- Выбор типа группы (будни или выходные)
- Указание даты начала занятий
- Автоматическая отправка запросов на обратную связь после окончания занятий
- Пересылка полученной обратной связи менеджеру

## Технические требования

- Python 3.8 или выше
- Доступ к API Telegram

## Установка и настройка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd feedback-bot
```

2. Установите необходимые зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` на основе примера `.env.example`:
```bash
cp .env.example .env
```

4. Отредактируйте файл `.env`, добавив:
   - `TELEGRAM_TOKEN` - токен вашего Telegram бота (получите его у [@BotFather](https://t.me/BotFather))
   - `MANAGER_CHAT_ID` - ID чата менеджера, который будет получать обратную связь
   - `DATABASE_URL` - URL базы данных (по умолчанию используется SQLite)

## Запуск бота

### Локальный запуск

```bash
python bot.py
```

### Размещение на Render

Бот можно легко развернуть на платформе [Render](https://render.com/). Для этого:

1. Зарегистрируйтесь на Render.com
2. Создайте новый Web Service, связав его с вашим GitHub-репозиторием
3. Настройте следующие параметры:
   - **Name**: feedback-bot (или любое другое)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   
4. В разделе Environment Variables добавьте:
   - `TELEGRAM_TOKEN`: ваш токен бота
   - `MANAGER_CHAT_ID`: ID чата менеджера
   - `DATABASE_URL`: URL базы данных на Render (или другой внешней базы данных)

5. Нажмите "Create Web Service"

#### Настройка вебхука

После развертывания необходимо установить вебхук для вашего бота. Есть два способа:

**Способ 1**: Используйте скрипт `set_webhook.py`

```bash
# Локально на вашем компьютере
python set_webhook.py
```

Затем введите URL вашего сервиса на Render, когда будет запрошено (например, https://feedback-bot.onrender.com).

**Способ 2**: Выполните HTTP-запрос вручную

```
https://api.telegram.org/bot<YOUR_TELEGRAM_TOKEN>/setWebhook?url=<YOUR_RENDER_URL>/bot<YOUR_TELEGRAM_TOKEN>
```

Где:
- `<YOUR_TELEGRAM_TOKEN>` - токен вашего бота
- `<YOUR_RENDER_URL>` - URL вашего сервиса на Render (например, https://feedback-bot.onrender.com)

#### Проверка статуса вебхука

Вы можете проверить, правильно ли установлен вебхук, выполнив запрос:

```
https://api.telegram.org/bot<YOUR_TELEGRAM_TOKEN>/getWebhookInfo
```

### Решение проблем развертывания на Render

Если вы видите ошибки при развертывании:

1. **Ошибка: RuntimeError: To use `start_webhook`, PTB must be installed via `pip install "python-telegram-bot[webhooks]"`**
   - Убедитесь, что в `requirements.txt` указано `python-telegram-bot[webhooks]`, а не просто `python-telegram-bot`

2. **Ошибка времени**
   - Проверьте логи на предмет несоответствия времени
   - Наш бот использует московское время (Europe/Moscow)

3. **Проблемы с базой данных**
   - На бесплатном плане Render файловая система временная, используйте внешнюю базу данных
   - Рекомендуется PostgreSQL на Render или другая внешняя база

4. **Бот не отвечает**
   - Проверьте, что вебхук правильно установлен
   - Проверьте логи на Render на наличие ошибок

## Настройка расписания

По умолчанию бот настроен для отправки запросов на обратную связь:
- Для групп будних дней: каждый будний день (Пн-Пт) в 18:00
- Для групп выходного дня: каждую субботу в 14:00

Вы можете изменить расписание, отредактировав функцию `init_schedule()` в файле `database.py`.

## Использование

1. Пользователь запускает бота командой `/start`
2. Выбирает тип группы (будни или выходные)
3. Вводит дату начала занятий
4. После окончания занятия бот автоматически отправит запрос на обратную связь
5. Любое текстовое сообщение от пользователя будет считаться обратной связью и перенаправлено менеджеру

## Структура проекта

- `bot.py` - основной файл бота
- `database.py` - модуль для работы с базой данных
- `utils.py` - вспомогательные функции
- `requirements.txt` - список зависимостей
- `.env.example` - пример файла с переменными окружения
- `Procfile` - файл для запуска на Render
- `render.yaml` - файл конфигурации для Render
- `runtime.txt` - версия Python
- `set_webhook.py` - скрипт для установки вебхука 