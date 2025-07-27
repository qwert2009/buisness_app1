#!/usr/bin/env python3
"""
Простой скрипт запуска Бизнес Менеджер Премиум+
Simple Start Script for Business Manager Premium+

Использование:
    python start.py                    # Обычный запуск
    python start.py --auto             # Автоматический режим
    python start.py --port 8502        # Указать порт
    python start.py --help             # Справка
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

def print_banner():
    """Вывод баннера приложения"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║        🚀 Бизнес Менеджер Премиум+ 🚀                       ║
║                                                              ║
║        Автоматический запуск с подбором серверов             ║
║        и обеспечением стабильности работы                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)

def check_python_version():
    """Проверка версии Python"""
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        print(f"   Текущая версия: {sys.version}")
        return False
    return True

def install_requirements():
    """Установка зависимостей"""
    requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        print("❌ Файл requirements.txt не найден")
        return False
    
    print("📦 Установка зависимостей...")
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], check=True, capture_output=True)
        print("✅ Зависимости установлены")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка установки зависимостей: {e}")
        return False

def create_directories():
    """Создание необходимых директорий"""
    directories = ["logs", "backups", "uploads", "exports", "static"]
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    print("📁 Директории созданы")

def simple_start(host="0.0.0.0", port=8501):
    """Простой запуск без автоматизации"""
    print(f"🚀 Запуск приложения на {host}:{port}")
    
    try:
        cmd = [
            sys.executable, "-m", "streamlit", "run", "enhanced_app.py",
            "--server.port", str(port),
            "--server.address", host,
            "--server.headless", "true"
        ]
        
        subprocess.run(cmd)
        
    except KeyboardInterrupt:
        print("\n👋 Приложение остановлено пользователем")
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")

def auto_start():
    """Автоматический запуск с полным функционалом"""
    print("🤖 Запуск в автоматическом режиме...")
    
    try:
        # Импортируем и запускаем автоматический запускатель
        from auto_launcher import AutoLauncher
        
        launcher = AutoLauncher()
        launcher.run()
        
    except ImportError:
        print("❌ Модуль auto_launcher не найден")
        print("   Используется простой режим запуска...")
        simple_start()
    except Exception as e:
        print(f"❌ Ошибка автоматического запуска: {e}")
        print("   Переключение на простой режим...")
        simple_start()

def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Запуск Бизнес Менеджер Премиум+",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python start.py                     # Простой запуск
  python start.py --auto              # Автоматический режим
  python start.py --port 8502         # Указать порт
  python start.py --host 127.0.0.1    # Указать хост
  python start.py --install           # Только установка зависимостей
        """
    )
    
    parser.add_argument('--auto', '-a', action='store_true',
                       help='Автоматический режим с мониторингом и восстановлением')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Хост для запуска (по умолчанию: 0.0.0.0)')
    parser.add_argument('--port', '-p', type=int, default=8501,
                       help='Порт для запуска (по умолчанию: 8501)')
    parser.add_argument('--install', '-i', action='store_true',
                       help='Только установка зависимостей')
    parser.add_argument('--no-banner', action='store_true',
                       help='Не показывать баннер')
    
    args = parser.parse_args()
    
    # Показываем баннер
    if not args.no_banner:
        print_banner()
    
    # Проверяем версию Python
    if not check_python_version():
        sys.exit(1)
    
    # Создаем директории
    create_directories()
    
    # Устанавливаем зависимости
    if args.install:
        success = install_requirements()
        sys.exit(0 if success else 1)
    
    # Проверяем наличие основного файла приложения
    if not Path("enhanced_app.py").exists():
        print("❌ Файл enhanced_app.py не найден")
        print("   Убедитесь, что вы находитесь в правильной директории")
        sys.exit(1)
    
    # Пытаемся установить зависимости автоматически
    if not install_requirements():
        print("⚠️  Продолжаем без установки зависимостей...")
    
    print("\n" + "="*60)
    print("🎯 Готов к запуску!")
    print("="*60)
    
    try:
        if args.auto:
            # Автоматический режим
            auto_start()
        else:
            # Простой режим
            simple_start(args.host, args.port)
            
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

