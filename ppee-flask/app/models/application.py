from app import db
from datetime import datetime
import os

# Связь между заявками и чек-листами
application_checklists = db.Table('application_checklists',
                                  db.Column('application_id', db.Integer, db.ForeignKey('applications.id'),
                                            primary_key=True),
                                  db.Column('checklist_id', db.Integer, db.ForeignKey('checklists.id'),
                                            primary_key=True)
                                  )


class Application(db.Model):
    """Модель заявки на анализ документа"""
    __tablename__ = 'applications'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default='created')  # created, indexing, indexed, analyzing, analyzed, error
    status_message = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    task_id = db.Column(db.String(36), nullable=True)  # ID задачи Celery
    last_operation = db.Column(db.String(50))  # 'indexing' или 'analyzing'

    # Поля для отслеживания прогресса анализа
    analysis_total_params = db.Column(db.Integer, default=0)
    analysis_completed_params = db.Column(db.Integer, default=0)
    analysis_started_at = db.Column(db.DateTime)
    analysis_completed_at = db.Column(db.DateTime)
    
    # Новые поля для работы как Assistant (Помощник)
    assistant_type = db.Column(db.String(50), default='support')  # support, qa, analyzer, custom
    system_prompt = db.Column(db.Text)  # Системный промпт для помощника
    llm_model = db.Column(db.String(100), default='gemma3:27b')  # Модель LLM
    temperature = db.Column(db.Float, default=0.7)
    max_tokens = db.Column(db.Integer, default=2000)
    
    # Флаги возможностей помощника
    is_public = db.Column(db.Boolean, default=False)  # Публичный доступ
    enable_search = db.Column(db.Boolean, default=True)  # Использовать поиск по базе знаний
    enable_web_search = db.Column(db.Boolean, default=False)  # Поиск в интернете
    
    # Настройки поиска
    search_limit = db.Column(db.Integer, default=10)  # Количество чанков для поиска
    use_reranker = db.Column(db.Boolean, default=True)  # Использовать ререйтинг
    
    # Статистика использования помощника
    total_conversations = db.Column(db.Integer, default=0)
    total_messages = db.Column(db.Integer, default=0)
    average_rating = db.Column(db.Float, default=0.0)

    # Отношения
    user = db.relationship('User', backref=db.backref('applications', lazy='dynamic'))
    files = db.relationship('File', backref='application', lazy='dynamic', cascade='all, delete-orphan')
    parameter_results = db.relationship('ParameterResult', backref='application', lazy='dynamic',
                                        cascade='all, delete-orphan')
    checklists = db.relationship('Checklist', secondary=application_checklists,
                                 backref=db.backref('applications', lazy='dynamic'))

    def __repr__(self):
        return f'<Application {self.id}: {self.name}>'

    def get_analysis_progress(self):
        """Возвращает прогресс анализа в процентах"""
        if self.analysis_total_params == 0:
            return 0
        return int((self.analysis_completed_params / self.analysis_total_params) * 100)

    def get_status_display(self):
        """Возвращает отображаемое значение статуса"""
        status_map = {
            'created': 'Создана',
            'indexing': 'Индексация',
            'indexed': 'Проиндексирована',
            'analyzing': f'Анализ ({self.analysis_completed_params}/{self.analysis_total_params})',
            'analyzed': 'Проанализирована',
            'error': 'Ошибка'
        }

        # Для статуса analyzing показываем прогресс
        if self.status == 'analyzing' and self.analysis_total_params > 0:
            return f'Анализ ({self.analysis_completed_params}/{self.analysis_total_params})'

        return status_map.get(self.status, self.status)

    def get_document_names_mapping(self):
        """Возвращает маппинг document_id -> original_filename"""
        mapping = {}
        for file in self.files:
            # Генерируем document_id так же, как при индексации
            doc_id = f"doc_{os.path.basename(file.file_path).replace(' ', '_').replace('.', '_')}"
            mapping[doc_id] = file.original_filename or file.filename
        return mapping

    def format_duration(self, start_time, end_time):
        """Форматирует длительность операции в человекочитаемый вид"""
        if not start_time or not end_time:
            return None

        duration = end_time - start_time
        total_seconds = int(duration.total_seconds())

        return self.format_duration_from_seconds(total_seconds)

    def format_duration_from_seconds(self, total_seconds):
        """Форматирует секунды в человекочитаемый вид"""
        total_seconds = int(total_seconds)

        if total_seconds < 60:
            return f"{total_seconds} сек."
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            if seconds > 0:
                return f"{minutes} мин. {seconds} сек."
            return f"{minutes} мин."
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if minutes > 0:
                return f"{hours} ч. {minutes} мин."
            return f"{hours} ч."

    # Методы для работы как Assistant
    def get_system_prompt(self):
        """Возвращает системный промпт для помощника"""
        if self.system_prompt:
            return self.system_prompt
        
        # Промпт по умолчанию для разных типов помощников
        prompts = {
            'support': """Ты - эксперт службы поддержки. Помогай пользователям решать их проблемы на основе базы знаний.
Будь вежливым, профессиональным и конкретным в своих ответах.
Если информации недостаточно, попроси уточнить детали.""",
            
            'qa': """Ты - помощник для ответов на вопросы. Отвечай точно и по существу на основе предоставленной информации.
Если не знаешь ответ, честно скажи об этом.""",
            
            'analyzer': """Ты - аналитический помощник. Анализируй документы и извлекай нужную информацию.
Структурируй ответы и выделяй ключевые моменты.""",
            
            'custom': """Ты - универсальный помощник. Помогай пользователям с их запросами."""
        }
        
        return prompts.get(self.assistant_type, prompts['custom'])
    
    def can_user_access(self, user):
        """Проверяет, может ли пользователь использовать помощника"""
        if self.is_public:
            return True
        if not user or not user.is_authenticated:
            return False
        return self.user_id == user.id or user.is_admin()
    
    def increment_conversation_count(self):
        """Увеличивает счетчик диалогов"""
        self.total_conversations = (self.total_conversations or 0) + 1
        db.session.commit()
    
    def increment_message_count(self):
        """Увеличивает счетчик сообщений"""
        self.total_messages = (self.total_messages or 0) + 1
        db.session.commit()
    
    def update_rating(self, new_rating):
        """Обновляет средний рейтинг помощника"""
        if self.average_rating == 0:
            self.average_rating = new_rating
        else:
            # Простое скользящее среднее
            self.average_rating = (self.average_rating * 0.9) + (new_rating * 0.1)
        db.session.commit()
    
    def to_assistant_dict(self):
        """Преобразует в словарь для использования как Assistant"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'type': self.assistant_type,
            'is_public': self.is_public,
            'llm_model': self.llm_model,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'enable_search': self.enable_search,
            'search_limit': self.search_limit,
            'use_reranker': self.use_reranker,
            'total_conversations': self.total_conversations,
            'total_messages': self.total_messages,
            'average_rating': self.average_rating,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def get_status_message_with_duration(self):
        """Возвращает сообщение статуса с длительностью операции"""
        if not self.status_message:
            return None

        # Для успешной индексации - считаем общее время всех файлов
        if self.status == 'indexed':
            total_seconds = 0
            for file in self.files:
                if file.indexing_started_at and file.indexing_completed_at:
                    file_duration = (file.indexing_completed_at - file.indexing_started_at).total_seconds()
                    total_seconds += file_duration

            if total_seconds > 0:
                duration = self.format_duration_from_seconds(total_seconds)
                return f"{self.status_message} ({duration})"

        # Для успешного анализа
        elif self.status == 'analyzed' and self.analysis_started_at and self.analysis_completed_at:
            duration = self.format_duration(self.analysis_started_at, self.analysis_completed_at)
            if duration:
                return f"{self.status_message} ({duration})"

        # Для ошибок индексации
        elif self.status == 'error' and self.last_operation == 'indexing':
            total_seconds = 0
            for file in self.files:
                if file.indexing_started_at:
                    # Если есть время окончания - используем его, иначе текущее время
                    end_time = file.indexing_completed_at or datetime.utcnow()
                    file_duration = (end_time - file.indexing_started_at).total_seconds()
                    total_seconds += file_duration

            if total_seconds > 0:
                duration = self.format_duration_from_seconds(total_seconds)
                return f"{self.status_message} (выполнялось {duration})"

        # Для ошибок анализа
        elif self.status == 'error' and self.last_operation == 'analyzing' and self.analysis_started_at:
            end_time = self.analysis_completed_at or datetime.utcnow()
            duration = self.format_duration(self.analysis_started_at, end_time)
            if duration:
                return f"{self.status_message} (выполнялось {duration})"

        return self.status_message


class File(db.Model):
    """Модель файла, связанного с заявкой"""
    __tablename__ = 'files'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer)  # Размер в байтах
    file_type = db.Column(db.String(50))  # document, attachment
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Поля для отслеживания индексации
    indexing_status = db.Column(db.String(50), default='pending')  # pending, indexing, completed, error
    index_session_id = db.Column(db.String(36))  # UUID сессии индексации
    chunks_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    indexing_started_at = db.Column(db.DateTime)
    indexing_completed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<File {self.id}: {self.original_filename}>'

    def get_indexing_duration(self):
        """Возвращает длительность индексации файла"""
        if not self.indexing_started_at or not self.indexing_completed_at:
            return None

        duration = self.indexing_completed_at - self.indexing_started_at
        total_seconds = int(duration.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds} сек."
        else:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            if seconds > 0:
                return f"{minutes} мин. {seconds} сек."
            return f"{minutes} мин."