"""
Configuration settings for Business Manager Premium+
Настройки конфигурации для Бизнес Менеджер Премиум+
"""

import os
from datetime import timedelta

class Config:
    """Базовая конфигурация"""
    
    # Основные настройки приложения
    APP_NAME = "Бизнес Менеджер Премиум+"
    APP_VERSION = "1.0.0"
    
    # База данных
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'business_manager.db')
    
    # Настройки безопасности
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-in-production'
    SESSION_TIMEOUT = timedelta(hours=24)
    
    # OpenAI настройки
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    OPENAI_API_BASE = os.environ.get('OPENAI_API_BASE') or 'https://api.openai.com/v1'
    
    # Настройки уведомлений
    SMTP_SERVER = os.environ.get('SMTP_SERVER') or 'smtp.gmail.com'
    SMTP_PORT = int(os.environ.get('SMTP_PORT') or 587)
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
    
    # Telegram Bot настройки
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    # WhatsApp API настройки
    WHATSAPP_API_TOKEN = os.environ.get('WHATSAPP_API_TOKEN')
    WHATSAPP_PHONE_ID = os.environ.get('WHATSAPP_PHONE_ID')
    
    # Настройки файлов
    MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'xlsx', 'csv'}
    
    # Настройки кэширования
    CACHE_TIMEOUT = 300  # 5 минут
    
    # Настройки логирования
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FILE = os.path.join(os.path.dirname(__file__), 'logs', 'app.log')
    
    # Настройки резервного копирования
    BACKUP_INTERVAL = timedelta(hours=6)  # Каждые 6 часов
    BACKUP_RETENTION_DAYS = 30
    BACKUP_FOLDER = os.path.join(os.path.dirname(__file__), 'backups')
    
    # Настройки интеграций
    INTEGRATION_TIMEOUT = 30  # секунд
    
    # 1С настройки
    ONEC_SERVER_URL = os.environ.get('ONEC_SERVER_URL')
    ONEC_USERNAME = os.environ.get('ONEC_USERNAME')
    ONEC_PASSWORD = os.environ.get('ONEC_PASSWORD')
    
    # CRM настройки
    CRM_API_URL = os.environ.get('CRM_API_URL')
    CRM_API_KEY = os.environ.get('CRM_API_KEY')
    
    # Google Sheets настройки
    GOOGLE_SHEETS_CREDENTIALS_FILE = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_FILE')
    
    # Настройки производительности
    MAX_CONCURRENT_REQUESTS = 100
    REQUEST_TIMEOUT = 30
    
    # Настройки PWA
    PWA_NAME = "БизнесМенеджер"
    PWA_SHORT_NAME = "БМ"
    PWA_THEME_COLOR = "#667eea"
    PWA_BACKGROUND_COLOR = "#667eea"
    
    # VAPID ключи для push-уведомлений
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_CLAIMS = {"sub": "mailto:support@businessmanager.com"}

class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    
class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    
    # Дополнительные настройки безопасности для продакшена
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class TestingConfig(Config):
    """Конфигурация для тестирования"""
    TESTING = True
    DATABASE_PATH = ':memory:'  # Используем in-memory базу для тестов
    LOG_LEVEL = 'ERROR'

# Выбор конфигурации на основе переменной окружения
config_mapping = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Получение текущей конфигурации"""
    config_name = os.environ.get('FLASK_ENV', 'default')
    return config_mapping.get(config_name, DevelopmentConfig)

# Настройки администратора по умолчанию
DEFAULT_ADMIN = {
    'email': 'alexkurumbayev@gmail.com',
    'password': 'qwerty123G',
    'full_name': 'Администратор системы',
    'is_admin': True,
    'premium_status': True
}

# Настройки по умолчанию для новых пользователей
DEFAULT_USER_SETTINGS = {
    'theme': 'light',
    'language': 'ru',
    'timezone': 'Europe/Moscow',
    'notifications_enabled': True,
    'email_notifications': True,
    'push_notifications': True,
    'sms_notifications': False
}

# Настройки премиум функций
PREMIUM_FEATURES = {
    'ai_analytics': True,
    'ai_assistant': True,
    'automation': True,
    'multi_business': True,
    'team_management': True,
    'corporate_chat': True,
    'advanced_integrations': True,
    'custom_reports': True,
    'api_access': True,
    'priority_support': True
}

# Лимиты для разных типов пользователей
USER_LIMITS = {
    'free': {
        'companies': 1,
        'users_per_company': 1,
        'orders_per_month': 100,
        'storage_mb': 100,
        'api_calls_per_day': 0
    },
    'premium': {
        'companies': 5,
        'users_per_company': 10,
        'orders_per_month': 1000,
        'storage_mb': 1000,
        'api_calls_per_day': 1000
    },
    'premium_plus': {
        'companies': -1,  # Безлимитно
        'users_per_company': -1,  # Безлимитно
        'orders_per_month': -1,  # Безлимитно
        'storage_mb': 10000,
        'api_calls_per_day': 10000
    }
}

# Настройки для различных модулей
MODULE_SETTINGS = {
    'inventory': {
        'low_stock_threshold': 10,
        'auto_reorder_enabled': True,
        'barcode_scanning': True
    },
    'orders': {
        'auto_status_update': True,
        'payment_reminders': True,
        'delivery_tracking': True
    },
    'customers': {
        'auto_segmentation': True,
        'birthday_reminders': True,
        'loyalty_program': True
    },
    'finance': {
        'auto_tax_calculation': True,
        'expense_categorization': True,
        'profit_analysis': True
    }
}

