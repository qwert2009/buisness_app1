
# --- Аутентификация, роли, команды, имперсонация ---
import yaml
import streamlit as st
import streamlit_authenticator as stauth

# Пример хранения пользователей и ролей (можно вынести в отдельный YAML-файл)
users_config = {
    'credentials': {
        'usernames': {
            'alexkurumbayev@gmail.com': {
                'email': 'alexkurumbayev@gmail.com',
                'name': 'Alex Kurumbayev',
                'password': stauth.Hasher(['qwerty123G']).generate()[0],
                'role': 'admin',
            },
        }
    },
    'cookie': {
        'expiry_days': 7,
        'key': 'streamlit_auth',
        'name': 'streamlit_auth',
    },
    'preauthorized': {
        'emails': ["alexkurumbayev@gmail.com"]
    }
}

def get_user_role(username):
    return users_config['credentials']['usernames'].get(username, {}).get('role', 'viewer')

def is_admin():
    return st.session_state.get('user_role') == 'admin'

def is_editor():
    return st.session_state.get('user_role') in ['admin', 'editor']

def is_viewer():
    return st.session_state.get('user_role') in ['admin', 'editor', 'viewer']

def impersonate_user(username):
    st.session_state['impersonated_user'] = username
    st.session_state['user_role'] = get_user_role(username)

def stop_impersonation():
    if 'impersonated_user' in st.session_state:
        del st.session_state['impersonated_user']
        st.session_state['user_role'] = get_user_role(st.session_state.get('username'))


def show_login():
    authenticator = stauth.Authenticate(
        users_config['credentials'],
        users_config['cookie']['name'],
        users_config['cookie']['key'],
        users_config['cookie']['expiry_days'],
        users_config['preauthorized']
    )
    name, authentication_status, username = authenticator.login('Вход', 'main')
    if authentication_status:
        st.session_state['username'] = username
        st.session_state['user_role'] = get_user_role(username)
        st.success(f"Добро пожаловать, {name}!")
        authenticator.logout('Выйти', 'sidebar')
        return True
    elif authentication_status is False:
        st.error('Неверный логин или пароль')

    # --- Регистрация нового пользователя ---
    with st.expander('Регистрация нового пользователя'):
        reg_email = st.text_input('Email для регистрации')
        reg_name = st.text_input('Имя')
        reg_password = st.text_input('Пароль', type='password')
        reg_role = st.selectbox('Роль', ['viewer', 'editor'])
        if st.button('Зарегистрироваться'):
            if reg_email and reg_password and reg_name:
                if reg_email in users_config['credentials']['usernames']:
                    st.warning('Пользователь с таким email уже существует.')
                else:
                    users_config['credentials']['usernames'][reg_email] = {
                        'email': reg_email,
                        'name': reg_name,
                        'password': stauth.Hasher([reg_password]).generate()[0],
                        'role': reg_role,
                    }
                    st.success('Пользователь успешно зарегистрирован! Теперь войдите.')
            else:
                st.warning('Пожалуйста, заполните все поля для регистрации.')
    return False

def show_impersonation_panel():
    if is_admin():
        st.sidebar.markdown('---')
        st.sidebar.subheader('Имперсонация (Switch User)')
        usernames = list(users_config['credentials']['usernames'].keys())
        selected = st.sidebar.selectbox('Выбрать пользователя', usernames)
        if st.sidebar.button('Перейти в аккаунт'):
            impersonate_user(selected)
            st.sidebar.success(f'Вы переключились на {selected}')
        if 'impersonated_user' in st.session_state:
            st.sidebar.info(f'Сейчас вы как: {st.session_state["impersonated_user"]}')
            if st.sidebar.button('Вернуться к своему аккаунту'):
                stop_impersonation()

# --- Вход и определение роли пользователя ---
if 'user_role' not in st.session_state:
    if not show_login():
        st.stop()

# --- Имперсонация ---
show_impersonation_panel()
# --- Автоматизация и планировщик задач (базовая интеграция) ---
from threading import Thread
import time as _time
import schedule

def run_scheduler():
    while True:
        schedule.run_pending()
        _time.sleep(1)

def schedule_daily_report(user_id):
    schedule.every().day.at("08:00").do(send_daily_report, user_id)

def schedule_monthly_report(user_id):
    schedule.every(30).days.at("08:00").do(send_daily_report, user_id)

def start_automation_for_user(user_id, daily=True, monthly=False):
    if daily:
        schedule_daily_report(user_id)
    if monthly:
        schedule_monthly_report(user_id)
    Thread(target=run_scheduler, daemon=True).start()

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

# Настройка страницы
st.set_page_config(
    page_title="Бизнес Менеджер",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Минималистичный классический дизайн (CSS)
st.markdown("""
<style>
    /* ... CSS ... (оставьте как есть, до </style>) ... */
</style>
""", unsafe_allow_html=True)

def show_modern_navigation():
    """Современная минималистичная навигация с уведомлениями"""
   
    # Получаем количество непрочитанных уведомлений
    unread_count = get_unread_notifications_count(st.session_state.user_id)
   
    # Отображение текущей компании (мультибизнес)
    if 'active_company_id' in st.session_state:
        conn = sqlite3.connect('business_manager.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM companies WHERE id = ?', (st.session_state.active_company_id,))
        cname = cursor.fetchone()
        if cname:
            st.info(f"Текущая компания: {cname[0]}")
        conn.close()
    # Кнопки навигации с использованием колонок
    col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)
   
    with col1:
        if st.button("📊 Панель", use_container_width=True,
                    type="primary" if st.session_state.current_page == "dashboard" else "secondary"):
            st.session_state.current_page = "dashboard"
            st.rerun()
   
    with col2:
        if st.button("📦 Заказы", use_container_width=True,
                    type="primary" if st.session_state.current_page == "orders" else "secondary"):
            st.session_state.current_page = "orders"
            st.rerun()
   
    with col3:
        if st.button("📋 Управление", use_container_width=True,
                    type="primary" if st.session_state.current_page == "order_management" else "secondary"):
            st.session_state.current_page = "order_management"
            st.rerun()
   
    with col4:
        if st.button("📈 Аналитика", use_container_width=True,
                    type="primary" if st.session_state.current_page == "analytics" else "secondary"):
            st.session_state.current_page = "analytics"
            st.rerun()
   
    with col5:
        if st.button("🏪 Склад", use_container_width=True,
                    type="primary" if st.session_state.current_page == "inventory" else "secondary"):
            st.session_state.current_page = "inventory"
            st.rerun()
   
    with col6:
        # Кнопка уведомлений с индикатором
        notification_button_type = "primary" if st.session_state.current_page == "notifications" else "secondary"
        if unread_count > 0:
            button_label = f"🔔 ({unread_count})"
        else:
            button_label = "🔔"
           
        if st.button(button_label, use_container_width=True, type=notification_button_type):
            st.session_state.current_page = "notifications"
            st.rerun()
   
    with col7:
        if st.button("🧠 ИИ", use_container_width=True,
                    type="primary" if st.session_state.current_page == "smart" else "secondary"):
            st.session_state.current_page = "smart"
            st.rerun()
   
    with col8:
        if st.button("⚙️ Настройки", use_container_width=True,
                    type="primary" if st.session_state.current_page == "settings" else "secondary"):
            st.session_state.current_page = "settings"
            st.rerun()

def show_admin_navigation():
    """Дополнительная навигация для администратора"""
    if st.session_state.get('is_admin', False):
        st.markdown('---')
        st.markdown('### 👨‍💼 Панель администратора')
       
        # Админские кнопки
        col1, col2, col3, col4, col5 = st.columns(5)
       
        with col1:
            if st.button("👥 Пользователи", use_container_width=True,
                        type="primary" if st.session_state.get('admin_page') == "users" else "secondary",
                        key="admin_users_btn"):
                st.session_state.admin_page = "users"
                st.session_state.current_page = "admin"
                st.rerun()
       
        with col2:
            if st.button("💳 Платежи", use_container_width=True,
                        type="primary" if st.session_state.get('admin_page') == "payments" else "secondary",
                        key="admin_payments_btn"):
                st.session_state.admin_page = "payments"
                st.session_state.current_page = "admin"
                st.rerun()
       
        with col3:
            if st.button("📊 Статистика", use_container_width=True,
                        type="primary" if st.session_state.get('admin_page') == "stats" else "secondary",
                        key="admin_stats_btn"):
                st.session_state.admin_page = "stats"
                st.session_state.current_page = "admin"
                st.rerun()
       
        with col4:
            if st.button("📈 Отчеты", use_container_width=True,
                        type="primary" if st.session_state.get('admin_page') == "reports" else "secondary",
                        key="admin_reports_btn"):
                st.session_state.admin_page = "reports"
                st.session_state.current_page = "admin"
                st.rerun()
       
        with col5:
            if st.button("⚙️ Админ настройки", use_container_width=True,
                        type="primary" if st.session_state.get('admin_page') == "admin_settings" else "secondary",
                        key="admin_settings_btn"):
                st.session_state.admin_page = "admin_settings"
                st.session_state.current_page = "admin"
                st.rerun()
       
        st.markdown('---')

# Инициализация базы данных
def init_db():
    # Добавляем warehouse_id в inventory, если его нет
    try:
        cursor.execute("ALTER TABLE inventory ADD COLUMN warehouse_id INTEGER")
    except Exception:
        pass
    conn = sqlite3.connect('business_manager.db')
    cursor = conn.cursor()
   
    # Таблица пользователей с расширенными полями
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
            last_login TIMESTAMP
        )
    ''')
   
    # Таблица заказов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_type TEXT NOT NULL,
            order_name TEXT NOT NULL,
            total_payment REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivery_type TEXT,
            notification_sent INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Таблица товаров в заказах
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            cost_price REAL NOT NULL,
            sale_price REAL DEFAULT 0,
            weight REAL NOT NULL,
            delivery_cost REAL,
            total_cost REAL,
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
    ''')
   
    # Проверяем и добавляем колонку sale_price если её нет
    try:
        cursor.execute('ALTER TABLE order_items ADD COLUMN sale_price REAL DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    # Добавляем колонку delivery_type для каждого товара
    try:
        cursor.execute('ALTER TABLE order_items ADD COLUMN item_delivery_type TEXT DEFAULT "truck"')
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    # Добавляем колонки для отслеживания статуса заказов
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN status TEXT DEFAULT "pending"')
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN expected_delivery_date TIMESTAMP')
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN actual_delivery_date TIMESTAMP')
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN delay_notification_sent INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    # Таблица склада
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Таблица истории заказов (для товаров, которые привозятся под заказ)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_id INTEGER,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            cost_price REAL NOT NULL,
            sale_price REAL NOT NULL,
            weight REAL NOT NULL,
            delivery_type TEXT DEFAULT "truck",
            delivery_cost REAL NOT NULL,
            total_cost REAL NOT NULL,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT "completed",
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
    ''')
   
    # Таблица настроек
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            financial_cushion_percent REAL DEFAULT 20.0,
            email_notifications BOOLEAN DEFAULT 1,
            smtp_server TEXT,
            smtp_port INTEGER DEFAULT 587,
            email_username TEXT,
            email_password TEXT,
            notify_new_orders BOOLEAN DEFAULT 1,
            notify_low_stock BOOLEAN DEFAULT 1,
            notify_daily_report BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Добавляем недостающие поля в таблицу settings, если их нет
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN notify_new_orders BOOLEAN DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # Поле уже существует
   
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN notify_low_stock BOOLEAN DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # Поле уже существует
       
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN notify_daily_report BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Поле уже существует
   
    # Добавляем поля для цен доставки
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN airplane_price_per_kg REAL DEFAULT 5.0")
    except (sqlite3.OperationalError, sqlite3.ProgrammingError):
        pass  # Поле уже существует
   
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN truck_price_per_kg REAL DEFAULT 2.0")
    except (sqlite3.OperationalError, sqlite3.ProgrammingError):
        pass  # Поле уже существует
   
    # Обновляем существующие записи, чтобы установить значения по умолчанию для новых полей
    cursor.execute("UPDATE settings SET notify_new_orders = 1 WHERE notify_new_orders IS NULL")
    cursor.execute("UPDATE settings SET notify_low_stock = 1 WHERE notify_low_stock IS NULL")
    cursor.execute("UPDATE settings SET notify_daily_report = 0 WHERE notify_daily_report IS NULL")
    cursor.execute("UPDATE settings SET airplane_price_per_kg = 5.0 WHERE airplane_price_per_kg IS NULL")
    cursor.execute("UPDATE settings SET truck_price_per_kg = 2.0 WHERE truck_price_per_kg IS NULL")

    # Таблица уведомлений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Таблица компаний (для мультибизнеса)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
    ''')
   
    # Таблица связи пользователей с компаниями (для гибкой ролевой модели)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_companies (
            user_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            role TEXT NOT NULL, -- 'owner', 'admin', 'editor', 'viewer'
            PRIMARY KEY (user_id, company_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
   
    # Таблица для хранения информации о складах (для мультисклада)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            location TEXT,
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
   
    # Добавляем колонку company_id в inventory, если ее нет
    try:
        cursor.execute("ALTER TABLE inventory ADD COLUMN company_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    # Добавляем колонку company_id в orders, если ее нет
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN company_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    # Добавляем колонку company_id в order_history, если ее нет
    try:
        cursor.execute("ALTER TABLE order_history ADD COLUMN company_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
   
    # Таблица для хранения AI-генерируемых идей (AI-генератор бизнес-идей)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            idea_text TEXT NOT NULL,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Таблица для хранения автоматических отчетов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_type TEXT NOT NULL, -- 'daily', 'monthly'
            report_content TEXT NOT NULL,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Таблица для финансового контроля (налоги, задолженности)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS financial_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            record_type TEXT NOT NULL, -- 'tax', 'debt', 'income', 'expense'
            amount REAL NOT NULL,
            description TEXT,
            record_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_paid BOOLEAN DEFAULT FALSE,
            due_date TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Таблица для журнала действий (безопасность)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Таблица для корпоративного чата
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER, -- NULL for group chat or specific user ID
            company_id INTEGER, -- For company-wide chats
            message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users (id),
            FOREIGN KEY (receiver_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
   
    # Таблица для настроек персонального бренда
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS branding_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            logo_url TEXT,
            primary_color TEXT DEFAULT '#1E90FF',
            secondary_color TEXT DEFAULT '#FFD700',
            email_signature TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
   
    # Добавляем админ пользователя, если его нет
    cursor.execute('SELECT * FROM users WHERE email = ?', ('admin@company.com',))
    if cursor.fetchone() is None:
        admin_password_hash = stauth.Hasher(['adminpass']).generate()[0]
        cursor.execute(
            "INSERT INTO users (email, password_hash, full_name, is_admin, premium_status) VALUES (?, ?, ?, ?, ?)",
            ('admin@company.com', admin_password_hash, 'Администратор', True, True)
        )
        conn.commit()
        st.success("Администратор добавлен: admin@company.com / adminpass")
   
    # Добавляем пользователя alexkurumbayev@gmail.com, если его нет
    cursor.execute('SELECT * FROM users WHERE email = ?', ('alexkurumbayev@gmail.com',))
    if cursor.fetchone() is None:
        user_password_hash = stauth.Hasher(['qwerty123G']).generate()[0]
        cursor.execute(
            "INSERT INTO users (email, password_hash, full_name, is_admin, premium_status) VALUES (?, ?, ?, ?, ?)",
            ('alexkurumbayev@gmail.com', user_password_hash, 'Alex Kurumbayev', True, True)
        )
        conn.commit()
        st.success("Пользователь добавлен: alexkurumbayev@gmail.com / qwerty123G")

    conn.commit()
    conn.close()

# Функции для работы с базой данных
def get_db_connection():
    conn = sqlite3.connect('business_manager.db')
    conn.row_factory = sqlite3.Row
    return conn

def add_user(email, password, full_name=None, phone=None, business_name=None, is_admin=False, premium_status=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        cursor.execute(
            "INSERT INTO users (email, password_hash, full_name, phone, business_name, is_admin, premium_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (email, password_hash, full_name, phone, business_name, is_admin, premium_status)
        )
        conn.commit()
        user_id = cursor.lastrowid
        # Создаем запись в таблице settings для нового пользователя
        cursor.execute("INSERT INTO settings (user_id) VALUES (?) ", (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        st.error("Пользователь с таким email уже существует.")
        return False
    finally:
        conn.close()

def get_user_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_last_login(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def update_user_premium_status(user_id, status, start_date=None, end_date=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET premium_status = ?, premium_start_date = ?, premium_end_date = ? WHERE id = ?",
        (status, start_date, end_date, user_id)
    )
    conn.commit()
    conn.close()

def add_order(user_id, order_type, order_name, total_payment, delivery_type, company_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (user_id, order_type, order_name, total_payment, delivery_type, company_id) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, order_type, order_name, total_payment, delivery_type, company_id)
    )
    conn.commit()
    order_id = cursor.lastrowid
    conn.close()
    return order_id

def add_order_item(order_id, product_name, quantity, cost_price, sale_price, weight, delivery_cost, total_cost, item_delivery_type="truck"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO order_items (order_id, product_name, quantity, cost_price, sale_price, weight, delivery_cost, total_cost, item_delivery_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, product_name, quantity, cost_price, sale_price, weight, delivery_cost, total_cost, item_delivery_type)
    )
    conn.commit()
    conn.close()

def get_orders(user_id, company_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if company_id:
        cursor.execute("SELECT * FROM orders WHERE user_id = ? AND company_id = ? ORDER BY created_at DESC", (user_id, company_id))
    else:
        cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_order_items(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    items = cursor.fetchall()
    conn.close()
    return items

def update_order_status(order_id, status, expected_delivery_date=None, actual_delivery_date=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE orders SET status = ?, expected_delivery_date = ?, actual_delivery_date = ? WHERE id = ?",
        (status, expected_delivery_date, actual_delivery_date, order_id)
    )
    conn.commit()
    conn.close()

def add_inventory_item(user_id, product_name, quantity, link, company_id=None, warehouse_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO inventory (user_id, product_name, quantity, link, company_id, warehouse_id) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, product_name, quantity, link, company_id, warehouse_id)
    )
    conn.commit()
    conn.close()

def get_inventory_items(user_id, company_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if company_id:
        cursor.execute("SELECT * FROM inventory WHERE user_id = ? AND company_id = ? ORDER BY created_at DESC", (user_id, company_id))
    else:
        cursor.execute("SELECT * FROM inventory WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    items = cursor.fetchall()
    conn.close()
    return items

def update_inventory_quantity(item_id, new_quantity):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_quantity, item_id))
    conn.commit()
    conn.close()

def delete_inventory_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def add_order_to_history(user_id, order_id, product_name, quantity, cost_price, sale_price, weight, delivery_type, delivery_cost, total_cost, status="completed", company_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO order_history (user_id, order_id, product_name, quantity, cost_price, sale_price, weight, delivery_type, delivery_cost, total_cost, status, company_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, order_id, product_name, quantity, cost_price, sale_price, weight, delivery_type, delivery_cost, total_cost, status, company_id)
    )
    conn.commit()
    conn.close()

def get_order_history(user_id, company_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if company_id:
        cursor.execute("SELECT * FROM order_history WHERE user_id = ? AND company_id = ? ORDER BY order_date DESC", (user_id, company_id))
    else:
        cursor.execute("SELECT * FROM order_history WHERE user_id = ? ORDER BY order_date DESC", (user_id,))
    history = cursor.fetchall()
    conn.close()
    return history

def get_user_settings(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,))
    settings = cursor.fetchone()
    conn.close()
    return settings

def update_user_settings(user_id, financial_cushion_percent, email_notifications, smtp_server, smtp_port, email_username, email_password, notify_new_orders, notify_low_stock, notify_daily_report, airplane_price_per_kg, truck_price_per_kg):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE settings SET financial_cushion_percent = ?, email_notifications = ?, smtp_server = ?, smtp_port = ?, email_username = ?, email_password = ?, notify_new_orders = ?, notify_low_stock = ?, notify_daily_report = ?, airplane_price_per_kg = ?, truck_price_per_kg = ? WHERE user_id = ?",
        (financial_cushion_percent, email_notifications, smtp_server, smtp_port, email_username, email_password, notify_new_orders, notify_low_stock, notify_daily_report, airplane_price_per_kg, truck_price_per_kg, user_id)
    )
    conn.commit()
    conn.close()

def send_email(to_email, subject, body, smtp_server, smtp_port, email_username, email_password):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_username
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            server.login(email_username, email_password)
            server.sendmail(email_username, to_email, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Ошибка при отправке email: {e}")
        return False

def send_new_order_notification(user_id, order_name, total_payment):
    settings = get_user_settings(user_id)
    if settings and settings['email_notifications'] and settings['notify_new_orders']:
        user = get_user_by_id(user_id)
        if user:
            subject = f"Новый заказ: {order_name}"
            body = f"У вас новый заказ '{order_name}' на сумму {total_payment} руб.\n\nС уважением,\nВаш Бизнес Менеджер"
            send_email(user['email'], subject, body, settings['smtp_server'], settings['smtp_port'], settings['email_username'], settings['email_password'])

def send_low_stock_notification(user_id, product_name, quantity):
    settings = get_user_settings(user_id)
    if settings and settings['email_notifications'] and settings['notify_low_stock']:
        user = get_user_by_id(user_id)
        if user:
            subject = f"Низкий запас товара: {product_name}"
            body = f"Товар '{product_name}' на складе заканчивается. Остаток: {quantity}.\n\nС уважением,\nВаш Бизнес Менеджер"
            send_email(user['email'], subject, body, settings['smtp_server'], settings['smtp_port'], settings['email_username'], settings['email_password'])

def send_daily_report(user_id):
    settings = get_user_settings(user_id)
    if settings and settings['email_notifications'] and settings['notify_daily_report']:
        user = get_user_by_id(user_id)
        if user:
            subject = "Ежедневный отчет Бизнес Менеджера"
            # Здесь можно сгенерировать реальный отчет
            body = "Это ваш ежедневный отчет. Сегодняшние показатели: ...\n\nС уважением,\nВаш Бизнес Менеджер"
            send_email(user['email'], subject, body, settings['smtp_server'], settings['smtp_port'], settings['email_username'], settings['email_password'])

def add_notification(user_id, message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (user_id, message))
    conn.commit()
    conn.close()

def get_notifications(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    notifications = cursor.fetchall()
    conn.close()
    return notifications

def mark_notification_as_read(notification_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = TRUE WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()

def get_unread_notifications_count(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = FALSE", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def add_company(owner_id, name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO companies (owner_id, name) VALUES (?, ?)", (owner_id, name))
    conn.commit()
    company_id = cursor.lastrowid
    # Добавляем владельца в user_companies с ролью 'owner'
    cursor.execute("INSERT INTO user_companies (user_id, company_id, role) VALUES (?, ?, ?)", (owner_id, company_id, 'owner'))
    conn.commit()
    conn.close()
    return company_id

def get_companies_for_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT c.id, c.name, uc.role FROM companies c JOIN user_companies uc ON c.id = uc.company_id WHERE uc.user_id = ?", (user_id,))
    companies = cursor.fetchall()
    conn.close()
    return companies

def get_company_by_id(company_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
    company = cursor.fetchone()
    conn.close()
    return company

def add_user_to_company(user_id, company_id, role):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO user_companies (user_id, company_id, role) VALUES (?, ?, ?)", (user_id, company_id, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        st.warning("Пользователь уже добавлен в эту компанию.")
        return False
    finally:
        conn.close()

def get_users_in_company(company_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT u.id, u.email, u.full_name, uc.role FROM users u JOIN user_companies uc ON u.id = uc.user_id WHERE uc.company_id = ?", (company_id,))
    users = cursor.fetchall()
    conn.close()
    return users

def update_user_company_role(user_id, company_id, new_role):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE user_companies SET role = ? WHERE user_id = ? AND company_id = ?", (new_role, user_id, company_id))
    conn.commit()
    conn.close()

def remove_user_from_company(user_id, company_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_companies WHERE user_id = ? AND company_id = ?", (user_id, company_id))
    conn.commit()
    conn.close()

def add_warehouse(company_id, name, location):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO warehouses (company_id, name, location) VALUES (?, ?, ?)", (company_id, name, location))
    conn.commit()
    conn.close()

def get_warehouses(company_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM warehouses WHERE company_id = ?", (company_id,))
    warehouses = cursor.fetchall()
    conn.close()
    return warehouses

def add_ai_idea(user_id, idea_text):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO ai_ideas (user_id, idea_text) VALUES (?, ?)", (user_id, idea_text))
    conn.commit()
    conn.close()

def get_ai_ideas(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ai_ideas WHERE user_id = ? ORDER BY generated_at DESC", (user_id,))
    ideas = cursor.fetchall()
    conn.close()
    return ideas

def add_auto_report(user_id, report_type, report_content):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO auto_reports (user_id, report_type, report_content) VALUES (?, ?, ?)", (user_id, report_type, report_content))
    conn.commit()
    conn.close()

def get_auto_reports(user_id, report_type=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if report_type:
        cursor.execute("SELECT * FROM auto_reports WHERE user_id = ? AND report_type = ? ORDER BY generated_at DESC", (user_id, report_type))
    else:
        cursor.execute("SELECT * FROM auto_reports WHERE user_id = ? ORDER BY generated_at DESC", (user_id,))
    reports = cursor.fetchall()
    conn.close()
    return reports

def add_financial_record(user_id, record_type, amount, description=None, is_paid=False, due_date=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO financial_records (user_id, record_type, amount, description, is_paid, due_date) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, record_type, amount, description, is_paid, due_date)
    )
    conn.commit()
    conn.close()

def get_financial_records(user_id, record_type=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if record_type:
        cursor.execute("SELECT * FROM financial_records WHERE user_id = ? AND record_type = ? ORDER BY record_date DESC", (user_id, record_type))
    else:
        cursor.execute("SELECT * FROM financial_records WHERE user_id = ? ORDER BY record_date DESC", (user_id,))
    records = cursor.fetchall()
    conn.close()
    return records

def update_financial_record_status(record_id, is_paid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE financial_records SET is_paid = ? WHERE id = ?", (is_paid, record_id))
    conn.commit()
    conn.close()

def add_activity_log(user_id, action, ip_address=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO activity_log (user_id, action, ip_address) VALUES (?, ?, ?)", (user_id, action, ip_address))
    conn.commit()
    conn.close()

def get_activity_log(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_log WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    log = cursor.fetchall()
    conn.close()
    return log

def add_chat_message(sender_id, message, receiver_id=None, company_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_messages (sender_id, message, receiver_id, company_id) VALUES (?, ?, ?, ?)", (sender_id, message, receiver_id, company_id))
    conn.commit()
    conn.close()

def get_chat_messages(user_id, other_user_id=None, company_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if company_id:
        # Company-wide chat
        cursor.execute("SELECT * FROM chat_messages WHERE company_id = ? ORDER BY timestamp ASC", (company_id,))
    elif other_user_id:
        # Private chat between two users
        cursor.execute("SELECT * FROM chat_messages WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?) ORDER BY timestamp ASC",
                       (user_id, other_user_id, other_user_id, user_id))
    else:
        # All messages for a user (could be expanded to show all private chats)
        cursor.execute("SELECT * FROM chat_messages WHERE sender_id = ? OR receiver_id = ? ORDER BY timestamp ASC", (user_id, user_id))
    messages = cursor.fetchall()
    conn.close()
    return messages

def update_branding_settings(user_id, logo_url=None, primary_color=None, secondary_color=None, email_signature=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Проверяем, существует ли запись для пользователя
    cursor.execute("SELECT * FROM branding_settings WHERE user_id = ?", (user_id,))
    existing_settings = cursor.fetchone()

    if existing_settings:
        # Обновляем существующую запись
        update_query = "UPDATE branding_settings SET "
        update_params = []
        if logo_url is not None: update_query += "logo_url = ?, "; update_params.append(logo_url)
        if primary_color is not None: update_query += "primary_color = ?, "; update_params.append(primary_color)
        if secondary_color is not None: update_query += "secondary_color = ?, "; update_params.append(secondary_color)
        if email_signature is not None: update_query += "email_signature = ?, "; update_params.append(email_signature)
       
        if update_params:
            update_query = update_query.rstrip(', ') + " WHERE user_id = ?"
            update_params.append(user_id)
            cursor.execute(update_query, tuple(update_params))
    else:
        # Создаем новую запись
        cursor.execute(
            "INSERT INTO branding_settings (user_id, logo_url, primary_color, secondary_color, email_signature) VALUES (?, ?, ?, ?, ?)",
            (user_id, logo_url, primary_color, secondary_color, email_signature)
        )
    conn.commit()
    conn.close()

def get_branding_settings(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM branding_settings WHERE user_id = ?", (user_id,))
    settings = cursor.fetchone()
    conn.close()
    return settings

# --- Функции для страниц Streamlit ---
def show_dashboard_page():
    st.title("📊 Панель управления")
    st.write("Добро пожаловать в Бизнес Менеджер!")
   
    user_id = st.session_state.user_id
    current_company_id = st.session_state.get('active_company_id')

    # Отображение текущей компании
    if current_company_id:
        company = get_company_by_id(current_company_id)
        if company:
            st.subheader(f"Текущая компания: {company['name']}")

    # Краткая статистика
    st.subheader("Краткая статистика")
    col1, col2, col3 = st.columns(3)
    with col1:
        orders = get_orders(user_id, current_company_id)
        st.metric(label="Всего заказов", value=len(orders))
    with col2:
        inventory_items = get_inventory_items(user_id, current_company_id)
        st.metric(label="Товаров на складе", value=len(inventory_items))
    with col3:
        # Пример: общая сумма заказов
        total_sales = sum([order['total_payment'] for order in orders])
        st.metric(label="Общая сумма продаж", value=f"{total_sales:.2f} руб.")

    # График продаж за последние 30 дней
    st.subheader("Продажи за последние 30 дней")
    sales_data = []
    today = datetime.now()
    for i in range(30):
        date = today - timedelta(days=i)
        daily_sales = sum([order['total_payment'] for order in orders if datetime.strptime(order['created_at'].split('.')[0], '%Y-%m-%d %H:%M:%S') .date() == date.date()])
        sales_data.append({"Дата": date.strftime("%Y-%m-%d"), "Продажи": daily_sales})
    df_sales = pd.DataFrame(sales_data).sort_values(by="Дата")
    st.line_chart(df_sales.set_index("Дата"))

    # Последние заказы
    st.subheader("Последние заказы")
    if orders:
        df_orders = pd.DataFrame(orders)
        st.dataframe(df_orders[['order_name', 'total_payment', 'created_at', 'status']])
    else:
        st.info("Пока нет заказов.")

    # Товары с низким остатком (пример)
    st.subheader("Товары с низким остатком")
    low_stock_items = [item for item in inventory_items if item['quantity'] < 10] # Пример порога
    if low_stock_items:
        df_low_stock = pd.DataFrame(low_stock_items)
        st.dataframe(df_low_stock[['product_name', 'quantity']])
    else:
        st.info("Все товары в достаточном количестве.")

def show_orders_page():
    st.title("📦 Управление заказами")
    user_id = st.session_state.user_id
    current_company_id = st.session_state.get('active_company_id')

    st.subheader("Добавить новый заказ")
    with st.form("new_order_form"):
        order_name = st.text_input("Название заказа")
        order_type = st.selectbox("Тип заказа", ["Продажа", "Закупка", "Возврат"])
        delivery_type = st.selectbox("Тип доставки", ["truck", "airplane"])
        num_items = st.number_input("Количество позиций в заказе", min_value=1, value=1)

        items_data = []
        for i in range(num_items):
            st.markdown(f"#### Позиция {i+1}")
            product_name = st.text_input(f"Название товара {i+1}", key=f"product_name_{i}")
            quantity = st.number_input(f"Количество {i+1}", min_value=1, key=f"quantity_{i}")
            cost_price = st.number_input(f"Себестоимость за ед. {i+1}", min_value=0.0, key=f"cost_price_{i}")
            sale_price = st.number_input(f"Цена продажи за ед. {i+1}", min_value=0.0, key=f"sale_price_{i}")
            weight = st.number_input(f"Вес за ед. (кг) {i+1}", min_value=0.0, key=f"weight_{i}")
            item_delivery_type = st.selectbox(f"Тип доставки для позиции {i+1}", ["truck", "airplane"], key=f"item_delivery_type_{i}")
            items_data.append({
                "product_name": product_name,
                "quantity": quantity,
                "cost_price": cost_price,
                "sale_price": sale_price,
                "weight": weight,
                "item_delivery_type": item_delivery_type
            })
       
        submitted = st.form_submit_button("Добавить заказ")
        if submitted:
            total_payment = 0
            total_delivery_cost = 0
            settings = get_user_settings(user_id)
            airplane_price_per_kg = settings['airplane_price_per_kg'] if settings else 5.0
            truck_price_per_kg = settings['truck_price_per_kg'] if settings else 2.0

            for item in items_data:
                item_total_cost = item['quantity'] * item['cost_price']
                item_total_sale = item['quantity'] * item['sale_price']
                item_total_weight = item['quantity'] * item['weight']
               
                if item['item_delivery_type'] == "airplane":
                    item_delivery_cost = item_total_weight * airplane_price_per_kg
                else:
                    item_delivery_cost = item_total_weight * truck_price_per_kg
               
                total_payment += item_total_sale # Для продаж
                total_delivery_cost += item_delivery_cost

                item['delivery_cost'] = item_delivery_cost
                item['total_cost'] = item_total_cost + item_delivery_cost

            order_id = add_order(user_id, order_type, order_name, total_payment, delivery_type, current_company_id)
            if order_id:
                for item in items_data:
                    add_order_item(order_id, item['product_name'], item['quantity'], item['cost_price'], item['sale_price'], item['weight'], item['delivery_cost'], item['total_cost'], item['item_delivery_type'])
                    # Добавляем в историю заказов (для товаров под заказ)
                    add_order_to_history(user_id, order_id, item['product_name'], item['quantity'], item['cost_price'], item['sale_price'], item['weight'], item['item_delivery_type'], item['delivery_cost'], item['total_cost'], company_id=current_company_id)
                st.success(f"Заказ '{order_name}' успешно добавлен!")
                send_new_order_notification(user_id, order_name, total_payment)
            else:
                st.error("Ошибка при добавлении заказа.")

    st.subheader("Список заказов")
    orders = get_orders(user_id, current_company_id)
    if orders:
        df_orders = pd.DataFrame(orders)
        st.dataframe(df_orders)

        selected_order_id = st.selectbox("Выберите заказ для просмотра деталей", [order['id'] for order in orders])
        if selected_order_id:
            st.subheader(f"Детали заказа #{selected_order_id}")
            order_items = get_order_items(selected_order_id)
            if order_items:
                df_order_items = pd.DataFrame(order_items)
                st.dataframe(df_order_items)

            # Обновление статуса заказа
            current_order = [o for o in orders if o['id'] == selected_order_id][0]
            new_status = st.selectbox("Обновить статус заказа", ["pending", "processing", "shipped", "delivered", "cancelled"], index=["pending", "processing", "shipped", "delivered", "cancelled"].index(current_order['status']))
            expected_date = st.date_input("Ожидаемая дата доставки", value=datetime.strptime(current_order['expected_delivery_date'].split('.')[0], '%Y-%m-%d %H:%M:%S').date() if current_order['expected_delivery_date'] else None)
            actual_date = st.date_input("Фактическая дата доставки", value=datetime.strptime(current_order['actual_delivery_date'].split('.')[0], '%Y-%m-%d %H:%M:%S').date() if current_order['actual_delivery_date'] else None)
           
            if st.button("Сохранить статус заказа"):
                update_order_status(selected_order_id, new_status, expected_date, actual_date)
                st.success("Статус заказа обновлен.")
                st.rerun()

    else:
        st.info("Пока нет заказов.")

def show_order_management_page():
    st.title("📋 Управление заказами (расширенное)")
    st.write("Здесь будет расширенное управление заказами, отслеживание, логистика.")
    user_id = st.session_state.user_id
    current_company_id = st.session_state.get('active_company_id')

    st.subheader("История заказов (товары под заказ)")
    history = get_order_history(user_id, current_company_id)
    if history:
        df_history = pd.DataFrame(history)
        st.dataframe(df_history)
    else:
        st.info("История заказов пуста.")

    st.subheader("Отслеживание задолженностей и напоминания")
    # Пример: Отображение неоплаченных заказов
    unpaid_orders = [order for order in get_orders(user_id, current_company_id) if order['status'] != 'delivered' and order['total_payment'] > 0] # Упрощенно
    if unpaid_orders:
        st.warning("Есть неоплаченные или незавершенные заказы!")
        for order in unpaid_orders:
            st.write(f"Заказ #{order['id']}: {order['order_name']} - {order['total_payment']} руб. (Статус: {order['status']})")
            if st.button(f"Отправить напоминание по заказу #{order['id']}", key=f"remind_order_{order['id']}"):
                # Здесь логика отправки напоминания (email/sms)
                st.info(f"Напоминание по заказу #{order['id']} отправлено.")
    else:
        st.info("Все заказы оплачены или завершены.")

    st.subheader("Автоматические счета и документы")
    st.write("Здесь будет функционал для автоматической генерации счетов, актов и других документов.")
    # Пример: кнопка для генерации счета
    if st.button("Сгенерировать счет для выбранного заказа"):
        st.info("Функционал генерации счета в разработке.")

def show_analytics_page():
    st.title("📈 Аналитика")
    user_id = st.session_state.user_id
    current_company_id = st.session_state.get('active_company_id')

    st.subheader("Обзор продаж")
    orders = get_orders(user_id, current_company_id)
    if orders:
        df_orders = pd.DataFrame(orders)
        df_orders['created_at'] = pd.to_datetime(df_orders['created_at'])
        df_orders['month'] = df_orders['created_at'].dt.to_period('M')

        monthly_sales = df_orders.groupby('month')['total_payment'].sum().reset_index()
        monthly_sales['month'] = monthly_sales['month'].astype(str)
        fig = px.bar(monthly_sales, x='month', y='total_payment', title='Продажи по месяцам')
        st.plotly_chart(fig)

        st.subheader("Аналитика клиентов (LTV, сегментация)")
        st.write("Здесь будет расширенная аналитика по клиентам, расчет LTV, сегментация и автоматические предложения.")
        st.info("Функционал аналитики клиентов в разработке.")

    else:
        st.info("Нет данных для аналитики.")

def show_inventory_page():
    st.title("🏪 Управление складом")
    user_id = st.session_state.user_id
    current_company_id = st.session_state.get('active_company_id')

    st.subheader("Добавить новый товар на склад")
    with st.form("new_inventory_item_form"):
        product_name = st.text_input("Название товара")
        quantity = st.number_input("Количество", min_value=1)
        link = st.text_input("Ссылка на товар (необязательно)")
       
        # Выбор склада (для мультисклада)
        warehouses = get_warehouses(current_company_id)
        warehouse_options = {w['name']: w['id'] for w in warehouses}
        selected_warehouse_name = st.selectbox("Выберите склад", list(warehouse_options.keys()) if warehouse_options else ["Нет складов"], key="warehouse_select")
        selected_warehouse_id = warehouse_options.get(selected_warehouse_name) if selected_warehouse_name != "Нет складов" else None

        submitted = st.form_submit_button("Добавить товар")
        if submitted:
            if product_name and quantity:
                add_inventory_item(user_id, product_name, quantity, link, current_company_id, selected_warehouse_id)
                st.success(f"Товар '{product_name}' успешно добавлен на склад!")
                st.rerun()
            else:
                st.error("Пожалуйста, заполните все обязательные поля.")

    st.subheader("Список товаров на складе")
    inventory_items = get_inventory_items(user_id, current_company_id)
    if inventory_items:
        df_inventory = pd.DataFrame(inventory_items)
        st.dataframe(df_inventory)

        selected_item_id = st.selectbox("Выберите товар для обновления/удаления", [item['id'] for item in inventory_items])
        if selected_item_id:
            current_item = [item for item in inventory_items if item['id'] == selected_item_id][0]
            new_quantity = st.number_input(f"Новое количество для {current_item['product_name']}", min_value=0, value=current_item['quantity'])
            if st.button("Обновить количество"):
                update_inventory_quantity(selected_item_id, new_quantity)
                st.success("Количество обновлено.")
                if new_quantity < 10: # Пример порога для уведомления
                    send_low_stock_notification(user_id, current_item['product_name'], new_quantity)
                st.rerun()
            if st.button("Удалить товар"):
                delete_inventory_item(selected_item_id)
                st.success("Товар удален со склада.")
                st.rerun()
    else:
        st.info("Склад пуст.")

    st.subheader("Управление складами (Мультисклад)")
    if st.session_state.get('premium_status', False):
        with st.expander("Добавить новый склад"):
            new_warehouse_name = st.text_input("Название нового склада")
            new_warehouse_location = st.text_input("Местоположение нового склада")
            if st.button("Добавить склад"):
                if new_warehouse_name and current_company_id:
                    add_warehouse(current_company_id, new_warehouse_name, new_warehouse_location)
                    st.success(f"Склад '{new_warehouse_name}' добавлен.")
                    st.rerun()
                else:
                    st.error("Пожалуйста, укажите название склада и выберите компанию.")

        st.subheader("Список складов")
        warehouses = get_warehouses(current_company_id)
        if warehouses:
            df_warehouses = pd.DataFrame(warehouses)
            st.dataframe(df_warehouses)
        else:
            st.info("Пока нет добавленных складов.")
    else:
        st.warning("Функция мультисклада доступна только для Премиум+ пользователей.")

def show_notifications_page():
    st.title("🔔 Уведомления")
    user_id = st.session_state.user_id

    notifications = get_notifications(user_id)
    if notifications:
        for notification in notifications:
            status = "(Прочитано)" if notification['is_read'] else "(Не прочитано)"
            st.info(f"{notification['created_at']}: {notification['message']} {status}")
            if not notification['is_read']:
                if st.button(f"Отметить как прочитанное #{notification['id']}", key=f"read_notif_{notification['id']}"):
                    mark_notification_as_read(notification['id'])
                    st.rerun()
    else:
        st.info("У вас пока нет уведомлений.")

def show_smart_page():
    st.title("🧠 ИИ-функции")
    user_id = st.session_state.user_id

    if st.session_state.get('premium_status', False):
        st.subheader("AI-генератор бизнес-идей")
        idea_prompt = st.text_area("Опишите, для чего нужна идея (например, 'идея для нового продукта в сфере e-commerce', 'стратегия маркетинга для малого бизнеса'):")
        if st.button("Сгенерировать идею"):
            if idea_prompt:
                with st.spinner("Генерируем идею..."):
                    # Здесь будет вызов реальной AI модели
                    generated_idea = f"Сгенерированная идея для '{idea_prompt}':\n\n1. **Инновационный продукт:** Создайте SaaS-платформу для автоматизации учета возвратов в e-commerce, интегрированную с популярными CMS и службами доставки. Предложите аналитику по причинам возвратов.\n2. **Маркетинговая стратегия:** Запустите персонализированные email-кампании на основе истории покупок и просмотров, предлагая релевантные товары и скидки. Используйте A/B тестирование для оптимизации.\n3. **Оптимизация процессов:** Внедрите систему предиктивной аналитики для прогнозирования спроса на товары, что позволит оптимизировать складские запасы и снизить издержки.\n\n*Это пример, реальная генерация будет зависеть от подключенной AI модели.*"
                    add_ai_idea(user_id, generated_idea)
                    st.success("Идея сгенерирована и сохранена!")
                    st.rerun()
            else:
                st.warning("Пожалуйста, введите описание для генерации идеи.")
       
        st.subheader("Ваши сгенерированные идеи")
        ai_ideas = get_ai_ideas(user_id)
        if ai_ideas:
            for idea in ai_ideas:
                st.markdown(f"**Идея от {idea['generated_at']}**:\n{idea['idea_text']}")
                st.markdown("---Н")
        else:
            st.info("Пока нет сгенерированных идей.")

        st.subheader("AI-ассистент 24/7")
        st.write("Здесь будет функционал AI-ассистента для генерации документов, ответов на вопросы и обучения сотрудников.")
        st.info("Функционал AI-ассистента в разработке.")

    else:
        st.warning("ИИ-функции доступны только для Премиум+ пользователей.")

def show_settings_page():
    st.title("⚙️ Настройки")
    user_id = st.session_state.user_id
    settings = get_user_settings(user_id)

    if settings:
        st.subheader("Общие настройки")
        new_financial_cushion_percent = st.slider("Процент финансовой подушки (для расчетов)", 0, 100, int(settings['financial_cushion_percent']))
       
        st.subheader("Настройки Email уведомлений")
        new_email_notifications = st.checkbox("Включить Email уведомления", value=settings['email_notifications'])
        new_smtp_server = st.text_input("SMTP Сервер", value=settings['smtp_server'])
        new_smtp_port = st.number_input("SMTP Порт", value=settings['smtp_port'])
        new_email_username = st.text_input("Email (логин)", value=settings['email_username'])
        new_email_password = st.text_input("Пароль Email", type="password", value=settings['email_password'])

        st.subheader("Типы уведомлений")
        new_notify_new_orders = st.checkbox("Уведомлять о новых заказах", value=settings['notify_new_orders'])
        new_notify_low_stock = st.checkbox("Уведомлять о низком остатке на складе", value=settings['notify_low_stock'])
        new_notify_daily_report = st.checkbox("Отправлять ежедневный отчет", value=settings['notify_daily_report'])

        st.subheader("Настройки стоимости доставки (за кг)")
        new_airplane_price_per_kg = st.number_input("Самолет", min_value=0.0, value=settings['airplane_price_per_kg'])
        new_truck_price_per_kg = st.number_input("Грузовик", min_value=0.0, value=settings['truck_price_per_kg'])

        if st.button("Сохранить настройки"):
            update_user_settings(user_id, new_financial_cushion_percent, new_email_notifications, new_smtp_server, new_smtp_port, new_email_username, new_email_password, new_notify_new_orders, new_notify_low_stock, new_notify_daily_report, new_airplane_price_per_kg, new_truck_price_per_kg)
            st.success("Настройки успешно сохранены!")
            st.rerun()
    else:
        st.info("Настройки не найдены. Пожалуйста, войдите в систему.")

    st.subheader("Мультибизнес")
    if st.session_state.get('premium_status', False):
        companies = get_companies_for_user(user_id)
        if companies:
            st.write("Ваши компании:")
            for company in companies:
                col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
                with col1:
                    st.write(f"- {company['name']} (Роль: {company['role']})")
                with col2:
                    if st.button("Выбрать", key=f"select_company_{company['id']}"):
                        st.session_state.active_company_id = company['id']
                        st.success(f"Выбрана компания: {company['name']}")
                        st.rerun()
                with col3:
                    if st.session_state.get('active_company_id') == company['id']:
                        st.success("Активна")
        else:
            st.info("У вас пока нет компаний. Добавьте новую.")

        with st.expander("Добавить новую компанию"):
            new_company_name = st.text_input("Название новой компании")
            if st.button("Создать компанию"):
                if new_company_name:
                    add_company(user_id, new_company_name)
                    st.success(f"Компания '{new_company_name}' создана!")
                    st.rerun()
                else:
                    st.error("Пожалуйста, введите название компании.")

        st.subheader("Управление командой (Гибкая ролевая модель)")
        if st.session_state.get('active_company_id'):
            current_company_id = st.session_state.active_company_id
            st.write(f"Управление командой для компании: {get_company_by_id(current_company_id)['name']}")

            st.markdown("##### Добавить пользователя в команду")
            new_member_email = st.text_input("Email пользователя для добавления")
            new_member_role = st.selectbox("Роль", ["viewer", "editor", "admin"])
            if st.button("Добавить в команду"):
                target_user = get_user_by_email(new_member_email)
                if target_user:
                    if add_user_to_company(target_user['id'], current_company_id, new_member_role):
                        st.success(f"Пользователь {new_member_email} добавлен в команду с ролью {new_member_role}.")
                        st.rerun()
                else:
                    st.error("Пользователь с таким email не найден.")
           
            st.markdown("##### Члены команды")
            team_members = get_users_in_company(current_company_id)
            if team_members:
                for member in team_members:
                    st.write(f"- {member['full_name']} ({member['email']}) - Роль: {member['role']}")
                    if st.session_state.user_id != member['id'] and st.button(f"Изменить роль {member['email']}", key=f"change_role_{member['id']}"):
                        # Здесь можно добавить модальное окно или форму для изменения роли
                        st.info(f"Функционал изменения роли для {member['email']} в разработке.")
                    if st.session_state.user_id != member['id'] and st.button(f"Удалить из команды {member['email']}", key=f"remove_member_{member['id']}"):
                        remove_user_from_company(member['id'], current_company_id)
                        st.success(f"Пользователь {member['email']} удален из команды.")
                        st.rerun()
            else:
                st.info("В этой компании пока нет членов команды.")

        else:
            st.info("Выберите компанию для управления командой.")

        st.subheader("Персональный бренд")
        branding_settings = get_branding_settings(user_id)
        with st.expander("Настроить персональный бренд"):
            new_logo_url = st.text_input("URL логотипа", value=branding_settings['logo_url'] if branding_settings else "")
            new_primary_color = st.color_picker("Основной цвет", value=branding_settings['primary_color'] if branding_settings else "#1E90FF")
            new_secondary_color = st.color_picker("Вторичный цвет", value=branding_settings['secondary_color'] if branding_settings else "#FFD700")
            new_email_signature = st.text_area("Подпись для Email", value=branding_settings['email_signature'] if branding_settings else "")
           
            if st.button("Сохранить настройки бренда"):
                update_branding_settings(user_id, new_logo_url, new_primary_color, new_secondary_color, new_email_signature)
                st.success("Настройки бренда сохранены!")
                st.rerun()

    else:
        st.warning("Функции мультибизнеса, управления командой и персонального бренда доступны только для Премиум+ пользователей.")

    st.subheader("Финансовый контроль")
    if st.session_state.get('premium_status', False):
        with st.expander("Добавить финансовую запись"):
            record_type = st.selectbox("Тип записи", ["tax", "debt", "income", "expense"])
            amount = st.number_input("Сумма", min_value=0.0, format="%.2f")
            description = st.text_area("Описание")
            is_paid = st.checkbox("Оплачено?")
            due_date = st.date_input("Дата оплаты (если применимо)", value=None)
            if st.button("Добавить запись"):
                add_financial_record(user_id, record_type, amount, description, is_paid, due_date)
                st.success("Финансовая запись добавлена.")
                st.rerun()
       
        st.subheader("Ваши финансовые записи")
        financial_records = get_financial_records(user_id)
        if financial_records:
            df_financial = pd.DataFrame(financial_records)
            st.dataframe(df_financial)

            selected_record_id = st.selectbox("Выберите запись для обновления статуса", [r['id'] for r in financial_records])
            if selected_record_id:
                current_record = [r for r in financial_records if r['id'] == selected_record_id][0]
                new_is_paid = st.checkbox(f"Отметить как оплачено для записи #{selected_record_id}", value=current_record['is_paid'])
                if st.button("Обновить статус оплаты"):
                    update_financial_record_status(selected_record_id, new_is_paid)
                    st.success("Статус оплаты обновлен.")
                    st.rerun()
        else:
            st.info("Пока нет финансовых записей.")
    else:
        st.warning("Функции финансового контроля доступны только для Премиум+ пользователей.")

    st.subheader("Безопасность (2FA, резервное копирование, журнал действий)")
    if st.session_state.get('premium_status', False):
        st.write("Здесь будут настройки безопасности: двухфакторная аутентификация, резервное копирование и просмотр журнала действий.")
       
        st.markdown("##### Журнал действий")
        activity_log = get_activity_log(user_id)
        if activity_log:
            df_log = pd.DataFrame(activity_log)
            st.dataframe(df_log)
        else:
            st.info("Журнал действий пуст.")

    else:
        st.warning("Функции безопасности доступны только для Премиум+ пользователей.")

    st.subheader("Экспорт/Импорт")
    if st.session_state.get('premium_status', False):
        st.write("Здесь будет функционал экспорта/импорта данных в различных форматах (Excel, PDF, 1С, Google Sheets).")
        st.info("Функционал экспорта/импорта в разработке.")
    else:
        st.warning("Функции экспорта/импорта доступны только для Премиум+ пользователей.")

    st.subheader("VIP-поддержка")
    if st.session_state.get('premium_status', False):
        st.write("У вас активна VIP-поддержка. Свяжитесь с вашим личным менеджером для быстрой помощи.")
        st.info("Контактная информация личного менеджера будет здесь.")
    else:
        st.warning("VIP-поддержка доступна только для Премиум+ пользователей.")

def show_admin_users_page():
    st.title("👨‍💼 Управление пользователями (Админ)")
    st.write("Здесь администратор может управлять всеми пользователями системы.")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()

    if users:
        df_users = pd.DataFrame(users)
        st.dataframe(df_users)

        st.subheader("Добавить нового пользователя")
        with st.form("new_user_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            full_name = st.text_input("Полное имя")
            is_admin_new = st.checkbox("Сделать администратором")
            premium_status_new = st.checkbox("Премиум+ статус")
            submitted = st.form_submit_button("Добавить пользователя")
            if submitted:
                if add_user(email, password, full_name, is_admin=is_admin_new, premium_status=premium_status_new):
                    st.success(f"Пользователь {email} успешно добавлен.")
                    st.rerun()

        st.subheader("Управление существующими пользователями")
        selected_user_email = st.selectbox("Выберите пользователя для управления", [u['email'] for u in users])
        if selected_user_email:
            selected_user = get_user_by_email(selected_user_email)
            if selected_user:
                st.write(f"**Управление пользователем: {selected_user['full_name']} ({selected_user['email']})**")
                new_premium_status = st.checkbox("Премиум+ статус", value=selected_user['premium_status'], key=f"premium_status_{selected_user['id']}")
                if st.button("Обновить премиум статус", key=f"update_premium_{selected_user['id']}"):
                    update_user_premium_status(selected_user['id'], new_premium_status)
                    st.success("Статус обновлен.")
                    st.rerun()

    else:
        st.info("Пока нет зарегистрированных пользователей.")

def show_admin_payments_page():
    st.title("👨‍💼 Управление платежами (Админ)")
    st.write("Здесь администратор может просматривать и управлять платежами.")
    st.info("Функционал управления платежами в разработке.")

def show_admin_stats_page():
    st.title("👨‍💼 Статистика системы (Админ)")
    st.write("Здесь администратор может просматривать общую статистику системы.")
    st.info("Функционал статистики системы в разработке.")

def show_admin_reports_page():
    st.title("👨‍💼 Отчеты системы (Админ)")
    st.write("Здесь администратор может генерировать отчеты по всей системе.")
    st.info("Функционал отчетов системы в разработке.")

def show_admin_settings_page():
    st.title("👨‍💼 Админ настройки")
    st.write("Здесь будут общие настройки для администратора.")
    st.info("Функционал админ настроек в разработке.")

# --- Основное приложение Streamlit ---
init_db()

# Инициализация session_state для навигации
if 'current_page' not in st.session_state:
    st.session_state.current_page = "dashboard"
if 'admin_page' not in st.session_state:
    st.session_state.admin_page = "users" # Дефолтная страница для админки

# Получаем user_id после успешного логина
if 'username' in st.session_state:
    logged_in_user = get_user_by_email(st.session_state.username)
    if logged_in_user:
        st.session_state.user_id = logged_in_user['id']
        st.session_state.is_admin = logged_in_user['is_admin']
        st.session_state.premium_status = logged_in_user['premium_status']
        update_user_last_login(st.session_state.user_id)

        # Устанавливаем активную компанию по умолчанию, если ее нет
        if 'active_company_id' not in st.session_state:
            companies = get_companies_for_user(st.session_state.user_id)
            if companies:
                # Выбираем первую компанию, где пользователь является владельцем или админом
                owner_company = next((c for c in companies if c['role'] in ['owner', 'admin']), None)
                if owner_company:
                    st.session_state.active_company_id = owner_company['id']
                else:
                    st.session_state.active_company_id = companies[0]['id'] # Или любую первую
            else:
                # Если компаний нет, создаем дефолтную для пользователя
                default_company_name = f"Компания {logged_in_user['full_name'] or logged_in_user['email']}"
                new_company_id = add_company(st.session_state.user_id, default_company_name)
                st.session_state.active_company_id = new_company_id
                st.success(f"Создана компания по умолчанию: {default_company_name}")

        # Отображение навигации
        show_modern_navigation()
        show_admin_navigation()

        # Отображение страниц
        if st.session_state.current_page == "dashboard":
            show_dashboard_page()
        elif st.session_state.current_page == "orders":
            show_orders_page()
        elif st.session_state.current_page == "order_management":
            show_order_management_page()
        elif st.session_state.current_page == "analytics":
            show_analytics_page()
        elif st.session_state.current_page == "inventory":
            show_inventory_page()
        elif st.session_state.current_page == "notifications":
            show_notifications_page()
        elif st.session_state.current_page == "smart":
            show_smart_page()
        elif st.session_state.current_page == "settings":
            show_settings_page()
        elif st.session_state.current_page == "admin":
            if st.session_state.admin_page == "users":
                show_admin_users_page()
            elif st.session_state.admin_page == "payments":
                show_admin_payments_page()
            elif st.session_state.admin_page == "stats":
                show_admin_stats_page()
            elif st.session_state.admin_page == "reports":
                show_admin_reports_page()
            elif st.session_state.admin_page == "admin_settings":
                show_admin_settings_page()
    else:
        st.error("Пользователь не найден в базе данных. Пожалуйста, свяжитесь с администратором.")
else:
    st.info("Пожалуйста, войдите в систему.")

# Запуск планировщика задач в фоновом режиме (если еще не запущен)
if 'scheduler_started' not in st.session_state:
    start_automation_for_user(st.session_state.user_id, daily=True, monthly=True) # Пример запуска
    st.session_state.scheduler_started = True

# CSS для скрытия Streamlit элементов (если нужно)
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)


