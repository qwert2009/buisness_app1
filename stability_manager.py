#!/usr/bin/env python3
"""
Система стабильности и восстановления
Stability and Recovery Management System
"""

import os
import sys
import time
import json
import shutil
import sqlite3
import threading
import subprocess
import logging
import psutil
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from pathlib import Path
import zipfile
import schedule

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/stability_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class HealthChecker:
    """Система проверки здоровья приложения"""
    
    def __init__(self):
        self.checks = {}
        self.last_check_results = {}
        self.check_interval = 30  # секунд
        self.monitoring_active = False
        
    def register_check(self, name: str, check_func: Callable, critical: bool = False):
        """Регистрация проверки здоровья"""
        self.checks[name] = {
            'func': check_func,
            'critical': critical,
            'last_result': None,
            'last_check': None,
            'failure_count': 0
        }
        logger.info(f"Зарегистрирована проверка: {name}")
    
    def run_check(self, name: str) -> bool:
        """Выполнение конкретной проверки"""
        if name not in self.checks:
            return False
        
        check = self.checks[name]
        try:
            result = check['func']()
            check['last_result'] = result
            check['last_check'] = datetime.now()
            
            if result:
                check['failure_count'] = 0
            else:
                check['failure_count'] += 1
                
            return result
            
        except Exception as e:
            logger.error(f"Ошибка в проверке {name}: {e}")
            check['last_result'] = False
            check['failure_count'] += 1
            return False
    
    def run_all_checks(self) -> Dict:
        """Выполнение всех проверок"""
        results = {}
        critical_failures = []
        
        for name in self.checks:
            result = self.run_check(name)
            results[name] = result
            
            if not result and self.checks[name]['critical']:
                critical_failures.append(name)
        
        return {
            'results': results,
            'critical_failures': critical_failures,
            'overall_health': len(critical_failures) == 0
        }
    
    def start_monitoring(self):
        """Запуск мониторинга здоровья"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        monitoring_thread.start()
        logger.info("Мониторинг здоровья запущен")
    
    def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        while self.monitoring_active:
            try:
                health_status = self.run_all_checks()
                
                if not health_status['overall_health']:
                    logger.warning(f"Критические ошибки: {health_status['critical_failures']}")
                    # Здесь можно добавить автоматическое восстановление
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга здоровья: {e}")
                time.sleep(5)

class BackupManager:
    """Менеджер резервного копирования"""
    
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        self.max_backups = 10
        self.auto_backup_enabled = True
        self.backup_interval_hours = 6
        
    def create_backup(self, backup_type: str = "manual") -> str:
        """Создание резервной копии"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}"
        backup_path = self.backup_dir / f"{backup_name}.zip"
        
        try:
            logger.info(f"Создание резервной копии: {backup_name}")
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Резервное копирование базы данных
                if os.path.exists('business_manager.db'):
                    zipf.write('business_manager.db', 'business_manager.db')
                
                # Резервное копирование конфигурационных файлов
                config_files = [
                    'server_config.json',
                    'config.py',
                    '.env'
                ]
                
                for config_file in config_files:
                    if os.path.exists(config_file):
                        zipf.write(config_file, config_file)
                
                # Резервное копирование пользовательских данных
                if os.path.exists('uploads'):
                    for root, dirs, files in os.walk('uploads'):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, '.')
                            zipf.write(file_path, arcname)
                
                # Резервное копирование логов (последние 7 дней)
                if os.path.exists('logs'):
                    cutoff_date = datetime.now() - timedelta(days=7)
                    for root, dirs, files in os.walk('logs'):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if os.path.getmtime(file_path) > cutoff_date.timestamp():
                                arcname = os.path.relpath(file_path, '.')
                                zipf.write(file_path, arcname)
            
            logger.info(f"Резервная копия создана: {backup_path}")
            self._cleanup_old_backups()
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            return None
    
    def restore_backup(self, backup_path: str) -> bool:
        """Восстановление из резервной копии"""
        try:
            logger.info(f"Восстановление из резервной копии: {backup_path}")
            
            # Создаем резервную копию текущего состояния
            current_backup = self.create_backup("pre_restore")
            
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall('.')
            
            logger.info("Восстановление завершено успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка восстановления: {e}")
            return False
    
    def _cleanup_old_backups(self):
        """Очистка старых резервных копий"""
        try:
            backup_files = list(self.backup_dir.glob("backup_*.zip"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            if len(backup_files) > self.max_backups:
                for old_backup in backup_files[self.max_backups:]:
                    old_backup.unlink()
                    logger.info(f"Удалена старая резервная копия: {old_backup}")
                    
        except Exception as e:
            logger.error(f"Ошибка очистки старых резервных копий: {e}")
    
    def schedule_auto_backup(self):
        """Планирование автоматического резервного копирования"""
        if self.auto_backup_enabled:
            schedule.every(self.backup_interval_hours).hours.do(
                lambda: self.create_backup("auto")
            )
            logger.info(f"Автоматическое резервное копирование запланировано каждые {self.backup_interval_hours} часов")

class ProcessManager:
    """Менеджер процессов приложения"""
    
    def __init__(self):
        self.main_process = None
        self.child_processes = []
        self.restart_attempts = 0
        self.max_restart_attempts = 5
        self.restart_delay = 10  # секунд
        self.monitoring_active = False
        
    def start_application(self, host: str = "0.0.0.0", port: int = 8501) -> bool:
        """Запуск основного приложения"""
        try:
            cmd = [
                sys.executable, "-m", "streamlit", "run", "enhanced_app.py",
                "--server.port", str(port),
                "--server.address", host,
                "--server.headless", "true"
            ]
            
            logger.info(f"Запуск приложения на {host}:{port}")
            
            self.main_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if os.name == 'posix' else None
            )
            
            # Ждем немного, чтобы убедиться, что процесс запустился
            time.sleep(3)
            
            if self.main_process.poll() is None:
                logger.info(f"Приложение успешно запущено (PID: {self.main_process.pid})")
                self.restart_attempts = 0
                return True
            else:
                logger.error("Приложение не смогло запуститься")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка запуска приложения: {e}")
            return False
    
    def stop_application(self):
        """Остановка приложения"""
        try:
            if self.main_process:
                logger.info("Остановка основного процесса")
                
                if os.name == 'posix':
                    # Unix-системы
                    os.killpg(os.getpgid(self.main_process.pid), signal.SIGTERM)
                else:
                    # Windows
                    self.main_process.terminate()
                
                # Ждем завершения процесса
                try:
                    self.main_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Принудительное завершение процесса")
                    if os.name == 'posix':
                        os.killpg(os.getpgid(self.main_process.pid), signal.SIGKILL)
                    else:
                        self.main_process.kill()
                
                self.main_process = None
                logger.info("Основной процесс остановлен")
            
            # Остановка дочерних процессов
            for process in self.child_processes:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except:
                    process.kill()
            
            self.child_processes.clear()
            
        except Exception as e:
            logger.error(f"Ошибка остановки приложения: {e}")
    
    def restart_application(self, host: str = "0.0.0.0", port: int = 8501) -> bool:
        """Перезапуск приложения"""
        if self.restart_attempts >= self.max_restart_attempts:
            logger.error(f"Превышено максимальное количество попыток перезапуска ({self.max_restart_attempts})")
            return False
        
        self.restart_attempts += 1
        logger.info(f"Перезапуск приложения (попытка {self.restart_attempts}/{self.max_restart_attempts})")
        
        self.stop_application()
        time.sleep(self.restart_delay)
        
        return self.start_application(host, port)
    
    def is_application_running(self) -> bool:
        """Проверка, работает ли приложение"""
        if not self.main_process:
            return False
        
        return self.main_process.poll() is None
    
    def start_monitoring(self, host: str = "0.0.0.0", port: int = 8501):
        """Запуск мониторинга процессов"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        monitoring_thread = threading.Thread(
            target=self._monitoring_loop, 
            args=(host, port), 
            daemon=True
        )
        monitoring_thread.start()
        logger.info("Мониторинг процессов запущен")
    
    def _monitoring_loop(self, host: str, port: int):
        """Основной цикл мониторинга процессов"""
        while self.monitoring_active:
            try:
                if not self.is_application_running():
                    logger.warning("Основной процесс не работает, попытка перезапуска")
                    self.restart_application(host, port)
                
                time.sleep(30)  # Проверяем каждые 30 секунд
                
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга процессов: {e}")
                time.sleep(5)

class StabilityManager:
    """Главный менеджер стабильности"""
    
    def __init__(self):
        self.health_checker = HealthChecker()
        self.backup_manager = BackupManager()
        self.process_manager = ProcessManager()
        self.recovery_strategies = {}
        
        # Регистрируем базовые проверки здоровья
        self._register_default_health_checks()
        
        # Планируем автоматические задачи
        self._schedule_maintenance_tasks()
    
    def _register_default_health_checks(self):
        """Регистрация базовых проверок здоровья"""
        
        def check_database():
            """Проверка доступности базы данных"""
            try:
                conn = sqlite3.connect('business_manager.db', timeout=5)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                conn.close()
                return True
            except:
                return False
        
        def check_disk_space():
            """Проверка свободного места на диске"""
            try:
                usage = psutil.disk_usage('.')
                free_percent = (usage.free / usage.total) * 100
                return free_percent > 10  # Минимум 10% свободного места
            except:
                return False
        
        def check_memory_usage():
            """Проверка использования памяти"""
            try:
                memory = psutil.virtual_memory()
                return memory.percent < 90  # Максимум 90% использования памяти
            except:
                return False
        
        def check_application_process():
            """Проверка работы основного процесса"""
            return self.process_manager.is_application_running()
        
        # Регистрируем проверки
        self.health_checker.register_check("database", check_database, critical=True)
        self.health_checker.register_check("disk_space", check_disk_space, critical=True)
        self.health_checker.register_check("memory_usage", check_memory_usage, critical=False)
        self.health_checker.register_check("application_process", check_application_process, critical=True)
    
    def _schedule_maintenance_tasks(self):
        """Планирование задач обслуживания"""
        # Автоматическое резервное копирование
        self.backup_manager.schedule_auto_backup()
        
        # Ежедневная очистка логов
        schedule.every().day.at("02:00").do(self._cleanup_logs)
        
        # Еженедельная оптимизация базы данных
        schedule.every().week.do(self._optimize_database)
    
    def _cleanup_logs(self):
        """Очистка старых логов"""
        try:
            log_dir = Path("logs")
            if log_dir.exists():
                cutoff_date = datetime.now() - timedelta(days=30)
                
                for log_file in log_dir.glob("*.log"):
                    if log_file.stat().st_mtime < cutoff_date.timestamp():
                        log_file.unlink()
                        logger.info(f"Удален старый лог: {log_file}")
                        
        except Exception as e:
            logger.error(f"Ошибка очистки логов: {e}")
    
    def _optimize_database(self):
        """Оптимизация базы данных"""
        try:
            conn = sqlite3.connect('business_manager.db')
            cursor = conn.cursor()
            cursor.execute("VACUUM")
            cursor.execute("ANALYZE")
            conn.close()
            logger.info("База данных оптимизирована")
            
        except Exception as e:
            logger.error(f"Ошибка оптимизации базы данных: {e}")
    
    def start_all_monitoring(self, host: str = "0.0.0.0", port: int = 8501):
        """Запуск всех систем мониторинга"""
        logger.info("Запуск всех систем мониторинга")
        
        # Запускаем мониторинг здоровья
        self.health_checker.start_monitoring()
        
        # Запускаем мониторинг процессов
        self.process_manager.start_monitoring(host, port)
        
        # Запускаем планировщик задач
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)
        
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        
        logger.info("Все системы мониторинга запущены")
    
    def emergency_recovery(self):
        """Экстренное восстановление"""
        logger.warning("Запуск экстренного восстановления")
        
        try:
            # Останавливаем все процессы
            self.process_manager.stop_application()
            
            # Создаем резервную копию текущего состояния
            self.backup_manager.create_backup("emergency")
            
            # Пытаемся восстановить из последней рабочей копии
            backup_files = list(Path("backups").glob("backup_*.zip"))
            if backup_files:
                latest_backup = max(backup_files, key=lambda x: x.stat().st_mtime)
                logger.info(f"Восстановление из резервной копии: {latest_backup}")
                self.backup_manager.restore_backup(str(latest_backup))
            
            # Перезапускаем приложение
            time.sleep(5)
            self.process_manager.restart_application()
            
            logger.info("Экстренное восстановление завершено")
            
        except Exception as e:
            logger.error(f"Ошибка экстренного восстановления: {e}")
    
    def get_system_status(self) -> Dict:
        """Получение статуса системы"""
        health_status = self.health_checker.run_all_checks()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "health": health_status,
            "application_running": self.process_manager.is_application_running(),
            "restart_attempts": self.process_manager.restart_attempts,
            "system_resources": {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('.').percent
            }
        }

# Глобальный экземпляр менеджера стабильности
stability_manager = StabilityManager()

def get_stability_manager() -> StabilityManager:
    """Получение экземпляра менеджера стабильности"""
    return stability_manager

if __name__ == "__main__":
    # Тестирование системы стабильности
    manager = StabilityManager()
    
    print("Статус системы:")
    status = manager.get_system_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))
    
    # Запуск мониторинга
    manager.start_all_monitoring()
    
    # Ждем некоторое время
    time.sleep(30)
    
    print("\nОбновленный статус:")
    status = manager.get_system_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))

