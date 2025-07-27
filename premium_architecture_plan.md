# План архитектуры Премиум+ функций

## Анализ существующей архитектуры

### Текущая структура:
- **Фреймворк**: Streamlit
- **База данных**: SQLite
- **Аутентификация**: streamlit_authenticator + собственная система
- **Структура**: Монолитное приложение с функциональными модулями

### Существующие таблицы БД:
1. `users` - пользователи с базовыми полями
2. `orders` - заказы
3. `order_items` - товары в заказах
4. `inventory` - склад
5. `order_history` - история заказов
6. `settings` - настройки пользователей
7. `notifications` - уведомления
8. `companies` - компании (мультибизнес)
9. `user_companies` - связь пользователей и компаний
10. `warehouses` - склады
11. `ai_ideas` - ИИ идеи
12. `auto_reports` - автоматические отчеты
13. `financial_records` - финансовые записи
14. `activity_log` - журнал действий
15. `chat_messages` - корпоративный чат
16. `branding_settings` - настройки бренда

## Дополнительные таблицы для премиум функций

### 1. Расширенная система ролей и команд
```sql
-- Таблица для детальных прав доступа
CREATE TABLE user_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,
    permission_type TEXT NOT NULL, -- 'read', 'write', 'delete', 'admin'
    resource_type TEXT NOT NULL, -- 'orders', 'inventory', 'analytics', etc.
    granted_by INTEGER, -- кто предоставил права
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (company_id) REFERENCES companies (id),
    FOREIGN KEY (granted_by) REFERENCES users (id)
);

-- Таблица для приглашений в команду
CREATE TABLE team_invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL,
    invited_by INTEGER NOT NULL,
    invitation_token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id),
    FOREIGN KEY (invited_by) REFERENCES users (id)
);
```

### 2. ИИ-аналитика и автоматизация
```sql
-- Таблица для ИИ прогнозов
CREATE TABLE ai_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    company_id INTEGER,
    prediction_type TEXT NOT NULL, -- 'sales', 'inventory', 'demand'
    prediction_data TEXT NOT NULL, -- JSON с данными прогноза
    confidence_score REAL,
    period_start DATE,
    period_end DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

-- Таблица для автоматизированных задач
CREATE TABLE automation_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    company_id INTEGER,
    task_type TEXT NOT NULL, -- 'report', 'reminder', 'calculation'
    task_config TEXT NOT NULL, -- JSON с конфигурацией
    schedule_pattern TEXT, -- cron pattern
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

-- Таблица для ИИ рекомендаций
CREATE TABLE ai_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    company_id INTEGER,
    recommendation_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    action_data TEXT, -- JSON с данными для действия
    priority INTEGER DEFAULT 1,
    is_read BOOLEAN DEFAULT FALSE,
    is_applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (company_id) REFERENCES companies (id)
);
```

### 3. Корпоративный чат и уведомления
```sql
-- Расширение таблицы чата
ALTER TABLE chat_messages ADD COLUMN message_type TEXT DEFAULT 'text'; -- 'text', 'file', 'image'
ALTER TABLE chat_messages ADD COLUMN file_url TEXT;
ALTER TABLE chat_messages ADD COLUMN is_edited BOOLEAN DEFAULT FALSE;
ALTER TABLE chat_messages ADD COLUMN edited_at TIMESTAMP;

-- Таблица для чат-каналов
CREATE TABLE chat_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    is_private BOOLEAN DEFAULT FALSE,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id),
    FOREIGN KEY (created_by) REFERENCES users (id)
);

-- Участники каналов
CREATE TABLE channel_members (
    channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    role TEXT DEFAULT 'member', -- 'admin', 'member'
    PRIMARY KEY (channel_id, user_id),
    FOREIGN KEY (channel_id) REFERENCES chat_channels (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Настройки уведомлений
CREATE TABLE notification_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL,
    delivery_method TEXT NOT NULL, -- 'email', 'sms', 'push'
    is_enabled BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Шаблоны уведомлений
CREATE TABLE notification_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    template_type TEXT NOT NULL,
    subject_template TEXT,
    body_template TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id)
);
```

### 4. Интеграции
```sql
-- Таблица для внешних интеграций
CREATE TABLE integrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    company_id INTEGER,
    integration_type TEXT NOT NULL, -- '1c', 'crm', 'whatsapp', 'telegram'
    config_data TEXT NOT NULL, -- JSON с настройками
    is_active BOOLEAN DEFAULT TRUE,
    last_sync TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

-- Лог синхронизации
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    integration_id INTEGER NOT NULL,
    sync_type TEXT NOT NULL, -- 'import', 'export'
    status TEXT NOT NULL, -- 'success', 'error', 'partial'
    records_processed INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (integration_id) REFERENCES integrations (id)
);
```

### 5. Аналитика клиентов
```sql
-- Таблица клиентов
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    address TEXT,
    customer_type TEXT DEFAULT 'regular', -- 'vip', 'regular', 'new'
    ltv REAL DEFAULT 0, -- Lifetime Value
    first_order_date TIMESTAMP,
    last_order_date TIMESTAMP,
    total_orders INTEGER DEFAULT 0,
    total_spent REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

-- Сегменты клиентов
CREATE TABLE customer_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    criteria TEXT NOT NULL, -- JSON с критериями сегментации
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

-- Принадлежность клиентов к сегментам
CREATE TABLE customer_segment_membership (
    customer_id INTEGER NOT NULL,
    segment_id INTEGER NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id, segment_id),
    FOREIGN KEY (customer_id) REFERENCES customers (id),
    FOREIGN KEY (segment_id) REFERENCES customer_segments (id)
);
```

### 6. Безопасность
```sql
-- Двухфакторная аутентификация
CREATE TABLE user_2fa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    secret_key TEXT NOT NULL,
    backup_codes TEXT, -- JSON массив кодов
    is_enabled BOOLEAN DEFAULT FALSE,
    enabled_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Сессии пользователей
CREATE TABLE user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token TEXT NOT NULL UNIQUE,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Резервные копии
CREATE TABLE backup_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    backup_type TEXT NOT NULL, -- 'full', 'incremental'
    file_path TEXT,
    file_size INTEGER,
    status TEXT NOT NULL, -- 'pending', 'running', 'completed', 'failed'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
```

## API архитектура

### Структура API endpoints:
```
/api/v1/
├── auth/
│   ├── login
│   ├── logout
│   ├── refresh
│   └── 2fa/
├── users/
│   ├── profile
│   ├── settings
│   └── permissions
├── companies/
│   ├── list
│   ├── create
│   ├── switch
│   └── {id}/
│       ├── team
│       ├── invite
│       └── settings
├── orders/
├── inventory/
├── analytics/
│   ├── dashboard
│   ├── predictions
│   └── recommendations
├── chat/
│   ├── channels
│   ├── messages
│   └── notifications
├── integrations/
│   ├── 1c
│   ├── crm
│   └── messengers
└── ai/
    ├── ideas
    ├── assistant
    └── reports
```

## Архитектура компонентов

### 1. Модульная структура
```
business_manager/
├── app.py (главный файл)
├── config/
│   ├── database.py
│   ├── settings.py
│   └── auth.py
├── models/
│   ├── user.py
│   ├── company.py
│   ├── order.py
│   └── ...
├── services/
│   ├── ai_service.py
│   ├── chat_service.py
│   ├── integration_service.py
│   └── notification_service.py
├── utils/
│   ├── auth.py
│   ├── permissions.py
│   └── helpers.py
├── components/
│   ├── navigation.py
│   ├── dashboard.py
│   └── ...
└── static/
    ├── css/
    ├── js/
    └── images/
```

### 2. Система прав доступа
- **Owner**: Полные права на компанию
- **Admin**: Все права кроме удаления компании
- **Editor**: Создание, редактирование данных
- **Viewer**: Только просмотр

### 3. Интеграция с ИИ
- OpenAI API для генерации идей и ассистента
- Локальные модели для аналитики
- Кэширование результатов

## План реализации

### Этап 1: Расширение БД и базовых функций
1. Создание дополнительных таблиц
2. Миграция данных
3. Обновление моделей

### Этап 2: Система ролей и команд
1. Расширенные роли
2. Приглашения в команду
3. Переключение между аккаунтами

### Этап 3: ИИ функции
1. Интеграция с OpenAI
2. Генератор идей
3. Аналитика и прогнозы

### Этап 4: Чат и уведомления
1. Реальное время чат
2. Push уведомления
3. Email/SMS интеграция

### Этап 5: Интеграции
1. API для внешних систем
2. Экспорт/импорт данных
3. Синхронизация

### Этап 6: UI/UX улучшения
1. Гамбургер меню
2. Адаптивный дизайн
3. PWA функции

## Технические требования

### Зависимости:
- streamlit
- sqlite3
- pandas
- plotly
- openai
- smtplib
- schedule
- hashlib
- jwt (для токенов)
- requests (для интеграций)

### Производительность:
- Кэширование запросов
- Пагинация данных
- Асинхронные задачи для тяжелых операций

### Безопасность:
- Хэширование паролей
- JWT токены
- 2FA
- Логирование действий
- Валидация входных данных

