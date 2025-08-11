from app import db
from datetime import datetime
import json


class Conversation(db.Model):
    """Модель диалога пользователя с помощником"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Связь с помощником (используем application_id для совместимости)
    assistant_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    
    # Связь с пользователем
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Основная информация
    title = db.Column(db.String(255))
    status = db.Column(db.String(50), default='active')  # active, archived, deleted
    
    # Статистика
    message_count = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    last_message_at = db.Column(db.DateTime)
    
    # Контекст и настройки
    context_summary = db.Column(db.Text)  # Сводка предыдущих сообщений для длинных диалогов
    settings = db.Column(db.JSON, default=dict)  # Настройки диалога (temperature, max_tokens и т.д.)
    
    # Временные метки
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    assistant = db.relationship('Application', backref=db.backref('conversations', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('conversations', lazy='dynamic'))
    messages = db.relationship('Message', backref='conversation', lazy='dynamic', cascade='all, delete-orphan', order_by='Message.created_at')
    
    def __repr__(self):
        return f'<Conversation {self.id}: {self.title or "Untitled"}>'
    
    def get_last_messages(self, limit=10):
        """Получить последние сообщения"""
        return self.messages.order_by(Message.created_at.desc()).limit(limit).all()[::-1]
    
    def get_context_for_llm(self, limit=10):
        """Получить контекст для LLM из последних сообщений"""
        messages = self.get_last_messages(limit)
        context = []
        for msg in messages:
            if msg.role == 'user':
                context.append(f"User: {msg.content}")
            elif msg.role == 'assistant':
                context.append(f"Assistant: {msg.content}")
        return "\n".join(context)
    
    def update_statistics(self):
        """Обновить статистику диалога"""
        self.message_count = self.messages.count()
        last_message = self.messages.order_by(Message.created_at.desc()).first()
        if last_message:
            self.last_message_at = last_message.created_at
        db.session.commit()
    
    def to_dict(self):
        """Преобразовать в словарь для API"""
        return {
            'id': self.id,
            'assistant_id': self.assistant_id,
            'assistant_name': self.assistant.name if self.assistant else None,
            'user_id': self.user_id,
            'title': self.title,
            'status': self.status,
            'message_count': self.message_count,
            'total_tokens': self.total_tokens,
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class Message(db.Model):
    """Модель сообщения в диалоге"""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Связь с диалогом
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    
    # Основная информация
    role = db.Column(db.String(20), nullable=False)  # user, assistant, system
    content = db.Column(db.Text, nullable=False)
    
    # Метаданные
    tokens_count = db.Column(db.Integer, default=0)
    processing_time = db.Column(db.Float)  # время обработки в секундах
    
    # Дополнительные данные
    attachments = db.Column(db.JSON)  # список прикрепленных файлов
    extra_data = db.Column(db.JSON)  # дополнительные метаданные
    
    # Данные поиска (если сообщение использовало поиск)
    search_results = db.Column(db.JSON)  # результаты поиска из векторной БД
    search_query = db.Column(db.String(500))  # поисковый запрос
    
    # LLM запрос и ответ (для отладки и аналитики)
    llm_request = db.Column(db.JSON)  # полный запрос к LLM
    llm_response = db.Column(db.JSON)  # полный ответ от LLM
    
    # Оценка и фидбек
    rating = db.Column(db.Integer)  # оценка от пользователя (1-5)
    feedback = db.Column(db.Text)  # текстовый фидбек
    
    # Временные метки
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Message {self.id}: {self.role} in conversation {self.conversation_id}>'
    
    def to_dict(self):
        """Преобразовать в словарь для API"""
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role,
            'content': self.content,
            'tokens_count': self.tokens_count,
            'processing_time': self.processing_time,
            'attachments': self.attachments,
            'extra_data': self.extra_data,
            'rating': self.rating,
            'created_at': self.created_at.isoformat()
        }
    
    def get_formatted_content(self):
        """Получить форматированное содержимое для отображения"""
        if self.role == 'user':
            return f"👤 {self.content}"
        elif self.role == 'assistant':
            return f"🤖 {self.content}"
        else:
            return f"ℹ️ {self.content}"