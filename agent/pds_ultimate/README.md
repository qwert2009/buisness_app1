<p align="center">
  <h1 align="center">🤖 PDS-Ultimate</h1>
  <p align="center">
    <b>Enterprise AI Personal Assistant for Telegram</b><br>
    <i>Один бот — ноль кнопок — полный контроль голосом и текстом</i>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/tests-2486_passed-brightgreen?logo=pytest" alt="Tests">
    <img src="https://img.shields.io/badge/tools-64+-orange?logo=gear" alt="Tools">
    <img src="https://img.shields.io/badge/AI-DeepSeek_R1-purple?logo=openai" alt="AI">
    <img src="https://img.shields.io/badge/STT-Vosk_Offline-red?logo=microphone" alt="STT">
    <img src="https://img.shields.io/badge/deploy-Docker-2496ED?logo=docker" alt="Docker">
    <img src="https://img.shields.io/badge/license-private-gray" alt="License">
  </p>
</p>

---

## 📋 Обзор

**PDS-Ultimate** — enterprise-grade AI-ассистент для управления бизнесом через Telegram. Полностью автономная система с 64+ инструментами, offline-распознаванием речи, интеллектуальной маршрутизацией задач и production-ready архитектурой.

### Ключевые возможности

| Модуль | Описание | Технологии |
|--------|----------|------------|
| 🧠 **AI Engine** | Reasoning + Chat, цепочки рассуждений, адаптивные запросы | DeepSeek R1 + Chat |
| 🎤 **Speech-to-Text** | Offline распознавание голоса с субтитрами (SRT) | Vosk + Whisper fallback |
| 📦 **Логистика** | Заказы, товары, трек-номера, статусы, антизабывание | SQLAlchemy + APScheduler |
| 💰 **Финансы** | `INCOME - GOODS = REMAINDER - DELIVERY = NET_PROFIT` | Multi-currency (USD/CNY/TMT) |
| 📅 **Календарь** | События, напоминания, утренний брифинг | Google Calendar API |
| ✍️ **Мимикрия стиля** | Анализ 7 TG + 3 WA чатов, генерация «как ты пишешь» | Telethon + Playwright |
| 📧 **Email отчёты** | Автоматические отчёты каждые 3 дня | Gmail API |
| 🔐 **Безопасность** | Авто-бэкап, кодовое слово — экстренное удаление | SQLite backup + encryption |
| 📄 **Документы** | Excel, Word, PDF — создание, чтение, парсинг | openpyxl + docx + PyPDF2 |
| 🌐 **Браузер** | Playwright Pro — парсинг, скриншоты, автоматизация | Playwright Chromium |
| 🔄 **Workflows** | Автоматические цепочки задач, чеклисты | Custom engine |
| 📊 **Аналитика** | Дашборды, CRM, вечерний дайджест | Analytics Dashboard |
| 🔌 **Плагины** | Расширяемая система плагинов | Plugin Manager |
| 🏗️ **Production** | Rate limiting, health checks, graceful shutdown | Production Hardening |

---

## 🏗️ Архитектура

```
pds_ultimate/                          # 64+ tools, 2486 tests
│
├── config.py                          # 14 frozen dataclasses
├── main.py                            # 7-step async startup
│
├── core/                              # 🧠 Ядро системы
│   ├── database.py                    # SQLAlchemy 2.0 + SQLite (14 моделей)
│   ├── llm_engine.py                  # DeepSeek API client (R1 + Chat)
│   ├── scheduler.py                   # APScheduler (cron/interval/date)
│   ├── business_tools.py              # 64+ бизнес-инструментов
│   │
│   ├── speech_engine.py               # 🎤 Vosk STT (offline, SRT subtitles)
│   ├── plugin_system.py               # 🔌 Plugin Manager
│   ├── autonomy_engine.py             # 🤖 Autonomous Agent
│   ├── browser_pro.py                 # 🌐 Playwright Pro
│   ├── reasoning_v2.py                # 🧠 Chain-of-Thought Reasoning
│   ├── memory_v2.py                   # 💾 Long-term Memory
│   │
│   ├── smart_triggers.py              # ⚡ Event-driven Triggers
│   ├── analytics_dashboard.py         # 📊 Analytics Dashboard
│   ├── crm_engine.py                  # 👤 CRM Engine
│   ├── evening_digest.py              # 🌙 Evening Digest
│   ├── workflow_engine.py             # 🔄 Workflow & Checklists
│   │
│   ├── semantic_search_v2.py          # 🔍 Semantic Search
│   ├── confidence_tracker.py          # 📈 Answer Confidence
│   ├── adaptive_query.py              # 🎯 Adaptive Query Engine
│   ├── task_prioritizer.py            # ⏰ Task Prioritization
│   ├── context_compressor.py          # 📦 Context Compression
│   ├── time_relevance.py              # ⏳ Time Relevance Scoring
│   │
│   ├── integration_layer.py           # 🔗 Tool Chains + Circuit Breaker
│   └── production.py                  # 🏭 Production Hardening
│
├── bot/                               # 📱 Telegram Bot
│   ├── setup.py                       # Aiogram 3 Bot + Dispatcher
│   ├── middlewares.py                 # Auth, Logging, DB Session
│   ├── conversation.py                # Context Manager
│   └── handlers/
│       ├── universal.py               # Intent routing (NLU → Tools)
│       ├── voice.py                   # Voice → Vosk STT → Text → Tools
│       └── files.py                   # Documents & Photos
│
├── modules/                           # 📁 Business Modules
│   ├── secretary/                     # Стиль, VIP, авто-ответы, календарь
│   ├── logistics/                     # Заказы, товары, доставка, архив
│   ├── finance/                       # Учёт, валюты, прибыль
│   ├── executive/                     # Брифинг, бэкап, безопасность
│   └── files/                         # Файловый менеджер
│
├── integrations/                      # 🔗 Внешние сервисы
│   ├── whatsapp.py                    # Playwright → WA Web
│   ├── gmail.py                       # Google API → Email
│   └── telethon_client.py             # Telethon → TG Userbot
│
├── utils/
│   └── parsers.py                     # 8 парсеров (regex, excel, word,
│                                      #   pdf, ocr, voice, csv, llm)
│
└── tests/                             # 🧪 2486 тестов (55 файлов)
    ├── test_part7_tools.py
    ├── test_part8_tools.py
    ├── test_part9_tools.py
    ├── test_part10_*.py               # 7 файлов
    ├── test_part11_integration.py
    ├── test_part12_production.py
    ├── test_part13_deploy.py
    ├── test_part14_final.py           # 164 теста (SpeechEngine, smoke, QA)
    └── ... (41 дополнительный файл)
```

---

## 🚀 Быстрый старт

### Локальная установка

```bash
# 1. Клонировать
git clone https://github.com/qwert2009/buisness_app1.git
cd buisness_app1/agent

# 2. Виртуальное окружение
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Зависимости
pip install -r pds_ultimate/requirements.txt

# 4. Playwright (для WhatsApp)
playwright install chromium

# 5. Vosk модель (для голоса)
pip install vosk
# Модель скачается автоматически при первом использовании

# 6. Настроить .env
cp pds_ultimate/.env.example pds_ultimate/.env
nano pds_ultimate/.env

# 7. Запустить
python -m pds_ultimate.main
```

### Docker (рекомендуется для production)

```bash
# Быстрый запуск
docker-compose up -d

# Или через deploy-скрипт
chmod +x scripts/deploy.sh
./scripts/deploy.sh

# Логи
docker-compose logs -f pds

# Бэкап
./scripts/backup.sh
```

---

## ⚙️ Конфигурация (.env)

```env
# ═══════ ОБЯЗАТЕЛЬНЫЕ ═══════
TG_BOT_TOKEN=123456:ABC-DEF          # Telegram Bot Token
TG_OWNER_ID=123456789                 # Ваш Telegram ID
DEEPSEEK_API_KEY=sk-xxxxx             # DeepSeek API ключ

# ═══════ ГОЛОС (Vosk — offline STT) ═══════
WHISPER_LANGUAGE=ru                    # ru, en
WHISPER_DEVICE=cpu                     # cpu, cuda, auto

# ═══════ ОПЦИОНАЛЬНО ═══════
GMAIL_ENABLED=false
WHATSAPP_ENABLED=false
TELETHON_API_ID=                       # Для мимикрии стиля
TELETHON_API_HASH=
SECURITY_EMERGENCY_CODE=               # Кодовое слово
```

**Минимум для старта:** `TG_BOT_TOKEN` + `TG_OWNER_ID` + `DEEPSEEK_API_KEY`

---

## 🧪 Тестирование

```bash
# Все тесты (2486)
cd agent
pytest --tb=short -q

# Конкретная часть
pytest pds_ultimate/tests/test_part14_final.py -v

# С покрытием
pytest --cov=pds_ultimate --cov-report=html
```

### Статистика тестов

| Часть | Файл | Тестов | Покрытие |
|-------|------|--------|----------|
| Part 7 | `test_part7_tools.py` | ~60 | Core tools |
| Part 8 | `test_part8_tools.py` | ~80 | Plugin, Autonomy, Browser |
| Part 9 | `test_part9_tools.py` | ~80 | CRM, Analytics, Workflows |
| Part 10 | `test_part10_*.py` (7 files) | ~200 | Search, Confidence, Priority |
| Part 11 | `test_part11_integration.py` | ~85 | Integration Layer |
| Part 12 | `test_part12_production.py` | ~80 | Production Hardening |
| Part 13 | `test_part13_deploy.py` | ~50 | Docker, Deploy scripts |
| Part 14 | `test_part14_final.py` | 164 | Speech, Smoke, QA |
| Core | 41 test files | ~1700 | Database, Parsers, Modules |
| **Итого** | **55 файлов** | **2486** | **Full coverage** |

---

## 🎤 Speech-to-Text (Vosk)

PDS-Ultimate использует **Vosk** для offline-распознавания речи — без API, без GPU, без отправки данных в облако.

```
Голосовое/Видео-кружок → ffmpeg → WAV 16kHz → Vosk → Текст → AI → Ответ
```

**Поддерживаемые модели:**

| Модель | Размер | Язык |
|--------|--------|------|
| `vosk-model-small-ru-0.22` | 45 MB | 🇷🇺 Русский |
| `vosk-model-small-en-us-0.15` | 40 MB | 🇺🇸 English |
| `vosk-model-ru-0.42` | 1.8 GB | 🇷🇺 Русский (HD) |
| `vosk-model-en-us-0.42-gigaspeech` | 2.3 GB | 🇺🇸 English (HD) |

**Функции:**
- ✅ Пословная разметка с таймингами
- ✅ Генерация SRT-субтитров
- ✅ Авто-конвертация из OGG, MP3, MP4, FLAC
- ✅ Fallback на Faster-Whisper если Vosk недоступен

---

## 🔧 64+ бизнес-инструментов

<details>
<summary><b>📦 Логистика (8 tools)</b></summary>

- `create_order` — Создание заказа
- `get_orders_status` — Статус заказов
- `update_order_status` — Обновление статуса
- `add_tracking` — Добавление трек-номера
- `search_orders` — Поиск по заказам
- `archive_order` — Архивация
- `get_order_history` — История заказа
- `anti_forget_check` — Проверка забытых заказов

</details>

<details>
<summary><b>💰 Финансы (7 tools)</b></summary>

- `set_income` — Установка дохода
- `set_expense` — Установка расхода
- `set_delivery_cost` — Стоимость доставки
- `get_profit_report` — Отчёт о прибыли
- `convert_currency` — Конвертация валют
- `financial_summary` — Финансовая сводка
- `export_finance_excel` — Экспорт в Excel

</details>

<details>
<summary><b>📅 Планирование (5 tools)</b></summary>

- `add_reminder` — Добавить напоминание
- `add_event` — Добавить событие
- `get_schedule` — Расписание на день
- `morning_briefing` — Утренний брифинг
- `google_calendar` — Google Calendar

</details>

<details>
<summary><b>🌐 Браузер & Исследования (6 tools)</b></summary>

- `web_search` — Поиск в интернете
- `browse_page` — Просмотр страницы
- `screenshot` — Скриншот сайта
- `deep_research` — Глубокое исследование
- `summarize_url` — Резюме страницы
- `translate` — Перевод текста

</details>

<details>
<summary><b>📄 Файлы (6 tools)</b></summary>

- `create_excel` — Создание Excel
- `read_excel` — Чтение Excel
- `create_word` — Создание Word
- `read_pdf` — Чтение PDF
- `create_report` — Генерация отчёта
- `ocr_image` — OCR фотографии

</details>

<details>
<summary><b>🧠 AI & Memory (8 tools)</b></summary>

- `remember` — Запомнить информацию
- `recall` — Вспомнить
- `semantic_search` — Семантический поиск
- `reason` — Chain-of-Thought reasoning
- `analyze` — Глубокий анализ
- `confidence_check` — Оценка уверенности
- `context_compress` — Сжатие контекста
- `adaptive_query` — Адаптивный запрос

</details>

<details>
<summary><b>🔗 Integration & Production (12 tools)</b></summary>

- `run_chain` — Цепочка инструментов
- `tool_health` — Здоровье инструментов
- `parallel_tools` — Параллельное выполнение
- `list_chains` — Список цепочек
- `system_health` — Здоровье системы
- `rate_limit_info` — Rate limiting
- `error_report` — Отчёт об ошибках
- `uptime_info` — Аптайм
- `backup_now` — Резервная копия
- `emergency_wipe` — Экстренное удаление
- `add_plugin` — Установка плагина
- `workflow_status` — Статус workflow

</details>

<details>
<summary><b>📊 Analytics & CRM (12 tools)</b></summary>

- `crm_add_contact` — Добавить контакт
- `crm_search` — Поиск по CRM
- `analytics_report` — Аналитический отчёт
- `evening_digest` — Вечерний дайджест
- `trigger_add` — Добавить триггер
- `trigger_list` — Список триггеров
- `checklist_create` — Создать чеклист
- `checklist_status` — Статус чеклиста
- `time_relevance` — Актуальность информации
- `task_priority` — Приоритизация задач
- `style_analyze` — Анализ стиля
- `style_generate` — Генерация в стиле

</details>

---

## 📋 Минимальные требования

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| Python | 3.11+ | 3.12+ |
| RAM | 2 GB | 4 GB |
| Disk | 1 GB | 5 GB (с моделями) |
| OS | Linux / macOS | Ubuntu 22.04+ |
| ffmpeg | Обязательно | `apt install ffmpeg` |

---

## 💬 Как пользоваться

Просто пиши боту **что хочешь** — никаких кнопок, никаких команд:

```
🗣️ «Запиши заказ: iPhone 16 Pro, 3 шт, $999»
💰 «Сколько я заработал за январь?»
📅 «Напомни завтра в 14:00 позвонить поставщику»
💱 «Переведи 500 долларов в манаты»
📊 «Сделай отчёт по всем заказам за месяц в Excel»
✍️ «Напиши сообщение Ахмету как я обычно пишу»
🔍 «Исследуй тренды AI 2026 и сделай резюме»
🎤 [отправить голосовое] → автоматическое распознавание
```

AI сам определит намерение и выберет нужные инструменты.

---

## 📦 Версионирование

| Версия | Описание | Тесты |
|--------|----------|-------|
| v1.0 (P1-7) | Core: DB, LLM, Bot, Parsers, Tools | ~800 |
| v2.0 (P8) | Plugin System, Autonomy, Browser Pro | ~1200 |
| v3.0 (P9) | CRM, Analytics, Workflows, Triggers | ~1600 |
| v4.0 (P10) | Semantic Search, Confidence, Priority | ~2000 |
| v5.0 (P11) | Integration Layer, Circuit Breaker | ~2100 |
| v6.0 (P12) | Production Hardening, Rate Limiting | ~2200 |
| v7.0 (P13) | Docker, Deploy, Backup scripts | ~2320 |
| **v8.0 (P14)** | **Vosk STT, Final QA, 164 smoke tests** | **2486** |

---

## ⚠️ Лицензия

Приватный проект. Все права защищены.

---

<p align="center">
  <b>Built with ❤️ using Python 3.12 • DeepSeek AI • Vosk STT • Aiogram 3</b>
</p>
