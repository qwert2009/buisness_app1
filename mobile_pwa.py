"""
Mobile and PWA Support - Модуль поддержки мобильных устройств и PWA
Включает в себя адаптивные стили и PWA функционал
"""

import streamlit as st
import json
import base64

def add_mobile_styles():
    """Добавление мобильных стилей"""
    st.markdown("""
    <style>
    /* Мобильные стили */
    @media screen and (max-width: 768px) {
        /* Основной контейнер */
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
            padding-top: 1rem;
        }
        
        /* Гамбургер меню для мобильных */
        .hamburger-menu {
            position: fixed;
            top: 10px;
            left: 10px;
            z-index: 1001;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 50px;
            padding: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(10px);
        }
        
        .hamburger-icon {
            width: 25px;
            height: 25px;
        }
        
        /* Боковое меню на мобильных */
        .sidebar-menu {
            width: 280px;
            left: -280px;
            padding: 60px 15px 20px;
        }
        
        .sidebar-menu.open {
            left: 0;
        }
        
        .menu-item {
            padding: 12px 15px;
            font-size: 0.9rem;
        }
        
        /* Метрики на мобильных */
        .metric-card {
            margin: 8px 0;
            padding: 15px;
        }
        
        .metric-value {
            font-size: 2rem;
        }
        
        .metric-label {
            font-size: 0.9rem;
        }
        
        /* Кнопки на мобильных */
        .custom-button {
            padding: 10px 20px;
            font-size: 0.9rem;
            width: 100%;
            margin: 5px 0;
        }
        
        /* Формы на мобильных */
        .custom-form {
            padding: 20px 15px;
            margin: 15px 0;
        }
        
        /* Таблицы на мобильных */
        .custom-table {
            font-size: 0.85rem;
        }
        
        .custom-table th,
        .custom-table td {
            padding: 8px 10px;
        }
        
        /* Чат на мобильных */
        .chat-container {
            max-height: 300px;
            padding: 15px;
        }
        
        .chat-message {
            max-width: 90%;
            padding: 10px 12px;
            font-size: 0.9rem;
        }
        
        /* Заголовки на мобильных */
        .custom-header {
            padding: 15px;
            margin-bottom: 20px;
        }
        
        .custom-header h1 {
            font-size: 2rem;
        }
        
        .custom-header p {
            font-size: 1rem;
        }
        
        /* Уведомления на мобильных */
        .notification {
            padding: 12px 15px;
            font-size: 0.9rem;
        }
        
        /* Селектор компаний на мобильных */
        .company-selector {
            margin-bottom: 15px;
        }
        
        /* Графики на мобильных */
        .js-plotly-plot {
            width: 100% !important;
        }
        
        /* Скрытие элементов на мобильных */
        .hide-on-mobile {
            display: none !important;
        }
        
        /* Streamlit элементы на мобильных */
        .stSelectbox > div > div {
            font-size: 0.9rem;
        }
        
        .stTextInput > div > div > input {
            font-size: 0.9rem;
        }
        
        .stTextArea > div > div > textarea {
            font-size: 0.9rem;
        }
        
        .stButton > button {
            width: 100%;
            font-size: 0.9rem;
            padding: 0.5rem 1rem;
        }
        
        /* Колонки на мобильных */
        .row-widget.stHorizontal > div {
            flex-direction: column;
        }
        
        .row-widget.stHorizontal > div > div {
            width: 100% !important;
            margin-bottom: 1rem;
        }
    }
    
    /* Планшетные стили */
    @media screen and (min-width: 769px) and (max-width: 1024px) {
        .sidebar-menu {
            width: 320px;
            left: -320px;
        }
        
        .metric-card {
            padding: 18px;
        }
        
        .custom-form {
            padding: 25px;
        }
    }
    
    /* Сенсорные устройства */
    @media (hover: none) and (pointer: coarse) {
        .menu-item:hover {
            background: rgba(255, 255, 255, 0.2);
            transform: none;
        }
        
        .custom-button:hover {
            transform: none;
        }
        
        .metric-card:hover {
            transform: none;
        }
        
        /* Увеличиваем области касания */
        .menu-item {
            min-height: 44px;
            display: flex;
            align-items: center;
        }
        
        .custom-button {
            min-height: 44px;
        }
        
        .hamburger-menu {
            min-width: 44px;
            min-height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
    }
    
    /* Поддержка темной темы */
    @media (prefers-color-scheme: dark) {
        .hamburger-menu {
            background: rgba(40, 40, 40, 0.95);
        }
        
        .hamburger-line {
            background-color: #fff;
        }
        
        .custom-form {
            background: #2d2d2d;
            color: #fff;
        }
        
        .notification.info {
            background-color: #1a4d5c;
            border-color: #17a2b8;
            color: #b8e6f0;
        }
    }
    
    /* Ориентация устройства */
    @media screen and (orientation: landscape) and (max-height: 600px) {
        .custom-header {
            padding: 10px;
            margin-bottom: 15px;
        }
        
        .custom-header h1 {
            font-size: 1.8rem;
        }
        
        .metric-card {
            padding: 12px;
        }
        
        .metric-value {
            font-size: 1.8rem;
        }
    }
    
    /* Высокая плотность пикселей */
    @media (-webkit-min-device-pixel-ratio: 2), (min-resolution: 192dpi) {
        .hamburger-line {
            height: 2px;
        }
        
        .status-indicator {
            width: 8px;
            height: 8px;
        }
    }
    </style>
    """, unsafe_allow_html=True)

def add_pwa_support():
    """Добавление PWA поддержки"""
    
    # Создаем манифест PWA
    manifest = {
        "name": "Бизнес Менеджер Премиум+",
        "short_name": "БизнесМенеджер",
        "description": "Полнофункциональная система управления бизнесом с ИИ",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#667eea",
        "theme_color": "#667eea",
        "orientation": "portrait-primary",
        "categories": ["business", "productivity", "finance"],
        "lang": "ru",
        "dir": "ltr",
        "icons": [
            {
                "src": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTkyIiBoZWlnaHQ9IjE5MiIgdmlld0JveD0iMCAwIDE5MiAxOTIiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxOTIiIGhlaWdodD0iMTkyIiByeD0iMjQiIGZpbGw9InVybCgjZ3JhZGllbnQwX2xpbmVhcl8xXzEpIi8+CjxwYXRoIGQ9Ik00OCA2NEg5NlY4MEg0OFY2NFoiIGZpbGw9IndoaXRlIi8+CjxwYXRoIGQ9Ik00OCA5NkgxNDRWMTEySDQ4Vjk2WiIgZmlsbD0id2hpdGUiLz4KPHA+CjxkZWZzPgo8bGluZWFyR3JhZGllbnQgaWQ9ImdyYWRpZW50MF9saW5lYXJfMV8xIiB4MT0iMCIgeTE9IjAiIHgyPSIxOTIiIHkyPSIxOTIiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KPHN0b3Agc3RvcC1jb2xvcj0iIzY2N0VFQSIvPgo8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3NjRCQTIiLz4KPC9saW5lYXJHcmFkaWVudD4KPC9kZWZzPgo8L3N2Zz4K",
                "sizes": "192x192",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            },
            {
                "src": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNTEyIiBoZWlnaHQ9IjUxMiIgdmlld0JveD0iMCAwIDUxMiA1MTIiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSI1MTIiIGhlaWdodD0iNTEyIiByeD0iNjQiIGZpbGw9InVybCgjZ3JhZGllbnQwX2xpbmVhcl8xXzEpIi8+CjxwYXRoIGQ9Ik0xMjggMTcwSDI1NlYyMTNIMTI4VjE3MFoiIGZpbGw9IndoaXRlIi8+CjxwYXRoIGQ9Ik0xMjggMjU2SDM4NFYyOTlIMTI4VjI1NloiIGZpbGw9IndoaXRlIi8+CjxkZWZzPgo8bGluZWFyR3JhZGllbnQgaWQ9ImdyYWRpZW50MF9saW5lYXJfMV8xIiB4MT0iMCIgeTE9IjAiIHgyPSI1MTIiIHkyPSI1MTIiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KPHN0b3Agc3RvcC1jb2xvcj0iIzY2N0VFQSIvPgo8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3NjRCQTIiLz4KPC9saW5lYXJHcmFkaWVudD4KPC9kZWZzPgo8L3N2Zz4K",
                "sizes": "512x512",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ],
        "screenshots": [
            {
                "src": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjU2OCIgdmlld0JveD0iMCAwIDMyMCA1NjgiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMjAiIGhlaWdodD0iNTY4IiBmaWxsPSIjRjhGOUZBIi8+CjxyZWN0IHg9IjIwIiB5PSI2MCIgd2lkdGg9IjI4MCIgaGVpZ2h0PSI4MCIgcng9IjEyIiBmaWxsPSJ1cmwoI2dyYWRpZW50MF9saW5lYXJfMV8xKSIvPgo8dGV4dCB4PSIxNjAiIHk9IjEwNSIgZmlsbD0id2hpdGUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxOCIgZm9udC13ZWlnaHQ9ImJvbGQiIHRleHQtYW5jaG9yPSJtaWRkbGUiPkJpem5lc01hbmFnZXI8L3RleHQ+CjxkZWZzPgo8bGluZWFyR3JhZGllbnQgaWQ9ImdyYWRpZW50MF9saW5lYXJfMV8xIiB4MT0iMjAiIHkxPSI2MCIgeDI9IjMwMCIgeTI9IjE0MCIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPgo8c3RvcCBzdG9wLWNvbG9yPSIjNjY3RUVBIi8+CjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzc2NEJBMiIvPgo8L2xpbmVhckdyYWRpZW50Pgo8L2RlZnM+Cjwvc3ZnPgo=",
                "sizes": "320x568",
                "type": "image/svg+xml",
                "form_factor": "narrow"
            }
        ],
        "shortcuts": [
            {
                "name": "Дашборд",
                "short_name": "Дашборд",
                "description": "Открыть главную панель",
                "url": "/?page=dashboard",
                "icons": [
                    {
                        "src": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOTYiIGhlaWdodD0iOTYiIHZpZXdCb3g9IjAgMCA5NiA5NiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHJlY3Qgd2lkdGg9Ijk2IiBoZWlnaHQ9Ijk2IiByeD0iMTIiIGZpbGw9IiM2NjdFRUEiLz4KPHA+Cjwvc3ZnPgo=",
                        "sizes": "96x96"
                    }
                ]
            },
            {
                "name": "Заказы",
                "short_name": "Заказы",
                "description": "Управление заказами",
                "url": "/?page=orders",
                "icons": [
                    {
                        "src": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOTYiIGhlaWdodD0iOTYiIHZpZXdCb3g9IjAgMCA5NiA5NiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHJlY3Qgd2lkdGg9Ijk2IiBoZWlnaHQ9Ijk2IiByeD0iMTIiIGZpbGw9IiM3NjRCQTIiLz4KPHA+Cjwvc3ZnPgo=",
                        "sizes": "96x96"
                    }
                ]
            }
        ],
        "related_applications": [],
        "prefer_related_applications": False
    }
    
    # Добавляем мета-теги для PWA
    st.markdown(f"""
    <link rel="manifest" href="data:application/json;base64,{base64.b64encode(json.dumps(manifest).encode()).decode()}">
    <meta name="theme-color" content="#667eea">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="БизнесМенеджер">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="application-name" content="БизнесМенеджер">
    <meta name="msapplication-TileColor" content="#667eea">
    <meta name="msapplication-config" content="none">
    """, unsafe_allow_html=True)

def add_service_worker():
    """Добавление Service Worker для PWA"""
    service_worker_js = """
    const CACHE_NAME = 'business-manager-v1';
    const urlsToCache = [
        '/',
        '/static/css/main.css',
        '/static/js/main.js'
    ];

    self.addEventListener('install', function(event) {
        event.waitUntil(
            caches.open(CACHE_NAME)
                .then(function(cache) {
                    return cache.addAll(urlsToCache);
                })
        );
    });

    self.addEventListener('fetch', function(event) {
        event.respondWith(
            caches.match(event.request)
                .then(function(response) {
                    if (response) {
                        return response;
                    }
                    return fetch(event.request);
                }
            )
        );
    });

    // Push notifications
    self.addEventListener('push', function(event) {
        const options = {
            body: event.data ? event.data.text() : 'Новое уведомление',
            icon: '/static/icon-192x192.png',
            badge: '/static/badge-72x72.png',
            vibrate: [100, 50, 100],
            data: {
                dateOfArrival: Date.now(),
                primaryKey: 1
            },
            actions: [
                {
                    action: 'explore',
                    title: 'Открыть',
                    icon: '/static/checkmark.png'
                },
                {
                    action: 'close',
                    title: 'Закрыть',
                    icon: '/static/xmark.png'
                }
            ]
        };

        event.waitUntil(
            self.registration.showNotification('Бизнес Менеджер', options)
        );
    });

    self.addEventListener('notificationclick', function(event) {
        event.notification.close();

        if (event.action === 'explore') {
            event.waitUntil(
                clients.openWindow('/')
            );
        }
    });
    """
    
    # Регистрируем Service Worker
    st.markdown(f"""
    <script>
    if ('serviceWorker' in navigator) {{
        window.addEventListener('load', function() {{
            const swCode = `{service_worker_js}`;
            const blob = new Blob([swCode], {{ type: 'application/javascript' }});
            const swUrl = URL.createObjectURL(blob);
            
            navigator.serviceWorker.register(swUrl)
                .then(function(registration) {{
                    console.log('ServiceWorker registration successful');
                }})
                .catch(function(err) {{
                    console.log('ServiceWorker registration failed: ', err);
                }});
        }});
    }}
    </script>
    """, unsafe_allow_html=True)

def add_push_notification_support():
    """Добавление поддержки push-уведомлений"""
    st.markdown("""
    <script>
    // Запрос разрешения на уведомления
    function requestNotificationPermission() {
        if ('Notification' in window && 'serviceWorker' in navigator) {
            Notification.requestPermission().then(function(permission) {
                if (permission === 'granted') {
                    console.log('Notification permission granted');
                    subscribeUserToPush();
                }
            });
        }
    }
    
    // Подписка на push-уведомления
    function subscribeUserToPush() {
        navigator.serviceWorker.ready.then(function(registration) {
            const applicationServerKey = urlBase64ToUint8Array('YOUR_VAPID_PUBLIC_KEY');
            
            return registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: applicationServerKey
            });
        }).then(function(subscription) {
            console.log('User is subscribed:', subscription);
            // Отправляем подписку на сервер
            sendSubscriptionToServer(subscription);
        }).catch(function(err) {
            console.log('Failed to subscribe the user: ', err);
        });
    }
    
    // Отправка подписки на сервер
    function sendSubscriptionToServer(subscription) {
        // В реальном приложении здесь должен быть API call
        console.log('Subscription sent to server');
    }
    
    // Утилита для конвертации VAPID ключа
    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }
    
    // Показ локального уведомления
    function showLocalNotification(title, body, icon) {
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(title, {
                body: body,
                icon: icon || '/static/icon-192x192.png',
                badge: '/static/badge-72x72.png'
            });
        }
    }
    
    // Автоматический запрос разрешения при загрузке
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(requestNotificationPermission, 2000);
    });
    </script>
    """, unsafe_allow_html=True)

def add_offline_support():
    """Добавление поддержки офлайн режима"""
    st.markdown("""
    <script>
    // Проверка статуса подключения
    function updateOnlineStatus() {
        const statusElement = document.getElementById('connection-status');
        if (navigator.onLine) {
            if (statusElement) {
                statusElement.style.display = 'none';
            }
        } else {
            if (!statusElement) {
                const status = document.createElement('div');
                status.id = 'connection-status';
                status.innerHTML = '🔌 Нет подключения к интернету';
                status.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    background: #f44336;
                    color: white;
                    text-align: center;
                    padding: 10px;
                    z-index: 9999;
                    font-family: Arial, sans-serif;
                `;
                document.body.prepend(status);
            } else {
                statusElement.style.display = 'block';
            }
        }
    }
    
    // Слушатели событий подключения
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);
    
    // Проверка при загрузке
    document.addEventListener('DOMContentLoaded', updateOnlineStatus);
    
    // Кэширование данных в localStorage
    function cacheData(key, data) {
        try {
            localStorage.setItem('bm_' + key, JSON.stringify({
                data: data,
                timestamp: Date.now()
            }));
        } catch (e) {
            console.log('Failed to cache data:', e);
        }
    }
    
    // Получение кэшированных данных
    function getCachedData(key, maxAge = 3600000) { // 1 час по умолчанию
        try {
            const cached = localStorage.getItem('bm_' + key);
            if (cached) {
                const parsed = JSON.parse(cached);
                if (Date.now() - parsed.timestamp < maxAge) {
                    return parsed.data;
                }
            }
        } catch (e) {
            console.log('Failed to get cached data:', e);
        }
        return null;
    }
    </script>
    """, unsafe_allow_html=True)

def add_touch_gestures():
    """Добавление поддержки жестов для сенсорных устройств"""
    st.markdown("""
    <script>
    // Поддержка свайпов для навигации
    let startX = 0;
    let startY = 0;
    let endX = 0;
    let endY = 0;
    
    document.addEventListener('touchstart', function(e) {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
    });
    
    document.addEventListener('touchend', function(e) {
        endX = e.changedTouches[0].clientX;
        endY = e.changedTouches[0].clientY;
        handleSwipe();
    });
    
    function handleSwipe() {
        const deltaX = endX - startX;
        const deltaY = endY - startY;
        const minSwipeDistance = 50;
        
        // Горизонтальный свайп
        if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > minSwipeDistance) {
            if (deltaX > 0) {
                // Свайп вправо - открыть меню
                const menu = document.getElementById('sidebarMenu');
                if (menu && !menu.classList.contains('open')) {
                    menu.classList.add('open');
                }
            } else {
                // Свайп влево - закрыть меню
                const menu = document.getElementById('sidebarMenu');
                if (menu && menu.classList.contains('open')) {
                    menu.classList.remove('open');
                }
            }
        }
    }
    
    // Предотвращение зума при двойном тапе
    let lastTouchEnd = 0;
    document.addEventListener('touchend', function(event) {
        const now = (new Date()).getTime();
        if (now - lastTouchEnd <= 300) {
            event.preventDefault();
        }
        lastTouchEnd = now;
    }, false);
    
    // Улучшенная прокрутка для мобильных
    document.addEventListener('touchmove', function(e) {
        // Разрешаем прокрутку только в определенных контейнерах
        const scrollableElements = ['.chat-container', '.custom-table', '.main'];
        let allowScroll = false;
        
        for (let element of scrollableElements) {
            if (e.target.closest(element)) {
                allowScroll = true;
                break;
            }
        }
        
        if (!allowScroll) {
            e.preventDefault();
        }
    }, { passive: false });
    </script>
    """, unsafe_allow_html=True)

def add_app_install_prompt():
    """Добавление промпта для установки приложения"""
    st.markdown("""
    <script>
    let deferredPrompt;
    
    window.addEventListener('beforeinstallprompt', (e) => {
        // Предотвращаем автоматический показ промпта
        e.preventDefault();
        deferredPrompt = e;
        
        // Показываем кнопку установки
        showInstallButton();
    });
    
    function showInstallButton() {
        const installButton = document.createElement('button');
        installButton.innerHTML = '📱 Установить приложение';
        installButton.className = 'install-button';
        installButton.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 25px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            z-index: 1000;
            font-size: 14px;
            transition: all 0.3s ease;
        `;
        
        installButton.addEventListener('click', installApp);
        document.body.appendChild(installButton);
        
        // Скрываем кнопку через 10 секунд
        setTimeout(() => {
            if (installButton.parentNode) {
                installButton.remove();
            }
        }, 10000);
    }
    
    function installApp() {
        if (deferredPrompt) {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then((choiceResult) => {
                if (choiceResult.outcome === 'accepted') {
                    console.log('User accepted the install prompt');
                } else {
                    console.log('User dismissed the install prompt');
                }
                deferredPrompt = null;
            });
        }
    }
    
    // Отслеживание успешной установки
    window.addEventListener('appinstalled', (evt) => {
        console.log('App was installed');
        // Можно отправить аналитику
    });
    </script>
    """, unsafe_allow_html=True)

def initialize_mobile_pwa():
    """Инициализация всех мобильных и PWA функций"""
    add_mobile_styles()
    add_pwa_support()
    add_service_worker()
    add_push_notification_support()
    add_offline_support()
    add_touch_gestures()
    add_app_install_prompt()
    
    # Добавляем viewport мета-тег для правильного отображения на мобильных
    st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="format-detection" content="telephone=no">
    <meta name="msapplication-tap-highlight" content="no">
    """, unsafe_allow_html=True)

