#!/bin/bash

# Бизнес Менеджер Премиум+ - Автоматический запуск
# Business Manager Premium+ - Auto Launcher

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Функция вывода баннера
show_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║        🚀 Бизнес Менеджер Премиум+ 🚀                       ║"
    echo "║                                                              ║"
    echo "║        Автоматический запуск с подбором серверов             ║"
    echo "║        и обеспечением стабильности работы                    ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Функция проверки Python
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python3 не найден${NC}"
        echo "   Пожалуйста, установите Python 3.8 или выше"
        return 1
    fi
    
    # Проверяем версию Python
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    required_version="3.8"
    
    if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
        echo -e "${RED}❌ Требуется Python $required_version или выше${NC}"
        echo "   Текущая версия: $python_version"
        return 1
    fi
    
    echo -e "${GREEN}✅ Python $python_version найден${NC}"
    return 0
}

# Функция проверки файлов
check_files() {
    if [ ! -f "enhanced_app.py" ]; then
        echo -e "${RED}❌ Файл enhanced_app.py не найден${NC}"
        echo "   Убедитесь, что вы находитесь в правильной директории"
        return 1
    fi
    
    echo -e "${GREEN}✅ Основные файлы найдены${NC}"
    return 0
}

# Функция создания директорий
create_directories() {
    directories=("logs" "backups" "uploads" "exports" "static")
    
    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
    done
    
    echo -e "${GREEN}📁 Директории созданы${NC}"
}

# Функция установки зависимостей
install_requirements() {
    if [ -f "requirements.txt" ]; then
        echo -e "${BLUE}📦 Установка зависимостей...${NC}"
        
        if python3 -m pip install -r requirements.txt; then
            echo -e "${GREEN}✅ Зависимости установлены${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠️  Ошибка установки зависимостей, продолжаем...${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️  Файл requirements.txt не найден${NC}"
        return 1
    fi
}

# Функция простого запуска
simple_start() {
    echo -e "${BLUE}🚀 Запуск в простом режиме...${NC}"
    
    # Определяем доступный порт
    port=8501
    while lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; do
        ((port++))
        if [ $port -gt 8520 ]; then
            echo -e "${RED}❌ Не удалось найти свободный порт${NC}"
            return 1
        fi
    done
    
    echo -e "${GREEN}🌐 Запуск на порту $port${NC}"
    echo -e "${CYAN}📱 Откройте в браузере: http://localhost:$port${NC}"
    echo -e "${YELLOW}⏹️  Для остановки нажмите Ctrl+C${NC}"
    echo ""
    
    python3 -m streamlit run enhanced_app.py \
        --server.port $port \
        --server.address 0.0.0.0 \
        --server.headless true
}

# Функция автоматического запуска
auto_start() {
    echo -e "${PURPLE}🤖 Запуск в автоматическом режиме...${NC}"
    
    if python3 start.py --auto; then
        return 0
    else
        echo -e "${YELLOW}⚠️  Ошибка автоматического режима, переключение на простой...${NC}"
        simple_start
        return $?
    fi
}

# Функция показа справки
show_help() {
    echo "Использование: $0 [ОПЦИЯ]"
    echo ""
    echo "Опции:"
    echo "  --auto, -a      Автоматический режим (по умолчанию)"
    echo "  --simple, -s    Простой режим запуска"
    echo "  --install, -i   Только установка зависимостей"
    echo "  --help, -h      Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0              # Автоматический режим"
    echo "  $0 --simple     # Простой режим"
    echo "  $0 --install    # Установка зависимостей"
    echo ""
}

# Функция установки как сервиса
install_service() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}❌ Для установки сервиса требуются права root${NC}"
        echo "   Запустите: sudo $0 --install-service"
        return 1
    fi
    
    service_file="/etc/systemd/system/business-manager.service"
    current_dir=$(pwd)
    current_user=$(logname)
    
    cat > "$service_file" << EOF
[Unit]
Description=Business Manager Premium+
After=network.target

[Service]
Type=simple
User=$current_user
WorkingDirectory=$current_dir
ExecStart=$current_dir/start.sh --auto
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable business-manager
    
    echo -e "${GREEN}✅ Сервис установлен${NC}"
    echo "   Для запуска: sudo systemctl start business-manager"
    echo "   Для просмотра логов: sudo journalctl -u business-manager -f"
}

# Функция обработки сигналов
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Получен сигнал завершения...${NC}"
    echo -e "${BLUE}👋 До свидания!${NC}"
    exit 0
}

# Устанавливаем обработчики сигналов
trap cleanup SIGINT SIGTERM

# Основная функция
main() {
    # Показываем баннер, если не указано --no-banner
    if [[ "$*" != *"--no-banner"* ]]; then
        show_banner
    fi
    
    # Обработка аргументов
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --install|-i)
            check_python || exit 1
            create_directories
            install_requirements
            exit $?
            ;;
        --install-service)
            install_service
            exit $?
            ;;
        --simple|-s)
            mode="simple"
            ;;
        --auto|-a|"")
            mode="auto"
            ;;
        *)
            echo -e "${RED}❌ Неизвестная опция: $1${NC}"
            show_help
            exit 1
            ;;
    esac
    
    # Проверки
    check_python || exit 1
    check_files || exit 1
    create_directories
    
    # Пытаемся установить зависимости
    install_requirements
    
    echo ""
    echo "══════════════════════════════════════════════════════════════"
    echo -e "${GREEN}🎯 Готов к запуску!${NC}"
    echo "══════════════════════════════════════════════════════════════"
    echo ""
    
    # Запуск в выбранном режиме
    case "$mode" in
        "simple")
            simple_start
            ;;
        "auto")
            auto_start
            ;;
    esac
    
    exit_code=$?
    
    echo ""
    echo -e "${BLUE}👋 Приложение завершено${NC}"
    exit $exit_code
}

# Запуск основной функции
main "$@"

