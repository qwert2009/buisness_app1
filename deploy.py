#!/usr/bin/env python3
"""
Deployment script for Business Manager Premium+
Скрипт деплоя для Бизнес Менеджер Премиум+
"""

import os
import sys
import subprocess
import shutil
from datetime import datetime
from config import get_config

def check_requirements():
    """Проверка системных требований"""
    print("🔍 Проверка системных требований...")
    
    # Проверка версии Python
    if sys.version_info < (3, 11):
        print("❌ Требуется Python 3.11 или выше")
        return False
    
    # Проверка наличия pip
    try:
        subprocess.run(['pip', '--version'], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("❌ pip не найден")
        return False
    
    print("✅ Системные требования выполнены")
    return True

def install_dependencies():
    """Установка зависимостей"""
    print("📦 Установка зависимостей...")
    
    try:
        subprocess.run([
            sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'
        ], check=True)
        print("✅ Зависимости установлены")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка установки зависимостей: {e}")
        return False

def setup_directories():
    """Создание необходимых директорий"""
    print("📁 Создание директорий...")
    
    directories = [
        'logs',
        'backups',
        'uploads',
        'exports',
        'static/images',
        'static/css',
        'static/js'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    print("✅ Директории созданы")

def setup_database():
    """Инициализация базы данных"""
    print("🗄️ Инициализация базы данных...")
    
    try:
        # Импортируем функцию инициализации из основного приложения
        from enhanced_app import init_enhanced_db, create_admin_user
        
        # Инициализируем базу данных
        init_enhanced_db()
        
        # Создаем администратора по умолчанию
        create_admin_user()
        
        print("✅ База данных инициализирована")
        return True
    except Exception as e:
        print(f"❌ Ошибка инициализации базы данных: {e}")
        return False

def setup_environment():
    """Настройка переменных окружения"""
    print("🔧 Настройка переменных окружения...")
    
    env_template = """
# Основные настройки
FLASK_ENV=production
SECRET_KEY=your-secret-key-change-this-in-production

# OpenAI API (для ИИ функций)
OPENAI_API_KEY=your-openai-api-key
OPENAI_API_BASE=https://api.openai.com/v1

# Email настройки
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Telegram Bot (опционально)
TELEGRAM_BOT_TOKEN=your-telegram-bot-token

# WhatsApp API (опционально)
WHATSAPP_API_TOKEN=your-whatsapp-token
WHATSAPP_PHONE_ID=your-phone-id

# 1С интеграция (опционально)
ONEC_SERVER_URL=http://your-1c-server
ONEC_USERNAME=your-1c-username
ONEC_PASSWORD=your-1c-password

# CRM интеграция (опционально)
CRM_API_URL=https://your-crm-api
CRM_API_KEY=your-crm-api-key

# Google Sheets (опционально)
GOOGLE_SHEETS_CREDENTIALS_FILE=path/to/credentials.json

# VAPID ключи для push-уведомлений (опционально)
VAPID_PUBLIC_KEY=your-vapid-public-key
VAPID_PRIVATE_KEY=your-vapid-private-key
"""
    
    if not os.path.exists('.env'):
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_template.strip())
        print("✅ Создан файл .env с шаблоном настроек")
        print("⚠️  Обязательно отредактируйте файл .env перед запуском!")
    else:
        print("✅ Файл .env уже существует")

def create_systemd_service():
    """Создание systemd сервиса для Linux"""
    if os.name != 'posix':
        return
    
    print("🔧 Создание systemd сервиса...")
    
    current_dir = os.path.abspath('.')
    python_path = sys.executable
    
    service_content = f"""[Unit]
Description=Business Manager Premium+
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory={current_dir}
Environment=PATH={os.path.dirname(python_path)}
ExecStart={python_path} -m streamlit run enhanced_app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
    
    service_file = 'business-manager.service'
    with open(service_file, 'w') as f:
        f.write(service_content)
    
    print(f"✅ Создан файл сервиса: {service_file}")
    print("📋 Для установки сервиса выполните:")
    print(f"   sudo cp {service_file} /etc/systemd/system/")
    print("   sudo systemctl daemon-reload")
    print("   sudo systemctl enable business-manager")
    print("   sudo systemctl start business-manager")

def create_docker_files():
    """Создание Docker файлов"""
    print("🐳 Создание Docker файлов...")
    
    dockerfile_content = """FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов требований
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY . .

# Создание необходимых директорий
RUN mkdir -p logs backups uploads exports static/images static/css static/js

# Открытие порта
EXPOSE 8501

# Команда запуска
CMD ["streamlit", "run", "enhanced_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
"""
    
    docker_compose_content = """version: '3.8'

services:
  business-manager:
    build: .
    ports:
      - "8501:8501"
    environment:
      - FLASK_ENV=production
    volumes:
      - ./business_manager.db:/app/business_manager.db
      - ./logs:/app/logs
      - ./backups:/app/backups
      - ./uploads:/app/uploads
    restart: unless-stopped
    
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - business-manager
    restart: unless-stopped
"""
    
    nginx_config = """events {
    worker_connections 1024;
}

http {
    upstream business_manager {
        server business-manager:8501;
    }
    
    server {
        listen 80;
        server_name your-domain.com;
        
        location / {
            proxy_pass http://business_manager;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # WebSocket поддержка для Streamlit
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
"""
    
    with open('Dockerfile', 'w') as f:
        f.write(dockerfile_content)
    
    with open('docker-compose.yml', 'w') as f:
        f.write(docker_compose_content)
    
    with open('nginx.conf', 'w') as f:
        f.write(nginx_config)
    
    print("✅ Docker файлы созданы")
    print("📋 Для запуска с Docker:")
    print("   docker-compose up -d")

def run_tests():
    """Запуск тестов"""
    print("🧪 Запуск тестов...")
    
    try:
        # Простая проверка импорта основных модулей
        import enhanced_app
        import ai_services
        import chat_notification_service
        import integration_service
        import ui_components
        import mobile_pwa
        
        print("✅ Все модули успешно импортированы")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def create_backup():
    """Создание резервной копии"""
    print("💾 Создание резервной копии...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    
    # Создаем архив с исходным кодом
    shutil.make_archive(
        f"backups/{backup_name}", 
        'zip', 
        '.', 
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 'backups')
    )
    
    print(f"✅ Резервная копия создана: backups/{backup_name}.zip")

def main():
    """Основная функция деплоя"""
    print("🚀 Начинаем деплой Business Manager Premium+")
    print("=" * 50)
    
    steps = [
        ("Проверка требований", check_requirements),
        ("Создание директорий", setup_directories),
        ("Установка зависимостей", install_dependencies),
        ("Настройка окружения", setup_environment),
        ("Инициализация БД", setup_database),
        ("Создание сервиса", create_systemd_service),
        ("Создание Docker файлов", create_docker_files),
        ("Запуск тестов", run_tests),
        ("Создание резервной копии", create_backup)
    ]
    
    failed_steps = []
    
    for step_name, step_func in steps:
        print(f"\\n{step_name}...")
        try:
            if not step_func():
                failed_steps.append(step_name)
        except Exception as e:
            print(f"❌ Ошибка в шаге '{step_name}': {e}")
            failed_steps.append(step_name)
    
    print("\\n" + "=" * 50)
    
    if failed_steps:
        print("⚠️  Деплой завершен с ошибками:")
        for step in failed_steps:
            print(f"   - {step}")
        print("\\nПожалуйста, исправьте ошибки и повторите деплой.")
    else:
        print("🎉 Деплой успешно завершен!")
        print("\\n📋 Следующие шаги:")
        print("1. Отредактируйте файл .env с вашими настройками")
        print("2. Запустите приложение: streamlit run enhanced_app.py")
        print("3. Откройте http://localhost:8501 в браузере")
        print("4. Войдите как администратор: alexkurumbayev@gmail.com / qwerty123G")
        print("\\n🔒 Не забудьте изменить пароль администратора!")

if __name__ == "__main__":
    main()

