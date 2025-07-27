"""
UI Components - Модуль компонентов пользовательского интерфейса
Содержит улучшенные компоненты для создания современного дизайна
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import base64

def apply_custom_css():
    """Применение кастомных CSS стилей"""
    st.markdown("""
    <style>
    /* Основные стили */
    .main {
        padding-top: 1rem;
    }
    
    /* Стили для гамбургер меню */
    .hamburger-menu {
        position: fixed;
        top: 20px;
        left: 20px;
        z-index: 1000;
        background: rgba(255, 255, 255, 0.9);
        border-radius: 50px;
        padding: 10px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        backdrop-filter: blur(10px);
    }
    
    .hamburger-icon {
        width: 30px;
        height: 30px;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        justify-content: space-around;
    }
    
    .hamburger-line {
        width: 100%;
        height: 3px;
        background-color: #333;
        border-radius: 2px;
        transition: all 0.3s ease;
    }
    
    /* Боковое меню */
    .sidebar-menu {
        position: fixed;
        top: 0;
        left: -300px;
        width: 300px;
        height: 100vh;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        transition: left 0.3s ease;
        z-index: 999;
        padding: 80px 20px 20px;
        box-shadow: 2px 0 10px rgba(0, 0, 0, 0.1);
    }
    
    .sidebar-menu.open {
        left: 0;
    }
    
    .menu-item {
        display: block;
        color: white;
        text-decoration: none;
        padding: 15px 20px;
        margin: 5px 0;
        border-radius: 10px;
        transition: all 0.3s ease;
        font-weight: 500;
    }
    
    .menu-item:hover {
        background: rgba(255, 255, 255, 0.2);
        transform: translateX(5px);
    }
    
    .menu-item.active {
        background: rgba(255, 255, 255, 0.3);
    }
    
    /* Карточки */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 15px;
        color: white;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        margin: 10px 0;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: bold;
        margin: 10px 0;
    }
    
    .metric-label {
        font-size: 1rem;
        opacity: 0.9;
    }
    
    .metric-change {
        font-size: 0.9rem;
        margin-top: 5px;
    }
    
    /* Кнопки */
    .custom-button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 25px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
    }
    
    .custom-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
    }
    
    /* Статус индикаторы */
    .status-indicator {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 8px;
    }
    
    .status-active { background-color: #4CAF50; }
    .status-pending { background-color: #FF9800; }
    .status-inactive { background-color: #F44336; }
    
    /* Анимации */
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .fade-in-up {
        animation: fadeInUp 0.6s ease-out;
    }
    
    /* Премиум бейдж */
    .premium-badge {
        background: linear-gradient(45deg, #FFD700, #FFA500);
        color: #333;
        padding: 4px 12px;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-block;
        margin-left: 10px;
    }
    
    /* Чат стили */
    .chat-container {
        max-height: 400px;
        overflow-y: auto;
        padding: 20px;
        background: #f8f9fa;
        border-radius: 15px;
        margin: 20px 0;
    }
    
    .chat-message {
        margin: 10px 0;
        padding: 12px 16px;
        border-radius: 18px;
        max-width: 70%;
        word-wrap: break-word;
    }
    
    .chat-message.own {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        margin-left: auto;
        text-align: right;
    }
    
    .chat-message.other {
        background: white;
        color: #333;
        border: 1px solid #e0e0e0;
    }
    
    /* Таблицы */
    .custom-table {
        background: white;
        border-radius: 15px;
        overflow: hidden;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    }
    
    .custom-table th {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 15px;
        font-weight: 600;
    }
    
    .custom-table td {
        padding: 12px 15px;
        border-bottom: 1px solid #f0f0f0;
    }
    
    .custom-table tr:hover {
        background-color: #f8f9fa;
    }
    
    /* Формы */
    .custom-form {
        background: white;
        padding: 30px;
        border-radius: 20px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        margin: 20px 0;
    }
    
    /* Уведомления */
    .notification {
        padding: 15px 20px;
        border-radius: 10px;
        margin: 10px 0;
        border-left: 4px solid;
    }
    
    .notification.success {
        background-color: #d4edda;
        border-color: #28a745;
        color: #155724;
    }
    
    .notification.warning {
        background-color: #fff3cd;
        border-color: #ffc107;
        color: #856404;
    }
    
    .notification.error {
        background-color: #f8d7da;
        border-color: #dc3545;
        color: #721c24;
    }
    
    .notification.info {
        background-color: #d1ecf1;
        border-color: #17a2b8;
        color: #0c5460;
    }
    
    /* Мобильная адаптация */
    @media (max-width: 768px) {
        .sidebar-menu {
            width: 280px;
        }
        
        .metric-card {
            margin: 5px 0;
            padding: 15px;
        }
        
        .metric-value {
            font-size: 2rem;
        }
        
        .chat-message {
            max-width: 85%;
        }
    }
    
    /* Скрытие стандартных элементов Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Кастомный header */
    .custom-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 30px;
        text-align: center;
    }
    
    .custom-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
    }
    
    .custom-header p {
        margin: 10px 0 0 0;
        opacity: 0.9;
        font-size: 1.1rem;
    }
    </style>
    """, unsafe_allow_html=True)

def create_hamburger_menu():
    """Создание гамбургер меню"""
    st.markdown("""
    <div class="hamburger-menu" onclick="toggleMenu()">
        <div class="hamburger-icon">
            <div class="hamburger-line"></div>
            <div class="hamburger-line"></div>
            <div class="hamburger-line"></div>
        </div>
    </div>
    
    <div class="sidebar-menu" id="sidebarMenu">
        <a href="#" class="menu-item" onclick="navigateTo('dashboard')">
            📊 Дашборд
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('orders')">
            📦 Заказы
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('inventory')">
            📋 Склад
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('customers')">
            👥 Клиенты
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('finance')">
            💰 Финансы
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('analytics')">
            📈 Аналитика
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('chat')">
            💬 Чат <span class="premium-badge">PREMIUM+</span>
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('automation')">
            🔄 Автоматизация <span class="premium-badge">PREMIUM+</span>
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('integrations')">
            🔗 Интеграции <span class="premium-badge">PREMIUM+</span>
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('companies')">
            🏢 Компании
        </a>
        <a href="#" class="menu-item" onclick="navigateTo('settings')">
            ⚙️ Настройки
        </a>
    </div>
    
    <script>
    function toggleMenu() {
        const menu = document.getElementById('sidebarMenu');
        menu.classList.toggle('open');
    }
    
    function navigateTo(page) {
        // Закрываем меню
        const menu = document.getElementById('sidebarMenu');
        menu.classList.remove('open');
        
        // Здесь должна быть логика навигации
        // В Streamlit это можно реализовать через session_state
        console.log('Navigate to:', page);
    }
    
    // Закрытие меню при клике вне его
    document.addEventListener('click', function(event) {
        const menu = document.getElementById('sidebarMenu');
        const hamburger = document.querySelector('.hamburger-menu');
        
        if (!menu.contains(event.target) && !hamburger.contains(event.target)) {
            menu.classList.remove('open');
        }
    });
    </script>
    """, unsafe_allow_html=True)

def create_metric_card(title, value, change=None, change_type="positive"):
    """Создание карточки метрики"""
    change_color = "#4CAF50" if change_type == "positive" else "#F44336"
    change_icon = "↗" if change_type == "positive" else "↘"
    
    change_html = ""
    if change:
        change_html = f'<div class="metric-change" style="color: {change_color};">{change_icon} {change}</div>'
    
    st.markdown(f"""
    <div class="metric-card fade-in-up">
        <div class="metric-label">{title}</div>
        <div class="metric-value">{value}</div>
        {change_html}
    </div>
    """, unsafe_allow_html=True)

def create_status_indicator(status):
    """Создание индикатора статуса"""
    status_class = {
        "active": "status-active",
        "pending": "status-pending", 
        "inactive": "status-inactive"
    }.get(status, "status-inactive")
    
    return f'<span class="status-indicator {status_class}"></span>'

def create_notification(message, type="info"):
    """Создание уведомления"""
    st.markdown(f"""
    <div class="notification {type}">
        {message}
    </div>
    """, unsafe_allow_html=True)

def create_custom_header(title, subtitle=None):
    """Создание кастомного заголовка"""
    subtitle_html = f"<p>{subtitle}</p>" if subtitle else ""
    
    st.markdown(f"""
    <div class="custom-header fade-in-up">
        <h1>{title}</h1>
        {subtitle_html}
    </div>
    """, unsafe_allow_html=True)

def create_chart_container(chart, title=None):
    """Создание контейнера для графика"""
    title_html = f"<h3 style='text-align: center; color: #333; margin-bottom: 20px;'>{title}</h3>" if title else ""
    
    st.markdown(f"""
    <div class="custom-form">
        {title_html}
    </div>
    """, unsafe_allow_html=True)
    
    st.plotly_chart(chart, use_container_width=True)

def create_data_table(df, title=None):
    """Создание кастомной таблицы"""
    if title:
        st.markdown(f"<h3 style='color: #333; margin-bottom: 20px;'>{title}</h3>", unsafe_allow_html=True)
    
    # Применяем кастомные стили к таблице
    st.markdown('<div class="custom-table">', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

def create_premium_feature_lock(feature_name):
    """Создание блокировки премиум функции"""
    st.markdown(f"""
    <div class="custom-form" style="text-align: center; background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%); color: #333;">
        <h3>🔒 {feature_name}</h3>
        <p>Эта функция доступна только для пользователей Премиум+</p>
        <button class="custom-button" style="background: #333; margin-top: 15px;">
            Обновить до Премиум+
        </button>
    </div>
    """, unsafe_allow_html=True)

def create_loading_spinner():
    """Создание спиннера загрузки"""
    st.markdown("""
    <div style="display: flex; justify-content: center; align-items: center; height: 100px;">
        <div style="border: 4px solid #f3f3f3; border-top: 4px solid #667eea; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite;"></div>
    </div>
    
    <style>
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    </style>
    """, unsafe_allow_html=True)

def create_progress_bar(progress, label=""):
    """Создание прогресс-бара"""
    st.markdown(f"""
    <div style="margin: 20px 0;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
            <span style="color: #333; font-weight: 500;">{label}</span>
            <span style="color: #667eea; font-weight: 600;">{progress}%</span>
        </div>
        <div style="background-color: #e0e0e0; border-radius: 10px; height: 8px; overflow: hidden;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100%; width: {progress}%; transition: width 0.3s ease;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def create_feature_card(icon, title, description, is_premium=False):
    """Создание карточки функции"""
    premium_badge = '<span class="premium-badge">PREMIUM+</span>' if is_premium else ''
    
    st.markdown(f"""
    <div class="custom-form" style="text-align: center; min-height: 200px; display: flex; flex-direction: column; justify-content: center;">
        <div style="font-size: 3rem; margin-bottom: 15px;">{icon}</div>
        <h3 style="color: #333; margin-bottom: 10px;">{title} {premium_badge}</h3>
        <p style="color: #666; line-height: 1.6;">{description}</p>
    </div>
    """, unsafe_allow_html=True)

def create_stats_grid(stats_data):
    """Создание сетки статистики"""
    cols = st.columns(len(stats_data))
    
    for i, (title, value, change, change_type) in enumerate(stats_data):
        with cols[i]:
            create_metric_card(title, value, change, change_type)

def create_action_buttons(buttons_data):
    """Создание группы кнопок действий"""
    cols = st.columns(len(buttons_data))
    
    for i, (label, key) in enumerate(buttons_data):
        with cols[i]:
            if st.button(label, key=key, use_container_width=True):
                return key
    
    return None

def get_base64_image(image_path):
    """Получение base64 представления изображения"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except:
        return None

def create_company_selector():
    """Создание селектора компаний"""
    if 'user_companies' in st.session_state and st.session_state.user_companies:
        companies = st.session_state.user_companies
        
        # Создаем красивый селектор компаний
        st.markdown("""
        <div style="background: white; padding: 15px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <label style="color: #333; font-weight: 600; margin-bottom: 10px; display: block;">Активная компания:</label>
        </div>
        """, unsafe_allow_html=True)
        
        company_options = {f"{comp['name']} ({comp['id']})": comp['id'] for comp in companies}
        
        selected_company_key = st.selectbox(
            "",
            options=list(company_options.keys()),
            key="company_selector",
            label_visibility="collapsed"
        )
        
        if selected_company_key:
            selected_company_id = company_options[selected_company_key]
            st.session_state.active_company_id = selected_company_id
            
            # Находим выбранную компанию
            selected_company = next((comp for comp in companies if comp['id'] == selected_company_id), None)
            if selected_company:
                st.session_state.active_company = selected_company

