#!/usr/bin/env python3
"""
Система автоматического подбора серверов и управления
Server Management and Auto-Selection System
"""

import os
import sys
import time
import json
import requests
import subprocess
import threading
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import psutil
import socket
import random

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/server_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ServerConfig:
    """Конфигурация сервера"""
    def __init__(self, name: str, host: str, port: int, priority: int = 1, 
                 max_connections: int = 100, health_check_url: str = None):
        self.name = name
        self.host = host
        self.port = port
        self.priority = priority
        self.max_connections = max_connections
        self.health_check_url = health_check_url or f"http://{host}:{port}/health"
        self.is_healthy = True
        self.last_check = None
        self.response_time = 0
        self.current_connections = 0
        self.error_count = 0
        self.uptime_start = datetime.now()

class ServerManager:
    """Менеджер серверов с автоматическим подбором"""
    
    def __init__(self, config_file: str = "server_config.json"):
        self.config_file = config_file
        self.servers: List[ServerConfig] = []
        self.current_server: Optional[ServerConfig] = None
        self.monitoring_active = False
        self.load_balancer_active = False
        self.auto_scaling_enabled = True
        self.health_check_interval = 30  # секунд
        self.max_error_threshold = 5
        self.response_time_threshold = 5000  # миллисекунд
        
        # Предустановленные серверы для автоматического подбора
        self.default_servers = [
            {
                "name": "Local Development",
                "host": "127.0.0.1",
                "port": 8501,
                "priority": 1,
                "max_connections": 50
            },
            {
                "name": "Local Alternative",
                "host": "0.0.0.0",
                "port": 8502,
                "priority": 2,
                "max_connections": 50
            },
            {
                "name": "Cloud Server 1",
                "host": "0.0.0.0",
                "port": 8503,
                "priority": 3,
                "max_connections": 200
            },
            {
                "name": "Cloud Server 2",
                "host": "0.0.0.0",
                "port": 8504,
                "priority": 4,
                "max_connections": 200
            }
        ]
        
        self.load_config()
        self.start_monitoring()

    def load_config(self):
        """Загрузка конфигурации серверов"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    
                for server_data in config_data.get('servers', []):
                    server = ServerConfig(**server_data)
                    self.servers.append(server)
                    
                logger.info(f"Загружено {len(self.servers)} серверов из конфигурации")
            else:
                # Создаем конфигурацию по умолчанию
                self.create_default_config()
                
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            self.create_default_config()

    def create_default_config(self):
        """Создание конфигурации по умолчанию"""
        logger.info("Создание конфигурации серверов по умолчанию")
        
        for server_data in self.default_servers:
            server = ServerConfig(**server_data)
            self.servers.append(server)
        
        self.save_config()

    def save_config(self):
        """Сохранение конфигурации"""
        try:
            config_data = {
                "servers": [
                    {
                        "name": server.name,
                        "host": server.host,
                        "port": server.port,
                        "priority": server.priority,
                        "max_connections": server.max_connections
                    }
                    for server in self.servers
                ]
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
                
            logger.info("Конфигурация серверов сохранена")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации: {e}")

    def check_server_health(self, server: ServerConfig) -> bool:
        """Проверка здоровья сервера"""
        try:
            start_time = time.time()
            
            # Проверяем доступность порта
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((server.host, server.port))
            sock.close()
            
            response_time = (time.time() - start_time) * 1000
            server.response_time = response_time
            server.last_check = datetime.now()
            
            if result == 0:
                server.is_healthy = True
                server.error_count = 0
                logger.debug(f"Сервер {server.name} здоров (время отклика: {response_time:.2f}мс)")
                return True
            else:
                server.is_healthy = False
                server.error_count += 1
                logger.warning(f"Сервер {server.name} недоступен")
                return False
                
        except Exception as e:
            server.is_healthy = False
            server.error_count += 1
            logger.error(f"Ошибка проверки сервера {server.name}: {e}")
            return False

    def get_best_server(self) -> Optional[ServerConfig]:
        """Получение лучшего доступного сервера"""
        healthy_servers = [s for s in self.servers if s.is_healthy and s.error_count < self.max_error_threshold]
        
        if not healthy_servers:
            logger.warning("Нет доступных здоровых серверов")
            return None
        
        # Сортируем по приоритету, затем по времени отклика
        healthy_servers.sort(key=lambda s: (s.priority, s.response_time))
        
        # Выбираем сервер с наименьшей нагрузкой среди серверов с одинаковым приоритетом
        best_priority = healthy_servers[0].priority
        best_servers = [s for s in healthy_servers if s.priority == best_priority]
        
        # Выбираем сервер с наименьшей нагрузкой
        best_server = min(best_servers, key=lambda s: s.current_connections / s.max_connections)
        
        logger.info(f"Выбран лучший сервер: {best_server.name} ({best_server.host}:{best_server.port})")
        return best_server

    def switch_server(self, new_server: ServerConfig):
        """Переключение на новый сервер"""
        if self.current_server:
            logger.info(f"Переключение с {self.current_server.name} на {new_server.name}")
        else:
            logger.info(f"Запуск на сервере {new_server.name}")
        
        self.current_server = new_server

    def start_monitoring(self):
        """Запуск мониторинга серверов"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        monitoring_thread.start()
        logger.info("Мониторинг серверов запущен")

    def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        while self.monitoring_active:
            try:
                # Проверяем здоровье всех серверов
                for server in self.servers:
                    self.check_server_health(server)
                
                # Если текущий сервер нездоров, переключаемся на лучший
                if self.current_server and not self.current_server.is_healthy:
                    logger.warning(f"Текущий сервер {self.current_server.name} нездоров, ищем замену")
                    best_server = self.get_best_server()
                    if best_server and best_server != self.current_server:
                        self.switch_server(best_server)
                
                # Если нет текущего сервера, выбираем лучший
                if not self.current_server:
                    best_server = self.get_best_server()
                    if best_server:
                        self.switch_server(best_server)
                
                time.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(5)

    def add_server(self, name: str, host: str, port: int, priority: int = 5):
        """Добавление нового сервера"""
        server = ServerConfig(name, host, port, priority)
        self.servers.append(server)
        self.save_config()
        logger.info(f"Добавлен новый сервер: {name} ({host}:{port})")

    def remove_server(self, name: str):
        """Удаление сервера"""
        self.servers = [s for s in self.servers if s.name != name]
        self.save_config()
        logger.info(f"Удален сервер: {name}")

    def get_server_status(self) -> Dict:
        """Получение статуса всех серверов"""
        return {
            "current_server": {
                "name": self.current_server.name,
                "host": self.current_server.host,
                "port": self.current_server.port,
                "uptime": str(datetime.now() - self.current_server.uptime_start)
            } if self.current_server else None,
            "servers": [
                {
                    "name": server.name,
                    "host": server.host,
                    "port": server.port,
                    "is_healthy": server.is_healthy,
                    "response_time": server.response_time,
                    "error_count": server.error_count,
                    "last_check": server.last_check.isoformat() if server.last_check else None
                }
                for server in self.servers
            ]
        }

    def auto_scale(self):
        """Автоматическое масштабирование"""
        if not self.auto_scaling_enabled:
            return
        
        # Проверяем нагрузку на текущий сервер
        if self.current_server:
            load_percentage = self.current_server.current_connections / self.current_server.max_connections
            
            if load_percentage > 0.8:  # Если нагрузка больше 80%
                logger.info("Высокая нагрузка, попытка масштабирования")
                self.try_start_additional_server()

    def try_start_additional_server(self):
        """Попытка запуска дополнительного сервера"""
        # Ищем свободный порт
        for port in range(8505, 8520):
            if self.is_port_free(port):
                logger.info(f"Запуск дополнительного сервера на порту {port}")
                self.start_server_instance(port)
                break

    def is_port_free(self, port: int) -> bool:
        """Проверка свободности порта"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('0.0.0.0', port))
            sock.close()
            return True
        except:
            return False

    def start_server_instance(self, port: int):
        """Запуск экземпляра сервера"""
        try:
            # Запускаем новый экземпляр приложения
            cmd = [
                sys.executable, "-m", "streamlit", "run", "enhanced_app.py",
                "--server.port", str(port),
                "--server.address", "0.0.0.0"
            ]
            
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Добавляем новый сервер в список
            server_name = f"Auto-scaled Server {port}"
            self.add_server(server_name, "0.0.0.0", port, priority=10)
            
            logger.info(f"Запущен дополнительный сервер на порту {port}")
            
        except Exception as e:
            logger.error(f"Ошибка запуска дополнительного сервера: {e}")

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.monitoring_active = False
        logger.info("Мониторинг серверов остановлен")

# Глобальный экземпляр менеджера серверов
server_manager = ServerManager()

def get_server_manager() -> ServerManager:
    """Получение экземпляра менеджера серверов"""
    return server_manager

def get_current_server_info() -> Dict:
    """Получение информации о текущем сервере"""
    return server_manager.get_server_status()

def ensure_server_running() -> Tuple[str, int]:
    """Обеспечение работы сервера"""
    best_server = server_manager.get_best_server()
    if not best_server:
        # Если нет доступных серверов, пытаемся запустить на порту по умолчанию
        logger.warning("Нет доступных серверов, запуск на порту по умолчанию")
        return "0.0.0.0", 8501
    
    server_manager.switch_server(best_server)
    return best_server.host, best_server.port

if __name__ == "__main__":
    # Тестирование системы
    manager = ServerManager()
    
    print("Статус серверов:")
    status = manager.get_server_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))
    
    # Ждем некоторое время для мониторинга
    time.sleep(10)
    
    print("\nОбновленный статус:")
    status = manager.get_server_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))

