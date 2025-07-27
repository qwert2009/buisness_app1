"""
AI Services Module - Модуль ИИ сервисов для Премиум+ функций
Включает в себя аналитику, прогнозы, автоматизацию и AI-ассистента
"""

import openai
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import sqlite3
import random
from typing import Dict, List, Optional, Tuple, Any
import schedule
import time
from threading import Thread
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import plotly.express as px
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

class AIAnalyticsService:
    """Сервис ИИ-аналитики для прогнозов и рекомендаций"""
    
    def __init__(self, db_path='business_manager.db'):
        self.db_path = db_path
        self.openai_available = bool(openai.api_key)
    
    def get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def generate_sales_forecast(self, user_id: int, company_id: int, days: int = 30) -> Dict:
        """Генерация прогноза продаж"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Получаем исторические данные продаж
        cursor.execute("""
            SELECT DATE(created_at) as date, SUM(total_amount) as daily_sales
            FROM orders 
            WHERE user_id = ? AND company_id = ?
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 90
        """, (user_id, company_id))
        
        historical_data = cursor.fetchall()
        conn.close()
        
        if len(historical_data) < 7:
            # Генерируем демо-данные для примера
            dates = pd.date_range(start=datetime.now() - timedelta(days=90), periods=90, freq='D')
            sales = [random.randint(1000, 5000) + random.randint(-500, 500) for _ in range(90)]
            historical_df = pd.DataFrame({'date': dates, 'sales': sales})
        else:
            historical_df = pd.DataFrame(historical_data)
            historical_df['date'] = pd.to_datetime(historical_df['date'])
        
        # Простой линейный прогноз
        historical_df['day_number'] = range(len(historical_df))
        
        # Обучаем модель
        X = historical_df[['day_number']].values
        y = historical_df['sales'].values
        
        model = LinearRegression()
        model.fit(X, y)
        
        # Генерируем прогноз
        future_days = range(len(historical_df), len(historical_df) + days)
        future_X = np.array(future_days).reshape(-1, 1)
        forecast = model.predict(future_X)
        
        # Добавляем случайность для реалистичности
        forecast = [max(0, f + random.randint(-200, 200)) for f in forecast]
        
        forecast_dates = pd.date_range(start=datetime.now(), periods=days, freq='D')
        
        # Сохраняем прогноз в БД
        self.save_prediction(user_id, company_id, 'sales', {
            'forecast': list(forecast),
            'dates': [d.isoformat() for d in forecast_dates],
            'confidence': 0.75,
            'model': 'linear_regression'
        })
        
        return {
            'forecast': forecast,
            'dates': forecast_dates.tolist(),
            'confidence_score': 0.75,
            'trend': 'increasing' if model.coef_[0] > 0 else 'decreasing',
            'total_predicted': sum(forecast)
        }
    
    def generate_inventory_recommendations(self, user_id: int, company_id: int) -> List[Dict]:
        """Генерация рекомендаций по складу"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные о товарах и их движении
        cursor.execute("""
            SELECT i.id, i.name, i.quantity, i.min_stock,
                   COUNT(oi.id) as orders_count,
                   SUM(oi.quantity) as total_sold
            FROM inventory i
            LEFT JOIN order_items oi ON i.id = oi.product_id
            WHERE i.user_id = ? AND i.company_id = ?
            GROUP BY i.id
        """, (user_id, company_id))
        
        inventory_data = cursor.fetchall()
        conn.close()
        
        recommendations = []
        
        for item in inventory_data:
            # Критический остаток
            if item['quantity'] <= item['min_stock']:
                recommendations.append({
                    'type': 'critical_stock',
                    'priority': 'high',
                    'title': f"Критический остаток: {item['name']}",
                    'description': f"Осталось {item['quantity']} единиц. Рекомендуется пополнить запас.",
                    'action': 'restock',
                    'product_id': item['id'],
                    'suggested_quantity': max(50, item['total_sold'] or 0)
                })
            
            # Популярные товары
            if item['total_sold'] and item['total_sold'] > 10:
                recommendations.append({
                    'type': 'popular_product',
                    'priority': 'medium',
                    'title': f"Популярный товар: {item['name']}",
                    'description': f"Продано {item['total_sold']} единиц. Рассмотрите увеличение запаса.",
                    'action': 'increase_stock',
                    'product_id': item['id'],
                    'suggested_quantity': int(item['total_sold'] * 1.5)
                })
            
            # Неликвидные товары
            if item['quantity'] > 100 and (item['total_sold'] or 0) < 5:
                recommendations.append({
                    'type': 'slow_moving',
                    'priority': 'low',
                    'title': f"Неликвидный товар: {item['name']}",
                    'description': f"Большой запас ({item['quantity']} ед.), но низкие продажи.",
                    'action': 'promotion',
                    'product_id': item['id']
                })
        
        # Сохраняем рекомендации
        for rec in recommendations:
            self.save_recommendation(user_id, company_id, rec['type'], rec)
        
        return recommendations
    
    def generate_customer_insights(self, user_id: int, company_id: int) -> Dict:
        """Анализ клиентов и сегментация"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные о заказах
        cursor.execute("""
            SELECT customer_name, customer_email, total_amount, created_at
            FROM orders 
            WHERE user_id = ? AND company_id = ?
            ORDER BY created_at DESC
        """, (user_id, company_id))
        
        orders_data = cursor.fetchall()
        conn.close()
        
        if not orders_data:
            return {'message': 'Недостаточно данных для анализа клиентов'}
        
        # Анализ клиентов
        customer_stats = {}
        for order in orders_data:
            email = order['customer_email'] or 'unknown'
            if email not in customer_stats:
                customer_stats[email] = {
                    'name': order['customer_name'],
                    'total_spent': 0,
                    'order_count': 0,
                    'first_order': order['created_at'],
                    'last_order': order['created_at']
                }
            
            customer_stats[email]['total_spent'] += order['total_amount']
            customer_stats[email]['order_count'] += 1
            customer_stats[email]['last_order'] = max(
                customer_stats[email]['last_order'], 
                order['created_at']
            )
        
        # Сегментация клиентов
        segments = {
            'vip': [],      # > 50000 руб
            'regular': [],  # 10000-50000 руб
            'new': [],      # < 10000 руб
            'inactive': []  # не покупали > 30 дней
        }
        
        for email, stats in customer_stats.items():
            days_since_last = (datetime.now() - datetime.fromisoformat(stats['last_order'])).days
            
            if days_since_last > 30:
                segments['inactive'].append(stats)
            elif stats['total_spent'] > 50000:
                segments['vip'].append(stats)
            elif stats['total_spent'] > 10000:
                segments['regular'].append(stats)
            else:
                segments['new'].append(stats)
        
        # Рекомендации по работе с клиентами
        recommendations = []
        
        if segments['inactive']:
            recommendations.append({
                'type': 'reactivation_campaign',
                'title': 'Реактивация неактивных клиентов',
                'description': f"У вас {len(segments['inactive'])} неактивных клиентов. Запустите email-кампанию с персональными предложениями.",
                'priority': 'high'
            })
        
        if segments['vip']:
            recommendations.append({
                'type': 'vip_program',
                'title': 'VIP-программа',
                'description': f"У вас {len(segments['vip'])} VIP-клиентов. Создайте для них специальную программу лояльности.",
                'priority': 'medium'
            })
        
        return {
            'segments': {k: len(v) for k, v in segments.items()},
            'total_customers': len(customer_stats),
            'average_ltv': sum(s['total_spent'] for s in customer_stats.values()) / len(customer_stats),
            'recommendations': recommendations
        }
    
    def save_prediction(self, user_id: int, company_id: int, prediction_type: str, data: Dict):
        """Сохранение прогноза в БД"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO ai_predictions (user_id, company_id, prediction_type, prediction_data, confidence_score)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, company_id, prediction_type, json.dumps(data), data.get('confidence', 0.5)))
        
        conn.commit()
        conn.close()
    
    def save_recommendation(self, user_id: int, company_id: int, rec_type: str, data: Dict):
        """Сохранение рекомендации в БД"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO ai_recommendations (user_id, company_id, recommendation_type, title, description, action_data, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, company_id, rec_type, 
            data.get('title', ''), 
            data.get('description', ''),
            json.dumps(data),
            1 if data.get('priority') == 'high' else 2 if data.get('priority') == 'medium' else 3
        ))
        
        conn.commit()
        conn.close()

class AIAssistantService:
    """AI-ассистент для генерации документов и ответов на вопросы"""
    
    def __init__(self):
        self.openai_available = bool(openai.api_key)
    
    def generate_business_document(self, document_type: str, context: Dict) -> str:
        """Генерация бизнес-документов"""
        if not self.openai_available:
            return self._generate_demo_document(document_type, context)
        
        prompts = {
            'business_plan': f"Создай бизнес-план для компании '{context.get('company_name', 'Моя компания')}' в сфере {context.get('industry', 'услуг')}",
            'marketing_strategy': f"Разработай маркетинговую стратегию для {context.get('product', 'продукта')} с бюджетом {context.get('budget', '100000')} рублей",
            'sales_report': f"Создай отчет по продажам на основе данных: {context.get('sales_data', 'нет данных')}",
            'job_description': f"Напиши описание вакансии для позиции {context.get('position', 'менеджер')} в компании {context.get('company_name', 'Моя компания')}",
            'contract_template': f"Создай шаблон договора для {context.get('service_type', 'услуг')} компании {context.get('company_name', 'Моя компания')}"
        }
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты профессиональный бизнес-консультант. Создавай качественные деловые документы на русском языке."},
                    {"role": "user", "content": prompts.get(document_type, f"Создай документ типа {document_type}")}
                ],
                max_tokens=1500,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Ошибка генерации документа: {str(e)}"
    
    def _generate_demo_document(self, document_type: str, context: Dict) -> str:
        """Демо-генерация документов без OpenAI"""
        templates = {
            'business_plan': f"""
# БИЗНЕС-ПЛАН
## {context.get('company_name', 'Моя компания')}

### 1. Описание бизнеса
Компания {context.get('company_name', 'Моя компания')} специализируется на {context.get('industry', 'предоставлении услуг')}.

### 2. Анализ рынка
- Размер рынка: растущий сегмент
- Целевая аудитория: {context.get('target_audience', 'малый и средний бизнес')}
- Конкуренты: анализ показывает возможности для роста

### 3. Маркетинговая стратегия
- Цифровой маркетинг
- Партнерские программы
- Прямые продажи

### 4. Финансовый план
- Стартовые инвестиции: {context.get('investment', '500,000')} руб.
- Прогноз выручки: рост 20% в год
- Точка безубыточности: 12 месяцев

### 5. Команда
- Основатель: опыт в отрасли
- Ключевые сотрудники: планируется найм
            """,
            'marketing_strategy': f"""
# МАРКЕТИНГОВАЯ СТРАТЕГИЯ

## Продукт: {context.get('product', 'Наш продукт')}
## Бюджет: {context.get('budget', '100,000')} руб.

### 1. Целевая аудитория
- Основная: предприниматели 25-45 лет
- Дополнительная: малый бизнес

### 2. Каналы продвижения
- Социальные сети (30% бюджета)
- Контекстная реклама (40% бюджета)
- Email-маркетинг (20% бюджета)
- Мероприятия (10% бюджета)

### 3. KPI
- Увеличение продаж на 25%
- Рост узнаваемости бренда
- ROI не менее 300%

### 4. Временные рамки
- Подготовка: 2 недели
- Запуск: 1 месяц
- Оценка результатов: каждые 2 недели
            """
        }
        
        return templates.get(document_type, f"Шаблон документа '{document_type}' в разработке.")
    
    def answer_business_question(self, question: str, context: Dict = None) -> str:
        """Ответы на бизнес-вопросы"""
        if not self.openai_available:
            return self._generate_demo_answer(question)
        
        try:
            context_info = ""
            if context:
                context_info = f"Контекст: {json.dumps(context, ensure_ascii=False)}"
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты опытный бизнес-консультант. Давай практичные советы по развитию бизнеса на русском языке."},
                    {"role": "user", "content": f"{question}\n{context_info}"}
                ],
                max_tokens=800,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Ошибка получения ответа: {str(e)}"
    
    def _generate_demo_answer(self, question: str) -> str:
        """Демо-ответы без OpenAI"""
        keywords_answers = {
            'продажи': "Для увеличения продаж рекомендую: 1) Анализ воронки продаж 2) Улучшение качества лидов 3) Обучение отдела продаж 4) Автоматизация CRM",
            'маркетинг': "Эффективная маркетинговая стратегия включает: 1) Четкое позиционирование 2) Многоканальное продвижение 3) Аналитику и оптимизацию 4) Работу с отзывами",
            'финансы': "Для улучшения финансового состояния: 1) Ведите управленческий учет 2) Контролируйте денежный поток 3) Оптимизируйте расходы 4) Диверсифицируйте доходы",
            'персонал': "Управление персоналом: 1) Четкие KPI и мотивация 2) Регулярное обучение 3) Корпоративная культура 4) Система обратной связи"
        }
        
        question_lower = question.lower()
        for keyword, answer in keywords_answers.items():
            if keyword in question_lower:
                return f"**Ответ на ваш вопрос:**\n\n{answer}\n\n*Для получения более детальной консультации обратитесь к специалисту.*"
        
        return "Спасибо за интересный вопрос! Для получения качественного ответа рекомендую обратиться к бизнес-консультанту или изучить специализированную литературу по данной теме."

class AutomationService:
    """Сервис автоматизации бизнес-процессов"""
    
    def __init__(self, db_path='business_manager.db'):
        self.db_path = db_path
        self.scheduler = schedule
        self.running = False
    
    def get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_automation_task(self, user_id: int, company_id: int, task_type: str, config: Dict, schedule_pattern: str = None):
        """Создание автоматизированной задачи"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        next_run = None
        if schedule_pattern:
            # Простая логика для определения следующего запуска
            if schedule_pattern == 'daily':
                next_run = (datetime.now() + timedelta(days=1)).isoformat()
            elif schedule_pattern == 'weekly':
                next_run = (datetime.now() + timedelta(weeks=1)).isoformat()
            elif schedule_pattern == 'monthly':
                next_run = (datetime.now() + timedelta(days=30)).isoformat()
        
        cursor.execute("""
            INSERT INTO automation_tasks (user_id, company_id, task_type, task_config, schedule_pattern, next_run)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, company_id, task_type, json.dumps(config), schedule_pattern, next_run))
        
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()
        
        return task_id
    
    def execute_automation_task(self, task_id: int):
        """Выполнение автоматизированной задачи"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM automation_tasks WHERE id = ? AND is_active = 1", (task_id,))
        task = cursor.fetchone()
        
        if not task:
            conn.close()
            return False
        
        config = json.loads(task['task_config'])
        
        try:
            if task['task_type'] == 'auto_report':
                self._generate_auto_report(task['user_id'], task['company_id'], config)
            elif task['task_type'] == 'stock_reminder':
                self._send_stock_reminder(task['user_id'], task['company_id'], config)
            elif task['task_type'] == 'customer_followup':
                self._send_customer_followup(task['user_id'], task['company_id'], config)
            elif task['task_type'] == 'backup':
                self._create_backup(task['user_id'], config)
            
            # Обновляем время последнего выполнения
            cursor.execute("""
                UPDATE automation_tasks 
                SET last_run = CURRENT_TIMESTAMP, next_run = ?
                WHERE id = ?
            """, (self._calculate_next_run(task['schedule_pattern']), task_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Ошибка выполнения задачи {task_id}: {str(e)}")
            conn.close()
            return False
    
    def _generate_auto_report(self, user_id: int, company_id: int, config: Dict):
        """Генерация автоматического отчета"""
        # Здесь будет логика генерации отчета
        print(f"Генерируем автоматический отчет для пользователя {user_id}")
    
    def _send_stock_reminder(self, user_id: int, company_id: int, config: Dict):
        """Отправка напоминания о критических остатках"""
        print(f"Отправляем напоминание о складских остатках для пользователя {user_id}")
    
    def _send_customer_followup(self, user_id: int, company_id: int, config: Dict):
        """Отправка follow-up сообщений клиентам"""
        print(f"Отправляем follow-up сообщения клиентам для пользователя {user_id}")
    
    def _create_backup(self, user_id: int, config: Dict):
        """Создание резервной копии"""
        print(f"Создаем резервную копию для пользователя {user_id}")
    
    def _calculate_next_run(self, schedule_pattern: str) -> str:
        """Расчет времени следующего выполнения"""
        if schedule_pattern == 'daily':
            return (datetime.now() + timedelta(days=1)).isoformat()
        elif schedule_pattern == 'weekly':
            return (datetime.now() + timedelta(weeks=1)).isoformat()
        elif schedule_pattern == 'monthly':
            return (datetime.now() + timedelta(days=30)).isoformat()
        return None
    
    def start_scheduler(self):
        """Запуск планировщика задач"""
        self.running = True
        
        def run_scheduler():
            while self.running:
                self.scheduler.run_pending()
                time.sleep(60)  # Проверяем каждую минуту
        
        scheduler_thread = Thread(target=run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
    
    def stop_scheduler(self):
        """Остановка планировщика"""
        self.running = False

# Глобальные экземпляры сервисов
ai_analytics = AIAnalyticsService()
ai_assistant = AIAssistantService()
automation_service = AutomationService()

