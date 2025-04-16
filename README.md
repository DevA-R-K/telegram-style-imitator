# 🤖 Telegram Imitator Bot

Бот, который имитирует стиль общения любого человека из Telegram-чата. Просто загрузи HTML-экспорт переписки — и бот начнет отвечать так, как выбранный собеседник!

## 🚀 Возможности

- 📥 Принимает HTML-файлы экспортов чатов Telegram
- 📊 Анализирует стиль общения (лексика, длина, эмодзи, фразы)
- 🤖 Генерирует ответы в стиле конкретного человека
- 🔁 Сохраняет и управляет профилями собеседников
- 🧠 Использует OpenRouter (Claude 3 Haiku) для генерации

---

## ⚙️ Установка

```bash
git clone https://github.com/yourusername/telegram-imitator-bot.git
cd telegram-imitator-bot
pip install -r requirements.txt
```

---

## 🔑 Настройка

Открой `config.py` и вставь свои ключи:

```python
BOT_TOKEN = "your_telegram_bot_token_here"
OPENROUTER_API_KEY = "your_openrouter_api_key_here"
```

---

## ▶️ Запуск

```bash
python bot.py
```

После запуска:
1. Открой бота в Telegram
2. Нажми "📁 Загрузить новый чат" и отправь `.html` файл
3. Выбери участника чата
4. Пиши — бот будет отвечать в его стиле

---

## 🗂️ Структура проекта

| Файл | Назначение |
|------|------------|
| `bot.py` | Основная логика Telegram-бота |
| `ai.py` | Генерация ответов через Claude |
| `html_parser.py` | Парсинг HTML из Telegram |
| `style_analysis.py` | Анализ стиля сообщений |
| `database.py` | SQLite база данных |
| `profile_management.py` | Управление профилями |
| `keyboards.py` | Клавиатуры Telegram |
| `config.py` | Хранение токенов |

---

## 🧠 Используемые технологии

- Python 3.10+
- aiogram 3
- aiohttp
- beautifulsoup4
- OpenRouter API (Claude 3)

---

## ⚠️ Заметка

Бот работает только с вручную загруженными чатами и не нарушает конфиденциальность. Используйте ответственно 🙏

---

## 📄 Лицензия

MIT License