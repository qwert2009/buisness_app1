import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
import io
import base64
import time
from typing import Optional, List, Dict, Tuple, Any
import random
import string
import secrets
import uuid
from threading import Thread
import schedule
import openai

# Импортируем AI сервисы
from ai_services import ai_analytics, ai_assistant, automation_service
from chat_notification_service import chat_service, notification_service, customer_communication
from integration_service import integration_service, export_service
from ui_components import *
from mobile_pwa import initialize_mobile_pwa

# Настройка страницы
st.set_page_config(
    page_title="Бизнес Менеджер Премиум+",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Улучшенный CSS дизайн
st.markdown("""
<style>
    /* Основные стили */
    .main {
        padding: 1rem;
    }
    
    /* Гамбургер меню стили */
    .hamburger-menu {
        position: fixed;
        top: 10px;
        left: 10px;
        z-index: 1000;
        background: #1f77b4;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 10px;
        cursor: pointer;
        font-size: 18px;
    }
    
    .sidebar-menu {
        position: fixed;
        top: 0;
        left: -300px;
        width: 300px;
        height: 100vh;
        background: #f8f9fa;
        transition: left 0.3s ease;
        z-index: 999;
        padding: 20px;
        box-shadow: 2px 0 5px rgba(0,0,0,0.1);
        overflow-y: auto;
    }
    
    .sidebar-menu.open {
        left: 0;
    }
    
    .menu-item {
        display: block;
        padding: 12px 16px;
        margin: 5px 0;
        text-decoration: none;
        color: #333;
        border-radius: 5px;
        transition: background-color 0.3s;
    }
    
    .menu-item:hover {
        background-color: #e9ecef;
    }
    
    .menu-item.active {
        background-color: #1f77b4;
        color: white;
    }
    
    /* Карточки */
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 10px 0;
    }
    
    /* Премиум бейдж */
    .premium-badge {
        background: linear-gradient(45deg, #FFD700, #FFA500);
        color: #333;
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 12px;
        font-weight: bold;
        display: inline-block;
        margin-left: 10px;
    }
    
    /* Уведомления */
    .notification-badge {
        background: #dc3545;
        color: white;
        border-radius: 50%;
        padding: 2px 6px;
        font-size: 10px;
        position: absolute;
        top: -5px;
        right: -5px;
    }
    
    /* Чат стили */
    .chat-message {
        padding: 10px;
        margin: 5px 0;
        border-radius: 10px;
        max-width: 70%;
    }
    
    .chat-message.own {
        background: #1f77b4;
        color: white;
        margin-left: auto;
    }
    
    .chat-message.other {
        background: #f1f3f4;
        color: #333;
    }
    
    /* Скрытие стандартных элементов Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}
    
    /* Адаптивность */
    @media (max-width: 768px) {
        .main {
            padding: 0.5rem;
        }
        
        .sidebar-menu {
            width: 250px;
        }
    }
</style>
""", unsafe_allow_html=True)

# Инициализация OpenAI (если доступен API ключ)
try:
    openai.api_key = os.getenv("OPENAI_API_KEY")
except:
    pass

# Расширенная инициализация базы данных
def init_enhanced_db():
    conn = sqlite3.connect('business_manager.db')
    cursor = conn.cursor()
    
    # Базовые таблицы (из оригинального кода)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            phone TEXT,
            full_name TEXT,
            business_name TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            premium_status BOOLEAN DEFAULT FALSE,
            premium_start_date TIMESTAMP,
            premium_end_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            avatar_url TEXT,
            timezone TEXT DEFAULT 'UTC'
        )
    ''')
    
    # Добавляем новые поля к существующим таблицам
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'UTC'")
    except sqlite3.OperationalError:
        pass
    
    # Таблица для детальных прав доступа
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            permission_type TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            granted_by INTEGER,
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id),
            FOREIGN KEY (granted_by) REFERENCES users (id)
        )
    ''')
    
    # Таблица для приглашений в команду
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_invitations (
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
        )
    ''')
    
    # Таблица компаний (если не существует)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            logo_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
    ''')
    
    # Связь пользователей с компаниями
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_companies (
            user_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, company_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    # Таблица для ИИ прогнозов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_id INTEGER,
            prediction_type TEXT NOT NULL,
            prediction_data TEXT NOT NULL,
            confidence_score REAL,
            period_start DATE,
            period_end DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    # Таблица для автоматизированных задач
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS automation_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_id INTEGER,
            task_type TEXT NOT NULL,
            task_config TEXT NOT NULL,
            schedule_pattern TEXT,
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    # Таблица для ИИ рекомендаций
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_id INTEGER,
            recommendation_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            action_data TEXT,
            priority INTEGER DEFAULT 1,
            is_read BOOLEAN DEFAULT FALSE,
            is_applied BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    # Таблица для чат-каналов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            is_private BOOLEAN DEFAULT FALSE,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')
    
    # Участники каналов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channel_members (
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            role TEXT DEFAULT 'member',
            PRIMARY KEY (channel_id, user_id),
            FOREIGN KEY (channel_id) REFERENCES chat_channels (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица сообщений чата
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            channel_id INTEGER,
            receiver_id INTEGER,
            company_id INTEGER,
            message TEXT NOT NULL,
            message_type TEXT DEFAULT 'text',
            file_url TEXT,
            is_edited BOOLEAN DEFAULT FALSE,
            edited_at TIMESTAMP,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users (id),
            FOREIGN KEY (channel_id) REFERENCES chat_channels (id),
            FOREIGN KEY (receiver_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    # Настройки уведомлений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            delivery_method TEXT NOT NULL,
            is_enabled BOOLEAN DEFAULT TRUE,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица для внешних интеграций
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS integrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_id INTEGER,
            integration_type TEXT NOT NULL,
            config_data TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            last_sync TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    # Двухфакторная аутентификация
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_2fa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            secret_key TEXT NOT NULL,
            backup_codes TEXT,
            is_enabled BOOLEAN DEFAULT FALSE,
            enabled_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Добавляем админ пользователя
    cursor.execute('SELECT * FROM users WHERE email = ?', ('alexkurumbayev@gmail.com',))
    if cursor.fetchone() is None:
        admin_password_hash = hashlib.sha256('qwerty123G'.encode()).hexdigest()
        cursor.execute(
            "INSERT INTO users (email, password_hash, full_name, is_admin, premium_status) VALUES (?, ?, ?, ?, ?)",
            ('alexkurumbayev@gmail.com', admin_password_hash, 'Alex Kurumbayev', True, True)
        )
        conn.commit()
    
    conn.commit()
    conn.close()

# Функции для работы с базой данных
def get_db_connection():
    conn = sqlite3.connect('business_manager.db')
    conn.row_factory = sqlite3.Row
    return conn

def authenticate_user(email, password):
    """Аутентификация пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    cursor.execute("SELECT * FROM users WHERE email = ? AND password_hash = ?", (email, password_hash))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(email, password, full_name=None, phone=None):
    """Создание нового пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        cursor.execute(
            "INSERT INTO users (email, password_hash, full_name, phone) VALUES (?, ?, ?, ?)",
            (email, password_hash, full_name, phone)
        )
        conn.commit()
        user_id = cursor.lastrowid
        
        # Создаем компанию по умолчанию для нового пользователя
        company_name = f"Компания {full_name or email.split('@')[0]}"
        cursor.execute("INSERT INTO companies (owner_id, name) VALUES (?, ?)", (user_id, company_name))
        conn.commit()
        company_id = cursor.lastrowid
        
        # Добавляем пользователя в компанию как владельца
        cursor.execute("INSERT INTO user_companies (user_id, company_id, role) VALUES (?, ?, ?)", 
                      (user_id, company_id, 'owner'))
        conn.commit()
        
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_user_companies(user_id):
    """Получение компаний пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.description, uc.role, c.logo_url
        FROM companies c 
        JOIN user_companies uc ON c.id = uc.company_id 
        WHERE uc.user_id = ?
        ORDER BY uc.joined_at DESC
    """, (user_id,))
    companies = cursor.fetchall()
    conn.close()
    return companies

def create_company(owner_id, name, description=None):
    """Создание новой компании"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO companies (owner_id, name, description) VALUES (?, ?, ?)", 
                  (owner_id, name, description))
    conn.commit()
    company_id = cursor.lastrowid
    
    # Добавляем владельца в user_companies
    cursor.execute("INSERT INTO user_companies (user_id, company_id, role) VALUES (?, ?, ?)", 
                  (owner_id, company_id, 'owner'))
    conn.commit()
    conn.close()
    return company_id

def invite_user_to_company(company_id, email, role, invited_by):
    """Приглашение пользователя в команду"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Генерируем токен приглашения
    invitation_token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=7)  # Приглашение действует 7 дней
    
    cursor.execute("""
        INSERT INTO team_invitations (company_id, email, role, invited_by, invitation_token, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (company_id, email, role, invited_by, invitation_token, expires_at))
    conn.commit()
    conn.close()
    
    return invitation_token

def accept_invitation(invitation_token, user_id):
    """Принятие приглашения в команду"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем приглашение
    cursor.execute("""
        SELECT * FROM team_invitations 
        WHERE invitation_token = ? AND expires_at > CURRENT_TIMESTAMP AND accepted_at IS NULL
    """, (invitation_token,))
    invitation = cursor.fetchone()
    
    if not invitation:
        conn.close()
        return False
    
    # Добавляем пользователя в компанию
    try:
        cursor.execute("INSERT INTO user_companies (user_id, company_id, role) VALUES (?, ?, ?)",
                      (user_id, invitation['company_id'], invitation['role']))
        
        # Отмечаем приглашение как принятое
        cursor.execute("UPDATE team_invitations SET accepted_at = CURRENT_TIMESTAMP WHERE id = ?",
                      (invitation['id'],))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_company_team_members(company_id):
    """Получение участников команды компании"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.email, u.full_name, u.avatar_url, uc.role, uc.joined_at
        FROM users u 
        JOIN user_companies uc ON u.id = uc.user_id 
        WHERE uc.company_id = ?
        ORDER BY uc.joined_at DESC
    """, (company_id,))
    members = cursor.fetchall()
    conn.close()
    return members

def update_user_role_in_company(user_id, company_id, new_role):
    """Обновление роли пользователя в компании"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE user_companies SET role = ? WHERE user_id = ? AND company_id = ?",
                  (new_role, user_id, company_id))
    conn.commit()
    conn.close()

def remove_user_from_company(user_id, company_id):
    """Удаление пользователя из компании"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_companies WHERE user_id = ? AND company_id = ?",
                  (user_id, company_id))
    conn.commit()
    conn.close()

def switch_user_context(user_id, target_user_id, company_id):
    """Переключение контекста пользователя (имперсонация)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем права на переключение
    cursor.execute("""
        SELECT uc.role FROM user_companies uc 
        WHERE uc.user_id = ? AND uc.company_id = ? AND uc.role IN ('owner', 'admin')
    """, (user_id, company_id))
    
    if cursor.fetchone():
        # Проверяем, что целевой пользователь есть в компании
        cursor.execute("SELECT * FROM user_companies WHERE user_id = ? AND company_id = ?",
                      (target_user_id, company_id))
        if cursor.fetchone():
            conn.close()
            return True
    
    conn.close()
    return False

def generate_ai_business_idea(prompt, user_id):
    """Генерация бизнес-идеи с помощью ИИ"""
    try:
        if not openai.api_key:
            # Заглушка для демонстрации
            ideas = [
                f"💡 **Инновационное решение для '{prompt}':**\n\n1. Создайте SaaS-платформу для автоматизации процессов в вашей сфере\n2. Разработайте мобильное приложение с ИИ-помощником\n3. Запустите онлайн-курсы по вашей экспертизе\n4. Создайте маркетплейс для специалистов отрасли",
                f"🚀 **Стратегия роста для '{prompt}':**\n\n1. Внедрите систему лояльности клиентов\n2. Автоматизируйте email-маркетинг\n3. Создайте партнерскую программу\n4. Разработайте API для интеграций",
                f"📈 **Оптимизация бизнеса '{prompt}':**\n\n1. Внедрите CRM-систему\n2. Автоматизируйте отчетность\n3. Оптимизируйте складские процессы\n4. Создайте систему аналитики"
            ]
            generated_idea = random.choice(ideas)
        else:
            # Реальный вызов OpenAI API
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты эксперт по бизнесу. Генерируй практичные и инновационные бизнес-идеи."},
                    {"role": "user", "content": f"Сгенерируй бизнес-идею для: {prompt}"}
                ],
                max_tokens=500,
                temperature=0.7
            )
            generated_idea = response.choices[0].message.content
        
        # Сохраняем идею в базу
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ai_ideas (user_id, idea_text) VALUES (?, ?)",
                      (user_id, generated_idea))
        conn.commit()
        conn.close()
        
        return generated_idea
    except Exception as e:
        return f"Ошибка генерации идеи: {str(e)}"

def get_user_ai_ideas(user_id, limit=10):
    """Получение ИИ идей пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ai_ideas WHERE user_id = ? ORDER BY generated_at DESC LIMIT ?",
                  (user_id, limit))
    ideas = cursor.fetchall()
    conn.close()
    return ideas

# Компоненты интерфейса
def show_hamburger_menu():
    """Отображение гамбургер меню"""
    if 'menu_open' not in st.session_state:
        st.session_state.menu_open = False
    
    # JavaScript для управления меню
    menu_js = """
    <script>
    function toggleMenu() {
        const menu = document.querySelector('.sidebar-menu');
        const isOpen = menu.classList.contains('open');
        if (isOpen) {
            menu.classList.remove('open');
        } else {
            menu.classList.add('open');
        }
    }
    
    // Закрытие меню при клике вне его
    document.addEventListener('click', function(event) {
        const menu = document.querySelector('.sidebar-menu');
        const hamburger = document.querySelector('.hamburger-menu');
        if (!menu.contains(event.target) && !hamburger.contains(event.target)) {
            menu.classList.remove('open');
        }
    });
    </script>
    """
    
    # HTML для меню
    menu_html = f"""
    <button class="hamburger-menu" onclick="toggleMenu()">☰</button>
    <div class="sidebar-menu">
        <h3>Бизнес Менеджер <span class="premium-badge">ПРЕМИУМ+</span></h3>
        <hr>
        <div class="menu-section">
            <h4>Основное</h4>
            <a href="#" class="menu-item" onclick="setPage('dashboard')">📊 Панель управления</a>
            <a href="#" class="menu-item" onclick="setPage('orders')">📦 Заказы</a>
            <a href="#" class="menu-item" onclick="setPage('inventory')">🏪 Склад</a>
            <a href="#" class="menu-item" onclick="setPage('analytics')">📈 Аналитика</a>
        </div>
        <hr>
        <div class="menu-section">
            <h4>Премиум функции</h4>
            <a href="#" class="menu-item" onclick="setPage('ai_features')">🧠 ИИ-функции</a>
            <a href="#" class="menu-item" onclick="setPage('chat')">💬 Корп. чат</a>
            <a href="#" class="menu-item" onclick="setPage('automation')">🔄 Автоматизация</a>
            <a href="#" class="menu-item" onclick="setPage('integrations')">🔗 Интеграции</a>
        </div>
        <hr>
        <div class="menu-section">
            <h4>Управление</h4>
            <a href="#" class="menu-item" onclick="setPage('companies')">🏢 Компании</a>
            <a href="#" class="menu-item" onclick="setPage('team')">👥 Команда</a>
            <a href="#" class="menu-item" onclick="setPage('settings')">⚙️ Настройки</a>
        </div>
        """ + ("<hr><div class='menu-section'><h4>Администрирование</h4><a href='#' class='menu-item' onclick='setPage(\"admin\")'>👨‍💼 Админ панель</a></div>" if st.session_state.get('is_admin') else "") + """
    </div>
    """ + menu_js + """
    """
    
    st.markdown(menu_html, unsafe_allow_html=True)

def show_login_page():
    """Страница входа"""
    st.title("🚀 Бизнес Менеджер Премиум+")
    st.markdown("### Войдите в систему")
    
    tab1, tab2 = st.tabs(["Вход", "Регистрация"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти")
            
            if submitted:
                user = authenticate_user(email, password)
                if user:
                    st.session_state.user_id = user['id']
                    st.session_state.user_email = user['email']
                    st.session_state.user_name = user['full_name']
                    st.session_state.is_admin = user['is_admin']
                    st.session_state.premium_status = user['premium_status']
                    st.session_state.logged_in = True
                    
                    # Устанавливаем активную компанию
                    companies = get_user_companies(user['id'])
                    if companies:
                        st.session_state.active_company_id = companies[0]['id']
                    
                    st.success("Успешный вход!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    
    with tab2:
        with st.form("register_form"):
            reg_email = st.text_input("Email", key="reg_email")
            reg_password = st.text_input("Пароль", type="password", key="reg_password")
            reg_full_name = st.text_input("Полное имя", key="reg_full_name")
            reg_phone = st.text_input("Телефон (необязательно)", key="reg_phone")
            reg_submitted = st.form_submit_button("Зарегистрироваться")
            
            if reg_submitted:
                if create_user(reg_email, reg_password, reg_full_name, reg_phone):
                    st.success("Регистрация успешна! Теперь вы можете войти.")
                else:
                    st.error("Пользователь с таким email уже существует")

def show_dashboard():
    """Главная панель управления с улучшенным дизайном"""
    create_custom_header("📊 Дашборд", "Обзор вашего бизнеса")
    
    user_id = st.session_state.user_id
    company_id = st.session_state.get('active_company_id')
    
    if not company_id:
        create_notification("Выберите активную компанию для просмотра дашборда", "warning")
        return
    
    # Селектор компаний
    create_company_selector()
    
    # Получаем статистику
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Общая статистика
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND company_id = ?", (user_id, company_id))
    total_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(total_amount) FROM orders WHERE user_id = ? AND company_id = ?", (user_id, company_id))
    total_revenue = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM customers WHERE company_id = ?", (company_id,))
    total_customers = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM inventory WHERE user_id = ? AND company_id = ? AND quantity <= min_stock", (user_id, company_id))
    low_stock_items = cursor.fetchone()[0]
    
    conn.close()
    
    # Создаем сетку метрик
    stats_data = [
        ("Всего заказов", str(total_orders), "+12%", "positive"),
        ("Выручка", f"₽{total_revenue:,.0f}", "+8%", "positive"),
        ("Клиенты", str(total_customers), "+5%", "positive"),
        ("Низкие остатки", str(low_stock_items), "-2", "negative" if low_stock_items > 0 else "positive")
    ]
    
    create_stats_grid(stats_data)
    
    # Графики и аналитика
    col1, col2 = st.columns(2)
    
    with col1:
        # График продаж
        sales_data = ai_analytics.generate_sales_forecast(user_id, company_id, 30)
        if sales_data:
            fig = px.line(
                x=list(range(len(sales_data))), 
                y=sales_data,
                title="Прогноз продаж на 30 дней",
                labels={'x': 'Дни', 'y': 'Продажи'}
            )
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='#333'
            )
            create_chart_container(fig, "📈 Прогноз продаж")
    
    with col2:
        # Топ товары
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.name, SUM(oi.quantity) as sold
            FROM order_items oi
            JOIN inventory i ON oi.inventory_id = i.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.user_id = ? AND o.company_id = ?
            GROUP BY i.name
            ORDER BY sold DESC
            LIMIT 5
        """, (user_id, company_id))
        
        top_products = cursor.fetchall()
        conn.close()
        
        if top_products:
            products = [p[0] for p in top_products]
            quantities = [p[1] for p in top_products]
            
            fig = px.bar(
                x=quantities,
                y=products,
                orientation='h',
                title="Топ-5 товаров",
                labels={'x': 'Продано', 'y': 'Товары'}
            )
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='#333'
            )
            create_chart_container(fig, "🏆 Популярные товары")
    
    # Быстрые действия
    st.markdown("### 🚀 Быстрые действия")
    
    action_buttons = [
        ("📦 Новый заказ", "new_order"),
        ("👥 Добавить клиента", "new_customer"),
        ("📋 Пополнить склад", "add_inventory"),
        ("📊 Отчет", "generate_report")
    ]
    
    selected_action = create_action_buttons(action_buttons)
    
    if selected_action:
        if selected_action == "new_order":
            st.session_state.page = 'orders'
            st.rerun()
        elif selected_action == "new_customer":
            st.session_state.page = 'customers'
            st.rerun()
        elif selected_action == "add_inventory":
            st.session_state.page = 'inventory'
            st.rerun()
        elif selected_action == "generate_report":
            create_notification("Генерация отчета...", "info")
    
    # Последние заказы
    st.markdown("### 📋 Последние заказы")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, created_at, customer_name, total_amount, status
        FROM orders 
        WHERE user_id = ? AND company_id = ?
        ORDER BY created_at DESC 
        LIMIT 5
    """, (user_id, company_id))
    
    recent_orders = cursor.fetchall()
    conn.close()
    
    if recent_orders:
        df = pd.DataFrame(recent_orders, columns=['ID', 'Дата', 'Клиент', 'Сумма', 'Статус'])
        df['Дата'] = pd.to_datetime(df['Дата']).dt.strftime('%d.%m.%Y %H:%M')
        df['Сумма'] = df['Сумма'].apply(lambda x: f"₽{x:,.0f}")
        
        create_data_table(df, "Последние заказы")
    else:
        create_notification("Заказов пока нет", "info")
    
    # Уведомления и задачи
    if st.session_state.get('premium_status'):
        st.markdown("### 🔔 Уведомления")
        
        # Проверяем низкие остатки
        if low_stock_items > 0:
            create_notification(f"⚠️ {low_stock_items} товаров с низким остатком на складе", "warning")
        
        # AI рекомендации
        recommendations = ai_assistant.get_business_recommendations(user_id, company_id)
        if recommendations:
            st.markdown("### 🤖 AI Рекомендации")
            for rec in recommendations[:3]:  # Показываем только первые 3
                create_notification(f"💡 {rec}", "info")
    else:
        create_premium_feature_lock("AI Рекомендации и Уведомления")

def show_ai_features():
    """ИИ функции"""
    st.title("🧠 ИИ-функции Премиум+")
    
    if not st.session_state.get('premium_status'):
        st.warning("ИИ-функции доступны только для Премиум+ пользователей")
        return
    
    user_id = st.session_state.user_id
    company_id = st.session_state.get('active_company_id')
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Генератор идей", "ИИ-Ассистент", "Прогнозы", "Рекомендации", "Автоматизация"])
    
    with tab1:
        st.subheader("🚀 AI-генератор бизнес-идей")
        
        idea_prompt = st.text_area(
            "Опишите вашу задачу или сферу деятельности:",
            placeholder="Например: 'нужна идея для увеличения продаж в интернет-магазине одежды'"
        )
        
        if st.button("Сгенерировать идею", type="primary"):
            if idea_prompt:
                with st.spinner("Генерируем идею..."):
                    idea = generate_ai_business_idea(idea_prompt, user_id)
                    st.markdown(idea)
            else:
                st.warning("Пожалуйста, опишите вашу задачу")
        
        # Показываем предыдущие идеи
        st.subheader("📝 Ваши сгенерированные идеи")
        ideas = get_user_ai_ideas(user_id)
        
        for idea in ideas:
            with st.expander(f"Идея от {idea['generated_at'][:16]}"):
                st.markdown(idea['idea_text'])
    
    with tab2:
        st.subheader("🤖 AI-ассистент 24/7")
        
        # Генерация документов
        st.markdown("### Генерация бизнес-документов")
        
        col1, col2 = st.columns(2)
        with col1:
            doc_type = st.selectbox("Тип документа", [
                "business_plan", "marketing_strategy", "sales_report", 
                "job_description", "contract_template"
            ], format_func=lambda x: {
                "business_plan": "Бизнес-план",
                "marketing_strategy": "Маркетинговая стратегия", 
                "sales_report": "Отчет по продажам",
                "job_description": "Описание вакансии",
                "contract_template": "Шаблон договора"
            }[x])
        
        with col2:
            if st.button("Сгенерировать документ"):
                context = {
                    'company_name': 'Моя компания',
                    'industry': 'услуги',
                    'budget': '100000'
                }
                
                with st.spinner("Генерируем документ..."):
                    document = ai_assistant.generate_business_document(doc_type, context)
                    st.markdown(document)
        
        # Чат с ассистентом
        st.markdown("### Задать вопрос ассистенту")
        
        if 'chat_messages' not in st.session_state:
            st.session_state.chat_messages = []
        
        user_question = st.text_input("Ваш вопрос:")
        if st.button("Отправить вопрос"):
            if user_question:
                st.session_state.chat_messages.append({"role": "user", "content": user_question})
                
                with st.spinner("Получаем ответ..."):
                    answer = ai_assistant.answer_business_question(user_question)
                    st.session_state.chat_messages.append({"role": "assistant", "content": answer})
        
        # Отображение чата
        for msg in st.session_state.chat_messages[-10:]:  # Показываем последние 10 сообщений
            if msg["role"] == "user":
                st.markdown(f"**Вы:** {msg['content']}")
            else:
                st.markdown(f"**Ассистент:** {msg['content']}")
    
    with tab3:
        st.subheader("📈 ИИ-прогнозы и аналитика")
        
        if company_id:
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Прогноз продаж"):
                    with st.spinner("Генерируем прогноз..."):
                        forecast = ai_analytics.generate_sales_forecast(user_id, company_id, 30)
                        
                        st.markdown("### Прогноз продаж на 30 дней")
                        
                        # График прогноза
                        df_forecast = pd.DataFrame({
                            'Дата': forecast['dates'],
                            'Прогноз продаж': forecast['forecast']
                        })
                        
                        fig = px.line(df_forecast, x='Дата', y='Прогноз продаж', 
                                     title="Прогноз продаж")
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Метрики
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.metric("Общий прогноз", f"₽{forecast['total_predicted']:,.0f}")
                        with col_b:
                            st.metric("Тренд", forecast['trend'])
                        with col_c:
                            st.metric("Точность", f"{forecast['confidence_score']*100:.0f}%")
            
            with col2:
                if st.button("Анализ клиентов"):
                    with st.spinner("Анализируем клиентов..."):
                        insights = ai_analytics.generate_customer_insights(user_id, company_id)
                        
                        if 'segments' in insights:
                            st.markdown("### Сегментация клиентов")
                            
                            # Диаграмма сегментов
                            segments_df = pd.DataFrame(list(insights['segments'].items()), 
                                                     columns=['Сегмент', 'Количество'])
                            
                            fig = px.pie(segments_df, values='Количество', names='Сегмент',
                                       title="Распределение клиентов по сегментам")
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Метрики
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.metric("Всего клиентов", insights['total_customers'])
                            with col_b:
                                st.metric("Средний LTV", f"₽{insights['average_ltv']:,.0f}")
                            
                            # Рекомендации
                            if insights.get('recommendations'):
                                st.markdown("### Рекомендации")
                                for rec in insights['recommendations']:
                                    st.info(f"**{rec['title']}**: {rec['description']}")
                        else:
                            st.info(insights.get('message', 'Нет данных для анализа'))
        else:
            st.warning("Выберите активную компанию для получения прогнозов")
    
    with tab4:
        st.subheader("💡 ИИ-рекомендации")
        
        if company_id:
            if st.button("Получить рекомендации по складу"):
                with st.spinner("Анализируем склад..."):
                    recommendations = ai_analytics.generate_inventory_recommendations(user_id, company_id)
                    
                    if recommendations:
                        for rec in recommendations:
                            priority_colors = {
                                'high': '🔴',
                                'medium': '🟡', 
                                'low': '🟢'
                            }
                            
                            priority_icon = priority_colors.get(rec['priority'], '⚪')
                            
                            with st.expander(f"{priority_icon} {rec['title']}"):
                                st.write(rec['description'])
                                
                                if rec.get('suggested_quantity'):
                                    st.info(f"Рекомендуемое количество: {rec['suggested_quantity']} единиц")
                                
                                if st.button(f"Применить", key=f"apply_{rec.get('product_id', random.randint(1000, 9999))}"):
                                    st.success("Рекомендация применена!")
                    else:
                        st.info("Рекомендации не найдены. Возможно, нужно больше данных о товарах.")
            
            # Показываем сохраненные рекомендации
            st.markdown("### Последние рекомендации")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ai_recommendations 
                WHERE user_id = ? AND company_id = ?
                ORDER BY created_at DESC LIMIT 5
            """, (user_id, company_id))
            saved_recs = cursor.fetchall()
            conn.close()
            
            for rec in saved_recs:
                with st.expander(f"{rec['title']} - {rec['created_at'][:16]}"):
                    st.write(rec['description'])
                    if not rec['is_read']:
                        if st.button("Отметить как прочитанное", key=f"read_{rec['id']}"):
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            cursor.execute("UPDATE ai_recommendations SET is_read = 1 WHERE id = ?", (rec['id'],))
                            conn.commit()
                            conn.close()
                            st.rerun()
        else:
            st.warning("Выберите активную компанию для получения рекомендаций")
    
    with tab5:
        st.subheader("🔄 Автоматизация бизнес-процессов")
        
        if company_id:
            # Создание новой автоматизированной задачи
            st.markdown("### Создать автоматизированную задачу")
            
            with st.form("automation_form"):
                task_type = st.selectbox("Тип задачи", [
                    "auto_report", "stock_reminder", "customer_followup", "backup"
                ], format_func=lambda x: {
                    "auto_report": "Автоматический отчет",
                    "stock_reminder": "Напоминание о складских остатках",
                    "customer_followup": "Follow-up с клиентами",
                    "backup": "Резервное копирование"
                }[x])
                
                schedule_pattern = st.selectbox("Расписание", [
                    "daily", "weekly", "monthly"
                ], format_func=lambda x: {
                    "daily": "Ежедневно",
                    "weekly": "Еженедельно", 
                    "monthly": "Ежемесячно"
                }[x])
                
                task_config = st.text_area("Настройки (JSON)", value='{"enabled": true}')
                
                if st.form_submit_button("Создать задачу"):
                    try:
                        config = json.loads(task_config)
                        task_id = automation_service.create_automation_task(
                            user_id, company_id, task_type, config, schedule_pattern
                        )
                        st.success(f"Задача создана с ID: {task_id}")
                    except json.JSONDecodeError:
                        st.error("Неверный формат JSON в настройках")
            
            # Показываем существующие задачи
            st.markdown("### Активные автоматизированные задачи")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM automation_tasks 
                WHERE user_id = ? AND company_id = ? AND is_active = 1
                ORDER BY created_at DESC
            """, (user_id, company_id))
            tasks = cursor.fetchall()
            conn.close()
            
            if tasks:
                for task in tasks:
                    with st.expander(f"{task['task_type']} - {task['schedule_pattern']}"):
                        col_a, col_b, col_c = st.columns(3)
                        
                        with col_a:
                            st.write(f"**Создана:** {task['created_at'][:16]}")
                        with col_b:
                            st.write(f"**Последний запуск:** {task['last_run'][:16] if task['last_run'] else 'Никогда'}")
                        with col_c:
                            st.write(f"**Следующий запуск:** {task['next_run'][:16] if task['next_run'] else 'Не запланирован'}")
                        
                        if st.button(f"Выполнить сейчас", key=f"run_{task['id']}"):
                            if automation_service.execute_automation_task(task['id']):
                                st.success("Задача выполнена!")
                            else:
                                st.error("Ошибка выполнения задачи")
            else:
                st.info("Нет активных автоматизированных задач")
        else:
            st.warning("Выберите активную компанию для настройки автоматизации")

def show_team_management():
    """Управление командой"""
    st.title("👥 Управление командой")
    
    company_id = st.session_state.get('active_company_id')
    if not company_id:
        st.warning("Выберите компанию для управления командой")
        return
    
    # Получаем информацию о компании
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
    company = cursor.fetchone()
    conn.close()
    
    if not company:
        st.error("Компания не найдена")
        return
    
    st.subheader(f"Команда компании: {company['name']}")
    
    # Показываем участников команды
    team_members = get_company_team_members(company_id)
    
    if team_members:
        st.markdown("### Участники команды")
        
        for member in team_members:
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
            
            with col1:
                avatar = "👤" if not member['avatar_url'] else "🖼️"
                st.markdown(f"{avatar} **{member['full_name'] or member['email']}**")
                st.caption(member['email'])
            
            with col2:
                role_colors = {
                    'owner': '🔴',
                    'admin': '🟠', 
                    'editor': '🟡',
                    'viewer': '🟢'
                }
                st.markdown(f"{role_colors.get(member['role'], '⚪')} {member['role'].title()}")
            
            with col3:
                st.caption(f"С {member['joined_at'][:10]}")
            
            with col4:
                if member['id'] != st.session_state.user_id:
                    if st.button("Управление", key=f"manage_{member['id']}"):
                        st.session_state.selected_member = member['id']
    
    # Приглашение нового участника
    st.markdown("### Пригласить в команду")
    
    with st.form("invite_form"):
        invite_email = st.text_input("Email пользователя")
        invite_role = st.selectbox("Роль", ["viewer", "editor", "admin"])
        invite_message = st.text_area("Сообщение (необязательно)")
        
        if st.form_submit_button("Отправить приглашение"):
            if invite_email:
                token = invite_user_to_company(
                    company_id, 
                    invite_email, 
                    invite_role, 
                    st.session_state.user_id
                )
                st.success(f"Приглашение отправлено на {invite_email}")
                st.info(f"Токен приглашения: {token}")
            else:
                st.error("Введите email пользователя")
    
    # Переключение между аккаунтами участников (для владельцев и админов)
    user_role = None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM user_companies WHERE user_id = ? AND company_id = ?",
                  (st.session_state.user_id, company_id))
    result = cursor.fetchone()
    if result:
        user_role = result['role']
    conn.close()
    
    if user_role in ['owner', 'admin']:
        st.markdown("### Переключение между аккаунтами")
        
        switch_options = {f"{m['full_name'] or m['email']} ({m['email']})": m['id'] 
                         for m in team_members if m['id'] != st.session_state.user_id}
        
        if switch_options:
            selected_user = st.selectbox("Выберите пользователя для переключения", 
                                       list(switch_options.keys()))
            
            if st.button("Переключиться на аккаунт"):
                target_user_id = switch_options[selected_user]
                if switch_user_context(st.session_state.user_id, target_user_id, company_id):
                    st.session_state.impersonated_user_id = target_user_id
                    st.session_state.original_user_id = st.session_state.user_id
                    st.success(f"Переключились на аккаунт: {selected_user}")
                    st.info("Для возврата к своему аккаунту используйте кнопку 'Вернуться' в настройках")
                else:
                    st.error("Не удалось переключиться на аккаунт")

def show_companies_management():
    """Управление компаниями (мультибизнес)"""
    st.title("🏢 Управление компаниями")
    
    if not st.session_state.get('premium_status'):
        st.warning("Функция мультибизнеса доступна только для Премиум+ пользователей")
        return
    
    user_id = st.session_state.user_id
    companies = get_user_companies(user_id)
    
    # Показываем список компаний
    st.subheader("Ваши компании")
    
    if companies:
        for company in companies:
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
            
            with col1:
                logo = "🏢" if not company['logo_url'] else "🖼️"
                st.markdown(f"{logo} **{company['name']}**")
                if company['description']:
                    st.caption(company['description'])
            
            with col2:
                role_colors = {
                    'owner': '👑',
                    'admin': '⭐', 
                    'editor': '✏️',
                    'viewer': '👁️'
                }
                st.markdown(f"{role_colors.get(company['role'], '❓')} {company['role'].title()}")
            
            with col3:
                is_active = st.session_state.get('active_company_id') == company['id']
                if is_active:
                    st.success("Активна")
                else:
                    if st.button("Активировать", key=f"activate_{company['id']}"):
                        st.session_state.active_company_id = company['id']
                        st.success(f"Активирована компания: {company['name']}")
                        st.rerun()
            
            with col4:
                if st.button("Управление", key=f"manage_company_{company['id']}"):
                    st.session_state.selected_company = company['id']
    
    # Создание новой компании
    st.subheader("Создать новую компанию")
    
    with st.form("create_company_form"):
        company_name = st.text_input("Название компании")
        company_description = st.text_area("Описание (необязательно)")
        
        if st.form_submit_button("Создать компанию"):
            if company_name:
                new_company_id = create_company(user_id, company_name, company_description)
                st.success(f"Компания '{company_name}' создана!")
                st.rerun()
            else:
                st.error("Введите название компании")

def show_corporate_chat():
    """Корпоративный чат"""
    st.title("💬 Корпоративный чат")
    
    if not st.session_state.get('premium_status'):
        st.warning("Корпоративный чат доступен только для Премиум+ пользователей")
        return
    
    user_id = st.session_state.user_id
    company_id = st.session_state.get('active_company_id')
    
    if not company_id:
        st.warning("Выберите активную компанию для использования чата")
        return
    
    # Боковая панель с каналами и контактами
    with st.sidebar:
        st.subheader("Каналы и чаты")
        
        # Создание нового канала
        with st.expander("Создать канал"):
            with st.form("create_channel"):
                channel_name = st.text_input("Название канала")
                channel_description = st.text_area("Описание")
                is_private = st.checkbox("Приватный канал")
                
                if st.form_submit_button("Создать"):
                    if channel_name:
                        channel_id = chat_service.create_channel(
                            company_id, channel_name, channel_description, is_private, user_id
                        )
                        st.success(f"Канал '{channel_name}' создан!")
                        st.rerun()
                    else:
                        st.error("Введите название канала")
        
        # Список каналов
        channels = chat_service.get_user_channels(user_id, company_id)
        
        st.markdown("### Каналы")
        for channel in channels:
            channel_icon = "🔒" if channel['is_private'] else "📢"
            unread_count = ""  # Здесь можно добавить подсчет непрочитанных
            
            if st.button(f"{channel_icon} {channel['name']} {unread_count}", 
                        key=f"channel_{channel['id']}"):
                st.session_state.active_chat_type = 'channel'
                st.session_state.active_chat_id = channel['id']
                st.session_state.active_chat_name = channel['name']
                st.rerun()
        
        # Список участников команды для личных сообщений
        st.markdown("### Участники команды")
        team_members = get_company_team_members(company_id)
        
        for member in team_members:
            if member['id'] != user_id:  # Не показываем себя
                member_name = member['full_name'] or member['email']
                if st.button(f"👤 {member_name}", key=f"dm_{member['id']}"):
                    st.session_state.active_chat_type = 'direct'
                    st.session_state.active_chat_id = member['id']
                    st.session_state.active_chat_name = member_name
                    st.rerun()
    
    # Основная область чата
    chat_type = st.session_state.get('active_chat_type')
    chat_id = st.session_state.get('active_chat_id')
    chat_name = st.session_state.get('active_chat_name', 'Выберите чат')
    
    if not chat_type or not chat_id:
        st.info("Выберите канал или контакт для начала общения")
        return
    
    st.subheader(f"💬 {chat_name}")
    
    # Получаем сообщения
    if chat_type == 'channel':
        messages = chat_service.get_channel_messages(chat_id, limit=50)
    else:  # direct message
        messages = chat_service.get_direct_messages(user_id, chat_id, limit=50)
    
    # Контейнер для сообщений
    messages_container = st.container()
    
    with messages_container:
        if messages:
            # Отображаем сообщения (в обратном порядке, так как получили по убыванию времени)
            for message in reversed(messages):
                is_own_message = message['sender_id'] == user_id
                
                # Создаем стиль для сообщения
                if is_own_message:
                    st.markdown(f"""
                    <div style="text-align: right; margin: 10px 0;">
                        <div style="background-color: #1f77b4; color: white; padding: 10px; border-radius: 15px; display: inline-block; max-width: 70%;">
                            <strong>Вы</strong><br>
                            {message['message']}
                            <br><small>{message['timestamp'][:16]}</small>
                            {' ✏️' if message['is_edited'] else ''}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="text-align: left; margin: 10px 0;">
                        <div style="background-color: #f1f3f4; color: #333; padding: 10px; border-radius: 15px; display: inline-block; max-width: 70%;">
                            <strong>{message['full_name'] or message['email']}</strong><br>
                            {message['message']}
                            <br><small>{message['timestamp'][:16]}</small>
                            {' ✏️' if message['is_edited'] else ''}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("Сообщений пока нет. Начните общение!")
    
    # Форма для отправки сообщений
    st.markdown("---")
    
    with st.form("send_message", clear_on_submit=True):
        col1, col2 = st.columns([4, 1])
        
        with col1:
            new_message = st.text_area("Введите сообщение...", height=100, key="message_input")
        
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)  # Отступ
            send_button = st.form_submit_button("Отправить", type="primary")
        
        if send_button and new_message.strip():
            if chat_type == 'channel':
                message_id = chat_service.send_message(
                    sender_id=user_id,
                    message=new_message.strip(),
                    channel_id=chat_id,
                    company_id=company_id
                )
            else:  # direct message
                message_id = chat_service.send_message(
                    sender_id=user_id,
                    message=new_message.strip(),
                    receiver_id=chat_id,
                    company_id=company_id
                )
            
            if message_id:
                st.success("Сообщение отправлено!")
                st.rerun()
            else:
                st.error("Ошибка отправки сообщения")
    
    # Управление каналом (для админов)
    if chat_type == 'channel':
        with st.expander("Управление каналом"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Добавить участника")
                team_members = get_company_team_members(company_id)
                available_members = [m for m in team_members if m['id'] != user_id]
                
                if available_members:
                    selected_member = st.selectbox(
                        "Выберите участника",
                        available_members,
                        format_func=lambda x: x['full_name'] or x['email']
                    )
                    
                    if st.button("Добавить в канал"):
                        if chat_service.add_user_to_channel(chat_id, selected_member['id']):
                            st.success(f"Пользователь {selected_member['full_name'] or selected_member['email']} добавлен в канал")
                        else:
                            st.error("Пользователь уже в канале или произошла ошибка")
            
            with col2:
                st.markdown("#### Настройки уведомлений")
                if st.button("Настроить уведомления"):
                    st.info("Настройки уведомлений в разработке")

def show_notification_settings():
    """Настройки уведомлений"""
    st.title("🔔 Настройки уведомлений")
    
    user_id = st.session_state.user_id
    current_settings = notification_service.get_user_notification_settings(user_id)
    
    st.markdown("### Типы уведомлений")
    
    notification_types = {
        'chat': 'Сообщения в чате',
        'orders': 'Новые заказы',
        'inventory': 'Складские остатки',
        'marketing': 'Маркетинговые рассылки',
        'system': 'Системные уведомления'
    }
    
    delivery_methods = {
        'email': 'Email',
        'sms': 'SMS',
        'push': 'Push-уведомления'
    }
    
    updated_settings = {}
    
    for ntype, ntype_name in notification_types.items():
        st.subheader(ntype_name)
        
        cols = st.columns(len(delivery_methods))
        
        for i, (method, method_name) in enumerate(delivery_methods.items()):
            with cols[i]:
                current_value = current_settings.get(ntype, {}).get(method, True)
                new_value = st.checkbox(
                    method_name,
                    value=current_value,
                    key=f"{ntype}_{method}"
                )
                
                if ntype not in updated_settings:
                    updated_settings[ntype] = {}
                updated_settings[ntype][method] = new_value
    
    if st.button("Сохранить настройки", type="primary"):
        for ntype, methods in updated_settings.items():
            for method, enabled in methods.items():
                notification_service.update_notification_settings(
                    user_id, ntype, method, enabled
                )
        
        st.success("Настройки уведомлений сохранены!")

def show_integrations():
    """Интеграции и экспорт данных"""
    st.title("🔗 Интеграции и экспорт данных")
    
    if not st.session_state.get('premium_status'):
        st.warning("Интеграции доступны только для Премиум+ пользователей")
        return
    
    user_id = st.session_state.user_id
    company_id = st.session_state.get('active_company_id')
    
    tab1, tab2, tab3, tab4 = st.tabs(["Интеграции", "Экспорт данных", "Мессенджеры", "Резервные копии"])
    
    with tab1:
        st.subheader("🏢 Интеграции с внешними системами")
        
        # Список существующих интеграций
        if company_id:
            integrations = integration_service.get_user_integrations(user_id, company_id)
            
            if integrations:
                st.markdown("### Активные интеграции")
                for integration in integrations:
                    with st.expander(f"{integration['integration_type'].upper()} - {integration['created_at'][:16]}"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.write(f"**Тип:** {integration['integration_type']}")
                            st.write(f"**Статус:** {'🟢 Активна' if integration['is_active'] else '🔴 Неактивна'}")
                        
                        with col2:
                            st.write(f"**Создана:** {integration['created_at'][:16]}")
                            last_sync = integration['last_sync']
                            st.write(f"**Последняя синхронизация:** {last_sync[:16] if last_sync else 'Никогда'}")
                        
                        with col3:
                            if integration['integration_type'] == '1c':
                                if st.button("Синхронизировать из 1С", key=f"sync_from_{integration['id']}"):
                                    result = integration_service.sync_data_from_1c(integration['id'])
                                    if result['success']:
                                        st.success(result['message'])
                                    else:
                                        st.error(result['message'])
                                
                                if st.button("Экспорт в 1С", key=f"sync_to_{integration['id']}"):
                                    result = integration_service.export_data_to_1c(integration['id'])
                                    if result['success']:
                                        st.success(result['message'])
                                    else:
                                        st.error(result['message'])
        
        # Создание новой интеграции
        st.markdown("### Добавить новую интеграцию")
        
        integration_type = st.selectbox("Тип интеграции", [
            "1c", "crm", "whatsapp", "telegram"
        ], format_func=lambda x: {
            "1c": "1С:Предприятие",
            "crm": "CRM система",
            "whatsapp": "WhatsApp Business",
            "telegram": "Telegram Bot"
        }[x])
        
        if integration_type == "1c":
            st.markdown("#### Настройки подключения к 1С")
            with st.form("1c_integration"):
                server_url = st.text_input("URL сервера 1С", placeholder="http://localhost:8080/demo/hs/api/")
                database = st.text_input("База данных", placeholder="demo_database")
                username = st.text_input("Имя пользователя", placeholder="admin")
                password = st.text_input("Пароль", type="password")
                
                if st.form_submit_button("Создать интеграцию"):
                    config = {
                        'server_url': server_url,
                        'database': database,
                        'username': username,
                        'password': password
                    }
                    
                    # Тестируем подключение
                    test_result = integration_service.test_integration_connection("1c", config)
                    
                    if test_result['success']:
                        integration_id = integration_service.create_integration(
                            user_id, company_id, "1c", config
                        )
                        st.success(f"Интеграция с 1С создана! ID: {integration_id}")
                        st.rerun()
                    else:
                        st.error(f"Ошибка подключения: {test_result['message']}")
        
        elif integration_type == "crm":
            st.markdown("#### Настройки подключения к CRM")
            with st.form("crm_integration"):
                crm_type = st.selectbox("Тип CRM", ["bitrix24", "amoCRM", "Pipedrive"])
                api_url = st.text_input("API URL", placeholder="https://your-domain.bitrix24.ru/rest/")
                api_key = st.text_input("API ключ", type="password")
                
                if st.form_submit_button("Создать интеграцию"):
                    config = {
                        'crm_type': crm_type,
                        'api_url': api_url,
                        'api_key': api_key
                    }
                    
                    test_result = integration_service.test_integration_connection("crm", config)
                    
                    if test_result['success']:
                        integration_id = integration_service.create_integration(
                            user_id, company_id, "crm", config
                        )
                        st.success(f"Интеграция с CRM создана! ID: {integration_id}")
                        st.rerun()
                    else:
                        st.error(f"Ошибка подключения: {test_result['message']}")
    
    with tab2:
        st.subheader("📤 Экспорт данных")
        
        if company_id:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Экспорт в Excel")
                
                data_type = st.selectbox("Тип данных", [
                    "orders", "inventory", "customers", "financial"
                ], format_func=lambda x: {
                    "orders": "Заказы",
                    "inventory": "Склад",
                    "customers": "Клиенты",
                    "financial": "Финансы"
                }[x])
                
                col_date1, col_date2 = st.columns(2)
                with col_date1:
                    date_from = st.date_input("С даты", value=datetime.now() - timedelta(days=30))
                with col_date2:
                    date_to = st.date_input("По дату", value=datetime.now())
                
                if st.button("Экспорт в Excel", type="primary"):
                    try:
                        excel_data = export_service.export_to_excel(
                            user_id, company_id, data_type, 
                            date_from.isoformat(), date_to.isoformat()
                        )
                        
                        st.download_button(
                            label="Скачать Excel файл",
                            data=excel_data,
                            file_name=f"{data_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        
                        st.success("Excel файл готов к скачиванию!")
                    except Exception as e:
                        st.error(f"Ошибка экспорта: {str(e)}")
            
            with col2:
                st.markdown("#### Экспорт в CSV")
                
                csv_data_type = st.selectbox("Тип данных для CSV", [
                    "orders", "inventory"
                ], format_func=lambda x: {
                    "orders": "Заказы",
                    "inventory": "Склад"
                }[x], key="csv_type")
                
                if st.button("Экспорт в CSV"):
                    try:
                        csv_data = export_service.export_to_csv(user_id, company_id, csv_data_type)
                        
                        st.download_button(
                            label="Скачать CSV файл",
                            data=csv_data,
                            file_name=f"{csv_data_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                        
                        st.success("CSV файл готов к скачиванию!")
                    except Exception as e:
                        st.error(f"Ошибка экспорта: {str(e)}")
        else:
            st.warning("Выберите активную компанию для экспорта данных")
    
    with tab3:
        st.subheader("💬 Интеграции с мессенджерами")
        
        if company_id:
            # WhatsApp Business
            st.markdown("#### WhatsApp Business API")
            
            with st.form("whatsapp_message"):
                phone_number = st.text_input("Номер телефона", placeholder="+7XXXXXXXXXX")
                message_text = st.text_area("Сообщение", placeholder="Привет! Это сообщение из Бизнес Менеджера")
                
                if st.form_submit_button("Отправить в WhatsApp"):
                    if phone_number and message_text:
                        # Здесь должна быть интеграция с реальным API
                        result = integration_service.send_whatsapp_message(0, phone_number, message_text)
                        if result['success']:
                            st.success("Сообщение отправлено в WhatsApp!")
                        else:
                            st.error("Ошибка отправки сообщения")
                    else:
                        st.error("Заполните все поля")
            
            # Telegram Bot
            st.markdown("#### Telegram Bot API")
            
            with st.form("telegram_message"):
                chat_id = st.text_input("Chat ID", placeholder="@username или числовой ID")
                telegram_message = st.text_area("Сообщение", placeholder="Привет из Бизнес Менеджера!")
                
                if st.form_submit_button("Отправить в Telegram"):
                    if chat_id and telegram_message:
                        result = integration_service.send_telegram_message(0, chat_id, telegram_message)
                        if result['success']:
                            st.success("Сообщение отправлено в Telegram!")
                        else:
                            st.error("Ошибка отправки сообщения")
                    else:
                        st.error("Заполните все поля")
            
            # Массовая рассылка
            st.markdown("#### Массовая рассылка клиентам")
            
            with st.form("bulk_messaging"):
                message_subject = st.text_input("Тема сообщения")
                message_body = st.text_area("Текст сообщения", 
                                          placeholder="Используйте {name} для персонализации")
                
                messaging_type = st.selectbox("Способ отправки", [
                    "email", "whatsapp", "telegram"
                ], format_func=lambda x: {
                    "email": "Email рассылка",
                    "whatsapp": "WhatsApp рассылка",
                    "telegram": "Telegram рассылка"
                }[x])
                
                if st.form_submit_button("Отправить рассылку"):
                    if message_subject and message_body:
                        # В реальном приложении здесь была бы интеграция с customer_communication
                        st.success(f"Рассылка через {messaging_type} запущена!")
                        st.info("В демо-режиме рассылка не отправляется реально")
                    else:
                        st.error("Заполните все поля")
        else:
            st.warning("Выберите активную компанию для работы с мессенджерами")
    
    with tab4:
        st.subheader("💾 Резервные копии")
        
        if company_id:
            st.markdown("#### Создание резервной копии")
            
            backup_scope = st.radio("Область резервного копирования", [
                "current_company", "all_companies"
            ], format_func=lambda x: {
                "current_company": "Только текущая компания",
                "all_companies": "Все компании пользователя"
            }[x])
            
            if st.button("Создать резервную копию", type="primary"):
                try:
                    if backup_scope == "current_company":
                        backup_data = export_service.create_backup_archive(user_id, company_id)
                        filename = f"backup_company_{company_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                    else:
                        backup_data = export_service.create_backup_archive(user_id)
                        filename = f"backup_all_companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                    
                    st.download_button(
                        label="Скачать резервную копию",
                        data=backup_data,
                        file_name=filename,
                        mime="application/zip"
                    )
                    
                    st.success("Резервная копия создана и готова к скачиванию!")
                    
                    # Сохраняем информацию о резервной копии в БД
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO backup_jobs (user_id, backup_type, file_size, status, completed_at)
                        VALUES (?, ?, ?, 'completed', CURRENT_TIMESTAMP)
                    """, (user_id, backup_scope, len(backup_data)))
                    conn.commit()
                    conn.close()
                    
                except Exception as e:
                    st.error(f"Ошибка создания резервной копии: {str(e)}")
            
            # История резервных копий
            st.markdown("#### История резервных копий")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM backup_jobs 
                WHERE user_id = ? 
                ORDER BY started_at DESC 
                LIMIT 10
            """, (user_id,))
            backups = cursor.fetchall()
            conn.close()
            
            if backups:
                for backup in backups:
                    with st.expander(f"Резервная копия от {backup['started_at'][:16]}"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.write(f"**Тип:** {backup['backup_type']}")
                            st.write(f"**Статус:** {backup['status']}")
                        
                        with col2:
                            if backup['file_size']:
                                size_mb = backup['file_size'] / (1024 * 1024)
                                st.write(f"**Размер:** {size_mb:.2f} МБ")
                            st.write(f"**Завершена:** {backup['completed_at'][:16] if backup['completed_at'] else 'Не завершена'}")
                        
                        with col3:
                            if backup['status'] == 'completed':
                                st.success("✅ Успешно")
                            else:
                                st.error("❌ Ошибка")
            else:
                st.info("История резервных копий пуста")
        else:
            st.warning("Выберите активную компанию для создания резервных копий")

# Основное приложение
def main():
    init_enhanced_db()
    
    # Применяем кастомные стили
    apply_custom_css()
    
    # Инициализируем мобильную поддержку и PWA
    initialize_mobile_pwa()
    
    # Создаем гамбургер меню
    create_hamburger_menu()
    
    # Инициализация состояния
    if not st.session_state.get('logged_in'):
        show_login_page()
        return
    
    # Отображение гамбургер меню
    show_hamburger_menu()
    
    # Определение текущей страницы
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'dashboard'
    
    # Навигация по страницам
    page = st.session_state.current_page
    
    if page == 'dashboard':
        show_dashboard()
    elif page == 'ai_features':
        show_ai_features()
    elif page == 'team':
        show_team_management()
    elif page == 'companies':
        show_companies_management()
    elif page == 'settings':
        st.title("⚙️ Настройки")
        st.info("Страница настроек в разработке")
    elif page == 'chat':
        show_corporate_chat()
    elif page == 'automation':
        st.title("🔄 Автоматизация")
        st.info("Автоматизация бизнес-процессов в разработке")
    elif page == 'integrations':
        show_integrations()
    elif page == 'admin' and st.session_state.get('is_admin'):
        st.title("👨‍💼 Панель администратора")
        st.info("Админ панель в разработке")
    else:
        show_dashboard()
    
    # Показываем информацию о пользователе в сайдбаре
    with st.sidebar:
        st.markdown("### Профиль")
        st.write(f"👤 {st.session_state.get('user_name', 'Пользователь')}")
        st.write(f"📧 {st.session_state.get('user_email')}")
        
        if st.session_state.get('premium_status'):
            st.markdown('<span class="premium-badge">ПРЕМИУМ+</span>', unsafe_allow_html=True)
        
        if st.session_state.get('impersonated_user_id'):
            st.warning("Вы работаете от имени другого пользователя")
            if st.button("Вернуться к своему аккаунту"):
                del st.session_state.impersonated_user_id
                del st.session_state.original_user_id
                st.rerun()
        
        if st.button("Выйти"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

if __name__ == "__main__":
    main()

