# 🤖 PDS-Ultimate — AI Enterprise Personal Assistant

**Персональная AI-система** для управления бизнесом через Telegram.
Один бот — ноль кнопок — полный контроль голосом и текстом.

---

## ⚡ Возможности

| Модуль | Что делает |
|--------|-----------|
| 🧠 **LLM Engine** | DeepSeek Reasoner + Chat — анализ, парсинг, генерация |
| 🎤 **Voice** | Faster-Whisper (локально) — голос→текст без отправки в облако |
| 📦 **Логистика** | Заказы, товары, трек-номера, статусы, антизабывание |
| 💰 **Финансы** | INCOME - GOODS = REMAINDER - DELIVERY = NET_PROFIT |
| 📅 **Календарь** | События, напоминания за 30 мин, утренний план |
| ✍️ **Мимикрия** | Анализ стиля из 7 TG + 3 WA чатов, генерация «как ты» |
| 📧 **Gmail** | Отчёты на почту каждые 3 дня |
| 🔐 **Безопасность** | Авто-бэкап, кодовое слово — экстренное удаление |
| 📄 **Файлы** | Excel, Word, PDF — создание, чтение, парсинг |

---

## 🏗️ Архитектура

```
pds_ultimate/
├── config.py              # Конфигурация (13 frozen dataclasses)
├── main.py                # Точка входа (7-step startup)
├── core/
│   ├── database.py        # SQLAlchemy 2.0 + SQLite (14 моделей)
│   ├── llm_engine.py      # DeepSeek API client
│   └── scheduler.py       # APScheduler (cron + interval + date)
├── bot/
│   ├── setup.py           # Aiogram 3 Bot + Dispatcher
│   ├── middlewares.py     # Auth, Logging, Database
│   ├── conversation.py    # Менеджер контекста диалога
│   └── handlers/
│       ├── universal.py   # Intent routing (все текстовые)
│       ├── voice.py       # Голосовые сообщения
│       └── files.py       # Документы и фото
├── modules/
│   ├── secretary/         # Стиль, VIP, авто-ответы, календарь
│   ├── logistics/         # Заказы, товары, доставка, архив
│   ├── finance/           # Учёт, валюты, прибыль, синхронизация
│   ├── executive/         # Утренний брифинг, бэкап
│   └── files/             # Файловый менеджер
├── integrations/
│   ├── whatsapp.py        # Playwright — WA Web
│   ├── gmail.py           # Google API — почта
│   └── telethon_client.py # Telethon — TG userbot
├── utils/
│   └── parsers.py         # 8 парсеров (regex, excel, word, pdf, ocr, voice, csv)
└── tests/                 # 101 тест
```

---

## 🚀 Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/qwert2009/buisness_app1.git
cd buisness_app1/agent

# 2. Виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# 3. Зависимости
pip install -r pds_ultimate/requirements.txt

# 4. Playwright (для WhatsApp)
playwright install chromium

# 5. Настроить .env
cp pds_ultimate/.env.example pds_ultimate/.env
nano pds_ultimate/.env

# 6. Запустить
python -m pds_ultimate.main
```

**Подробная инструкция по получению API ключей** → [`SETUP.md`](SETUP.md)

---

## 🧪 Тесты

```bash
cd agent
PYTHONPATH=. pytest pds_ultimate/tests/ -v
```

**101 тест** — config, database, parsers, finance, modules, order lifecycle, cross-references.

---

## 📋 Минимальные требования

- Python 3.11+
- 2 GB RAM (без GPU) / 4 GB RAM (с GPU для Whisper)
- Linux / macOS / WSL2

**Минимум для старта:** `TG_BOT_TOKEN` + `TG_OWNER_ID` + `DEEPSEEK_API_KEY`

---

## 💬 Как пользоваться

Просто пиши боту **что хочешь** — никаких кнопок, никаких команд (кроме `/start`):

- *«Запиши заказ: iPhone 16 Pro, 3 шт, $999»*
- *«Сколько я заработал за январь?»*
- *«Напомни мне завтра в 14:00 позвонить поставщику»*
- *«Переведи 500 долларов в манаты»*
- *«Сделай отчёт по всем заказам за месяц»*
- *«Напиши сообщение Ахмету как я обычно пишу»*

ИИ сам поймёт, что ты хочешь, и сделает.

---

## ⚠️ Лицензия

Приватный проект. Все права защищены.
