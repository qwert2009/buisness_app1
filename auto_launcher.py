#!/usr/bin/env python3
"""
Автоматический запускатель Бизнес Менеджер Премиум+
Auto Launcher for Business Manager Premium+

Этот скрипт автоматически:
- Подбирает оптимальный сервер
- Обеспечивает стабильность работы
- Восстанавливает работу при сбоях
- Никогда не падает
"""
#!/usr/bin/env python3
"""
Auto Launcher for Business Manager Premium+
Автоматический запуск с подбором серверов и обеспечением стабильности
"""
import os
import sys
import time
import json
import socket
import subprocess
from pathlib import Path
import urllib.request

CONFIG_FILE = "server_config.json"
APP_FILE = "enhanced_app.py"
PYTHON_EXEC = sys.executable

DEFAULT_PORTS = [8501, 8502, 8503, 8504, 8505]

def load_server_config():
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    # Default config if not exists
    return {
        "servers": [
            {"name": "Default", "host": "0.0.0.0", "port": p, "priority": i+1, "max_connections": 100}
            for i, p in enumerate(DEFAULT_PORTS)
        ]
    }

def is_port_free(port, host="0.0.0.0"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False

def find_free_server(servers):
    for srv in sorted(servers, key=lambda x: x.get("priority", 1)):
        port = srv["port"]
        host = srv.get("host", "0.0.0.0")
        if is_port_free(port, host):
            return host, port
    return None, None

def start_streamlit_app(host, port):
    cmd = [PYTHON_EXEC, "-m", "streamlit", "run", APP_FILE, f"--server.port={port}", f"--server.address={host}"]
    print(f"Запуск приложения на {host}:{port} ...")
    return subprocess.Popen(cmd)

def wait_for_server(port, timeout=30):
    url = f"http://localhost:{port}/"
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False

def main():
    config = load_server_config()
    servers = config.get("servers", [])
    attempt = 0
    max_attempts = 20
    while attempt < max_attempts:
        host, port = find_free_server(servers)
        if host and port:
            proc = start_streamlit_app(host, port)
            print(f"Ожидание запуска сервера на http://localhost:{port} ...")
            if wait_for_server(port, timeout=40):
                print(f"Сервер успешно запущен: http://localhost:{port}")
                print(f"BROWSER_URL:http://localhost:{port}")
                # Ждем завершения процесса
                try:
                    proc.wait()
                except KeyboardInterrupt:
                    print("Остановка приложения пользователем.")
                    proc.terminate()
                    sys.exit(0)
                print(f"Приложение завершилось. Перезапуск через 3 секунды...")
                time.sleep(3)
                attempt += 1
            else:
                print(f"Сервер не поднялся на порту {port}, пробуем другой...")
                proc.terminate()
                time.sleep(2)
                attempt += 1
        else:
            print("Нет свободных портов для запуска. Ожидание 5 секунд...")
            time.sleep(5)
            attempt += 1
    print("Не удалось запустить приложение после нескольких попыток.")
    sys.exit(1)

if __name__ == "__main__":
    main()


