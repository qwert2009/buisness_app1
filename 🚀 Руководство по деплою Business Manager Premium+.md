# 🚀 Руководство по деплою Business Manager Premium+

## Быстрый старт

### 1. Автоматический деплой
```bash
python3 deploy.py
```

### 2. Ручная установка

#### Шаг 1: Установка зависимостей
```bash
pip3 install -r requirements.txt
```

#### Шаг 2: Настройка переменных окружения
Создайте файл `.env` и заполните необходимые параметры:
```bash
cp .env.example .env
nano .env
```

#### Шаг 3: Запуск приложения
```bash
streamlit run enhanced_app.py --server.port 8501 --server.address 0.0.0.0
```

## 🔧 Конфигурация

### Обязательные настройки

#### OpenAI API (для ИИ-функций)
```bash
export OPENAI_API_KEY="your-openai-api-key"
export OPENAI_API_BASE="https://api.openai.com/v1"
```

#### Администратор по умолчанию
- **Email:** alexkurumbayev@gmail.com
- **Пароль:** qwerty123G
- **⚠️ Обязательно смените пароль после первого входа!**

### Опциональные настройки

#### Email уведомления
```bash
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your-email@gmail.com"
export SMTP_PASSWORD="your-app-password"
```

#### Telegram Bot
```bash
export TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
```

#### WhatsApp API
```bash
export WHATSAPP_API_TOKEN="your-whatsapp-token"
export WHATSAPP_PHONE_ID="your-phone-id"
```

## 🐳 Docker деплой

### Быстрый запуск
```bash
docker-compose up -d
```

### Ручная сборка
```bash
docker build -t business-manager .
docker run -p 8501:8501 business-manager
```

## ☁️ Облачный деплой

### Streamlit Cloud
1. Загрузите код в GitHub репозиторий
2. Подключите репозиторий к Streamlit Cloud
3. Настройте переменные окружения в панели управления
4. Деплой произойдет автоматически

### Heroku
```bash
# Создание приложения
heroku create your-app-name

# Настройка переменных окружения
heroku config:set OPENAI_API_KEY=your-key
heroku config:set SECRET_KEY=your-secret-key

# Деплой
git push heroku main
```

### AWS EC2
```bash
# Подключение к серверу
ssh -i your-key.pem ubuntu@your-server-ip

# Установка зависимостей
sudo apt update
sudo apt install python3-pip nginx

# Клонирование репозитория
git clone your-repo-url
cd business-manager

# Запуск деплоя
python3 deploy.py

# Настройка nginx (опционально)
sudo cp nginx.conf /etc/nginx/sites-available/business-manager
sudo ln -s /etc/nginx/sites-available/business-manager /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

## 🔒 Безопасность

### SSL сертификат
```bash
# Использование Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Firewall настройки
```bash
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### Резервное копирование
```bash
# Автоматическое резервное копирование
crontab -e

# Добавить строку для ежедневного бэкапа в 2:00
0 2 * * * /path/to/business-manager/backup.sh
```

## 📊 Мониторинг

### Системные логи
```bash
# Просмотр логов приложения
tail -f logs/app.log

# Системные логи (если используется systemd)
sudo journalctl -u business-manager -f
```

### Мониторинг производительности
```bash
# Использование ресурсов
htop

# Дисковое пространство
df -h

# Сетевые соединения
netstat -tulpn | grep :8501
```

## 🔄 Обновления

### Обновление приложения
```bash
# Остановка сервиса
sudo systemctl stop business-manager

# Обновление кода
git pull origin main

# Установка новых зависимостей
pip3 install -r requirements.txt

# Миграция базы данных (если необходимо)
python3 migrate.py

# Запуск сервиса
sudo systemctl start business-manager
```

### Откат к предыдущей версии
```bash
# Восстановление из резервной копии
cd backups
unzip backup_YYYYMMDD_HHMMSS.zip -d ../rollback/
cd ../rollback
python3 deploy.py
```

## 🚨 Устранение неполадок

### Приложение не запускается
1. Проверьте логи: `tail -f logs/app.log`
2. Убедитесь, что порт 8501 свободен: `netstat -tulpn | grep :8501`
3. Проверьте переменные окружения: `env | grep OPENAI`

### База данных недоступна
1. Проверьте права доступа к файлу БД: `ls -la business_manager.db`
2. Пересоздайте БД: `rm business_manager.db && python3 -c "from enhanced_app import init_enhanced_db; init_enhanced_db()"`

### ИИ-функции не работают
1. Проверьте API ключ OpenAI: `echo $OPENAI_API_KEY`
2. Проверьте подключение к интернету: `ping api.openai.com`
3. Проверьте баланс на аккаунте OpenAI

### Медленная работа
1. Увеличьте ресурсы сервера (RAM, CPU)
2. Оптимизируйте базу данных: `python3 optimize_db.py`
3. Настройте кэширование

## 📞 Поддержка

### Техническая поддержка
- **Email:** support@businessmanager.com
- **Telegram:** @BusinessManagerSupport

### Документация
- **Основная документация:** README.md
- **API документация:** docs/api.md
- **FAQ:** docs/faq.md

### Сообщество
- **GitHub Issues:** github.com/your-repo/issues
- **Telegram чат:** t.me/BusinessManagerChat

## 📋 Чек-лист деплоя

### Перед деплоем
- [ ] Код протестирован локально
- [ ] Все зависимости указаны в requirements.txt
- [ ] Переменные окружения настроены
- [ ] Создана резервная копия данных
- [ ] SSL сертификат готов (для продакшена)

### После деплоя
- [ ] Приложение доступно по URL
- [ ] Вход администратора работает
- [ ] Все основные функции работают
- [ ] ИИ-функции активны (если настроены)
- [ ] Уведомления работают (если настроены)
- [ ] Мониторинг настроен
- [ ] Резервное копирование настроено

### Безопасность
- [ ] Пароль администратора изменен
- [ ] Firewall настроен
- [ ] SSL сертификат установлен
- [ ] Логирование включено
- [ ] Регулярные обновления настроены

---

**Удачного деплоя! 🚀**

