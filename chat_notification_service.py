"""
Chat and Notification Service - Модуль корпоративного чата и уведомлений
Включает в себя внутренний чат, каналы, уведомления и рассылки
"""

import sqlite3
import json
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import requests
import hashlib
import uuid
from threading import Thread
import time

class ChatService:
    """Сервис корпоративного чата"""
    
    def __init__(self, db_path='business_manager.db'):
        self.db_path = db_path
    
    def get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_channel(self, company_id: int, name: str, description: str = None, 
                      is_private: bool = False, created_by: int = None) -> int:
        """Создание нового канала"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO chat_channels (company_id, name, description, is_private, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (company_id, name, description, is_private, created_by))
        
        conn.commit()
        channel_id = cursor.lastrowid
        
        # Добавляем создателя как администратора канала
        if created_by:
            cursor.execute("""
                INSERT INTO channel_members (channel_id, user_id, role)
                VALUES (?, ?, 'admin')
            """, (channel_id, created_by))
            conn.commit()
        
        conn.close()
        return channel_id
    
    def add_user_to_channel(self, channel_id: int, user_id: int, role: str = 'member') -> bool:
        """Добавление пользователя в канал"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO channel_members (channel_id, user_id, role)
                VALUES (?, ?, ?)
            """, (channel_id, user_id, role))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    def remove_user_from_channel(self, channel_id: int, user_id: int) -> bool:
        """Удаление пользователя из канала"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM channel_members WHERE channel_id = ? AND user_id = ?",
                      (channel_id, user_id))
        conn.commit()
        conn.close()
        return True
    
    def send_message(self, sender_id: int, message: str, channel_id: int = None, 
                    receiver_id: int = None, company_id: int = None, 
                    message_type: str = 'text', file_url: str = None) -> int:
        """Отправка сообщения"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO chat_messages (sender_id, channel_id, receiver_id, company_id, 
                                     message, message_type, file_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sender_id, channel_id, receiver_id, company_id, message, message_type, file_url))
        
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()
        
        # Отправляем уведомления получателям
        if channel_id:
            self._notify_channel_members(channel_id, sender_id, message)
        elif receiver_id:
            self._notify_direct_message(receiver_id, sender_id, message)
        
        return message_id
    
    def get_channel_messages(self, channel_id: int, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Получение сообщений канала"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cm.*, u.full_name, u.email, u.avatar_url
            FROM chat_messages cm
            JOIN users u ON cm.sender_id = u.id
            WHERE cm.channel_id = ?
            ORDER BY cm.timestamp DESC
            LIMIT ? OFFSET ?
        """, (channel_id, limit, offset))
        
        messages = cursor.fetchall()
        conn.close()
        
        return [dict(msg) for msg in messages]
    
    def get_direct_messages(self, user1_id: int, user2_id: int, limit: int = 50) -> List[Dict]:
        """Получение личных сообщений между двумя пользователями"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cm.*, u.full_name, u.email, u.avatar_url
            FROM chat_messages cm
            JOIN users u ON cm.sender_id = u.id
            WHERE (cm.sender_id = ? AND cm.receiver_id = ?) 
               OR (cm.sender_id = ? AND cm.receiver_id = ?)
            ORDER BY cm.timestamp DESC
            LIMIT ?
        """, (user1_id, user2_id, user2_id, user1_id, limit))
        
        messages = cursor.fetchall()
        conn.close()
        
        return [dict(msg) for msg in messages]
    
    def get_user_channels(self, user_id: int, company_id: int) -> List[Dict]:
        """Получение каналов пользователя"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cc.*, cm_user.role as user_role,
                   COUNT(cm.id) as message_count,
                   MAX(cm.timestamp) as last_message_time
            FROM chat_channels cc
            JOIN channel_members cm_user ON cc.id = cm_user.channel_id
            LEFT JOIN chat_messages cm ON cc.id = cm.channel_id
            WHERE cm_user.user_id = ? AND cc.company_id = ?
            GROUP BY cc.id
            ORDER BY last_message_time DESC
        """, (user_id, company_id))
        
        channels = cursor.fetchall()
        conn.close()
        
        return [dict(channel) for channel in channels]
    
    def edit_message(self, message_id: int, new_content: str, editor_id: int) -> bool:
        """Редактирование сообщения"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем, может ли пользователь редактировать сообщение
        cursor.execute("SELECT sender_id FROM chat_messages WHERE id = ?", (message_id,))
        message = cursor.fetchone()
        
        if not message or message['sender_id'] != editor_id:
            conn.close()
            return False
        
        cursor.execute("""
            UPDATE chat_messages 
            SET message = ?, is_edited = 1, edited_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_content, message_id))
        
        conn.commit()
        conn.close()
        return True
    
    def delete_message(self, message_id: int, deleter_id: int) -> bool:
        """Удаление сообщения"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем права на удаление
        cursor.execute("""
            SELECT cm.sender_id, cc.created_by, cm_member.role
            FROM chat_messages cm
            LEFT JOIN chat_channels cc ON cm.channel_id = cc.id
            LEFT JOIN channel_members cm_member ON cc.id = cm_member.channel_id AND cm_member.user_id = ?
            WHERE cm.id = ?
        """, (deleter_id, message_id))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False
        
        # Может удалять: автор сообщения, создатель канала или админ канала
        can_delete = (result['sender_id'] == deleter_id or 
                     result['created_by'] == deleter_id or 
                     result['role'] == 'admin')
        
        if not can_delete:
            conn.close()
            return False
        
        cursor.execute("DELETE FROM chat_messages WHERE id = ?", (message_id,))
        conn.commit()
        conn.close()
        return True
    
    def _notify_channel_members(self, channel_id: int, sender_id: int, message: str):
        """Уведомление участников канала о новом сообщении"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Получаем участников канала (кроме отправителя)
        cursor.execute("""
            SELECT cm.user_id, u.email, u.full_name
            FROM channel_members cm
            JOIN users u ON cm.user_id = u.id
            WHERE cm.channel_id = ? AND cm.user_id != ?
        """, (channel_id, sender_id))
        
        members = cursor.fetchall()
        
        # Получаем информацию о канале и отправителе
        cursor.execute("""
            SELECT cc.name as channel_name, u.full_name as sender_name
            FROM chat_channels cc, users u
            WHERE cc.id = ? AND u.id = ?
        """, (channel_id, sender_id))
        
        info = cursor.fetchone()
        conn.close()
        
        if info:
            notification_service.send_chat_notification(
                members, info['sender_name'], info['channel_name'], message
            )
    
    def _notify_direct_message(self, receiver_id: int, sender_id: int, message: str):
        """Уведомление о личном сообщении"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT u1.email as receiver_email, u1.full_name as receiver_name,
                   u2.full_name as sender_name
            FROM users u1, users u2
            WHERE u1.id = ? AND u2.id = ?
        """, (receiver_id, sender_id))
        
        info = cursor.fetchone()
        conn.close()
        
        if info:
            notification_service.send_direct_message_notification(
                info['receiver_email'], info['sender_name'], message
            )

class NotificationService:
    """Сервис уведомлений"""
    
    def __init__(self, db_path='business_manager.db'):
        self.db_path = db_path
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        # В реальном приложении эти данные должны быть в переменных окружения
        self.email_user = "noreply@businessmanager.com"
        self.email_password = "app_password"
    
    def get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_notification_template(self, company_id: int, template_type: str, 
                                   subject_template: str, body_template: str) -> int:
        """Создание шаблона уведомления"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO notification_templates (company_id, template_type, subject_template, body_template)
            VALUES (?, ?, ?, ?)
        """, (company_id, template_type, subject_template, body_template))
        
        conn.commit()
        template_id = cursor.lastrowid
        conn.close()
        return template_id
    
    def update_notification_settings(self, user_id: int, notification_type: str, 
                                   delivery_method: str, is_enabled: bool):
        """Обновление настроек уведомлений пользователя"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO notification_settings 
            (user_id, notification_type, delivery_method, is_enabled)
            VALUES (?, ?, ?, ?)
        """, (user_id, notification_type, delivery_method, is_enabled))
        
        conn.commit()
        conn.close()
    
    def get_user_notification_settings(self, user_id: int) -> Dict[str, Dict]:
        """Получение настроек уведомлений пользователя"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT notification_type, delivery_method, is_enabled
            FROM notification_settings
            WHERE user_id = ?
        """, (user_id,))
        
        settings = cursor.fetchall()
        conn.close()
        
        # Группируем по типу уведомления
        result = {}
        for setting in settings:
            ntype = setting['notification_type']
            if ntype not in result:
                result[ntype] = {}
            result[ntype][setting['delivery_method']] = setting['is_enabled']
        
        return result
    
    def send_email_notification(self, to_email: str, subject: str, body: str, 
                              is_html: bool = False) -> bool:
        """Отправка email уведомления"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_user
            msg['To'] = to_email
            msg['Subject'] = subject
            
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # В демо-режиме просто логируем
            print(f"EMAIL NOTIFICATION: To: {to_email}, Subject: {subject}")
            print(f"Body: {body[:100]}...")
            
            # Реальная отправка (закомментирована для демо)
            # context = ssl.create_default_context()
            # with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            #     server.starttls(context=context)
            #     server.login(self.email_user, self.email_password)
            #     server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"Ошибка отправки email: {str(e)}")
            return False
    
    def send_sms_notification(self, phone: str, message: str) -> bool:
        """Отправка SMS уведомления"""
        try:
            # В демо-режиме просто логируем
            print(f"SMS NOTIFICATION: To: {phone}, Message: {message}")
            
            # Здесь должна быть интеграция с SMS-провайдером
            # Например, через API Twilio, SMS.ru и т.д.
            
            return True
        except Exception as e:
            print(f"Ошибка отправки SMS: {str(e)}")
            return False
    
    def send_push_notification(self, user_id: int, title: str, body: str, 
                             data: Dict = None) -> bool:
        """Отправка push уведомления"""
        try:
            # В демо-режиме просто логируем
            print(f"PUSH NOTIFICATION: User: {user_id}, Title: {title}, Body: {body}")
            
            # Здесь должна быть интеграция с Firebase Cloud Messaging или аналогом
            
            return True
        except Exception as e:
            print(f"Ошибка отправки push: {str(e)}")
            return False
    
    def send_chat_notification(self, members: List, sender_name: str, 
                             channel_name: str, message: str):
        """Отправка уведомлений о сообщении в чате"""
        subject = f"Новое сообщение в канале {channel_name}"
        body = f"""
Пользователь {sender_name} написал в канале {channel_name}:

{message[:200]}{'...' if len(message) > 200 else ''}

Перейдите в приложение, чтобы прочитать полное сообщение.
        """
        
        for member in members:
            # Проверяем настройки уведомлений пользователя
            settings = self.get_user_notification_settings(member['user_id'])
            chat_settings = settings.get('chat', {})
            
            if chat_settings.get('email', True):  # По умолчанию включено
                self.send_email_notification(member['email'], subject, body)
            
            if chat_settings.get('push', True):
                self.send_push_notification(member['user_id'], subject, message[:100])
    
    def send_direct_message_notification(self, receiver_email: str, sender_name: str, message: str):
        """Отправка уведомления о личном сообщении"""
        subject = f"Личное сообщение от {sender_name}"
        body = f"""
Пользователь {sender_name} отправил вам личное сообщение:

{message[:200]}{'...' if len(message) > 200 else ''}

Перейдите в приложение, чтобы ответить.
        """
        
        self.send_email_notification(receiver_email, subject, body)
    
    def send_bulk_notification(self, user_ids: List[int], subject: str, body: str, 
                             notification_type: str = 'marketing'):
        """Массовая рассылка уведомлений"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Получаем email адреса пользователей
        placeholders = ','.join('?' * len(user_ids))
        cursor.execute(f"""
            SELECT id, email, full_name FROM users 
            WHERE id IN ({placeholders})
        """, user_ids)
        
        users = cursor.fetchall()
        conn.close()
        
        successful_sends = 0
        
        for user in users:
            # Проверяем настройки пользователя
            settings = self.get_user_notification_settings(user['id'])
            marketing_settings = settings.get(notification_type, {})
            
            if marketing_settings.get('email', False):  # Маркетинговые по умолчанию выключены
                personalized_body = body.replace('{name}', user['full_name'] or 'Пользователь')
                if self.send_email_notification(user['email'], subject, personalized_body):
                    successful_sends += 1
        
        return successful_sends
    
    def schedule_notification(self, user_id: int, notification_type: str, 
                            scheduled_time: datetime, subject: str, body: str):
        """Планирование отложенного уведомления"""
        # В реальном приложении здесь должна быть интеграция с планировщиком задач
        print(f"Запланировано уведомление для пользователя {user_id} на {scheduled_time}")
        print(f"Тип: {notification_type}, Тема: {subject}")

class CustomerCommunicationService:
    """Сервис коммуникации с клиентами"""
    
    def __init__(self, db_path='business_manager.db'):
        self.db_path = db_path
        self.notification_service = NotificationService(db_path)
    
    def get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_customer_segment(self, company_id: int, name: str, description: str, 
                              criteria: Dict) -> int:
        """Создание сегмента клиентов"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO customer_segments (company_id, name, description, criteria)
            VALUES (?, ?, ?, ?)
        """, (company_id, name, description, json.dumps(criteria)))
        
        conn.commit()
        segment_id = cursor.lastrowid
        conn.close()
        return segment_id
    
    def get_customers_by_segment(self, segment_id: int) -> List[Dict]:
        """Получение клиентов по сегменту"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.* FROM customers c
            JOIN customer_segment_membership csm ON c.id = csm.customer_id
            WHERE csm.segment_id = ?
        """, (segment_id,))
        
        customers = cursor.fetchall()
        conn.close()
        return [dict(customer) for customer in customers]
    
    def send_customer_campaign(self, company_id: int, segment_id: int, 
                             subject: str, body: str, campaign_type: str = 'email') -> Dict:
        """Отправка рекламной кампании клиентам"""
        customers = self.get_customers_by_segment(segment_id)
        
        results = {
            'total_customers': len(customers),
            'successful_sends': 0,
            'failed_sends': 0,
            'errors': []
        }
        
        for customer in customers:
            try:
                if campaign_type == 'email' and customer.get('email'):
                    personalized_body = body.replace('{name}', customer.get('name', 'Клиент'))
                    if self.notification_service.send_email_notification(
                        customer['email'], subject, personalized_body, is_html=True
                    ):
                        results['successful_sends'] += 1
                    else:
                        results['failed_sends'] += 1
                elif campaign_type == 'sms' and customer.get('phone'):
                    personalized_message = body.replace('{name}', customer.get('name', 'Клиент'))
                    if self.notification_service.send_sms_notification(
                        customer['phone'], personalized_message
                    ):
                        results['successful_sends'] += 1
                    else:
                        results['failed_sends'] += 1
                else:
                    results['failed_sends'] += 1
                    results['errors'].append(f"Нет контактных данных для клиента {customer.get('name', 'ID:' + str(customer['id']))}")
            
            except Exception as e:
                results['failed_sends'] += 1
                results['errors'].append(str(e))
        
        return results
    
    def create_automated_followup(self, company_id: int, trigger_event: str, 
                                delay_hours: int, message_template: str):
        """Создание автоматического follow-up"""
        # Интеграция с системой автоматизации
        config = {
            'trigger_event': trigger_event,
            'delay_hours': delay_hours,
            'message_template': message_template
        }
        
        from ai_services import automation_service
        return automation_service.create_automation_task(
            0, company_id, 'customer_followup', config, 'trigger'
        )

# Глобальные экземпляры сервисов
chat_service = ChatService()
notification_service = NotificationService()
customer_communication = CustomerCommunicationService()

