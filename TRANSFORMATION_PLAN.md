# Детальная карта трансформации PPEE-Flask в систему "Помощников"

## Текущая архитектура (PPEE-Flask)

**Концепция:** Система анализа документов ППЭЭ с помощью LLM
- **Application** - заявка для обработки документов
- **Checklist** - чек-лист параметров для извлечения из документов
- **ChecklistParameter** - конкретный параметр для поиска в документах
- **User** - пользователи с ролями (admin, prompt_engineer, user)

## Новая архитектура (Система Помощников)

**Концепция:** Универсальная платформа для создания и использования LLM-помощников
- **Assistant** - конфигурируемый помощник (бывший Application)
- **PromptTemplate** - шаблон промпта для помощника (бывший Checklist)
- **PromptParameter** - параметр шаблона (бывший ChecklistParameter)
- **User** - пользователи с ролями (admin, template_creator, user)

---

## 1. МОДЕЛИ ДАННЫХ (app/models/)

### 1.1. Трансформация Application → Assistant

**Файл:** `app/models/application.py` → `app/models/assistant.py`

#### Изменения полей:
```python
# БЫЛО (Application)
name = db.Column(db.String(255), nullable=False)
description = db.Column(db.Text)
status = db.Column(db.String(50), default='created')  # created, indexing, indexed, analyzing, analyzed, error

# СТАНЕТ (Assistant)
name = db.Column(db.String(255), nullable=False)
description = db.Column(db.Text)
assistant_type = db.Column(db.String(50), default='chat')  # chat, document_analyzer, qa_bot
status = db.Column(db.String(50), default='active')  # active, inactive, training
```

#### Новые поля:
```python
# Конфигурация помощника
system_prompt = db.Column(db.Text)  # Системный промпт
llm_model = db.Column(db.String(100), default='gemma3:27b')
temperature = db.Column(db.Float, default=0.7)
max_tokens = db.Column(db.Integer, default=2000)
context_window = db.Column(db.Integer, default=8000)

# Возможности помощника
can_upload_files = db.Column(db.Boolean, default=False)
can_search_web = db.Column(db.Boolean, default=False)
can_generate_images = db.Column(db.Boolean, default=False)
can_analyze_code = db.Column(db.Boolean, default=False)

# Знания и векторная база
knowledge_base_id = db.Column(db.String(100))  # ID коллекции в Qdrant
has_knowledge_base = db.Column(db.Boolean, default=False)

# Статистика использования
total_conversations = db.Column(db.Integer, default=0)
total_messages = db.Column(db.Integer, default=0)
average_rating = db.Column(db.Float, default=0.0)
```

#### Удаляемые поля:
```python
# Убираем поля, специфичные для анализа документов
task_id, last_operation, analysis_total_params, analysis_completed_params,
analysis_started_at, analysis_completed_at
```

#### Новые отношения:
```python
# Заменяем связи с чек-листами на шаблоны промптов
prompt_templates = db.relationship('PromptTemplate', secondary=assistant_templates,
                                 backref=db.backref('assistants', lazy='dynamic'))
conversations = db.relationship('Conversation', backref='assistant', lazy='dynamic')
knowledge_chunks = db.relationship('KnowledgeChunk', backref='assistant', lazy='dynamic')
```

### 1.2. Трансформация Checklist → PromptTemplate

**Файл:** `app/models/checklist.py` → `app/models/prompt_template.py`

#### Изменения полей:
```python
# БЫЛО (Checklist)
name = db.Column(db.String(255), nullable=False, unique=True)
description = db.Column(db.Text)

# СТАНЕТ (PromptTemplate)
name = db.Column(db.String(255), nullable=False)  # убираем unique
description = db.Column(db.Text)
template_type = db.Column(db.String(50), default='general')  # general, system, user, function
```

#### Новые поля:
```python
# Шаблон промпта
prompt_text = db.Column(db.Text, nullable=False)
variables = db.Column(db.JSON)  # {'var1': 'description', 'var2': 'description'}

# Категоризация
category = db.Column(db.String(100))  # business, technical, creative, etc.
tags = db.Column(db.JSON)  # ['tag1', 'tag2', 'tag3']

# Использование
usage_count = db.Column(db.Integer, default=0)
rating = db.Column(db.Float, default=0.0)
rating_count = db.Column(db.Integer, default=0)

# Версионирование
version = db.Column(db.String(20), default='1.0')
parent_template_id = db.Column(db.Integer, db.ForeignKey('prompt_templates.id'))
```

#### Переименование отношений:
```python
# БЫЛО
parameters = db.relationship('ChecklistParameter', ...)

# СТАНЕТ
parameters = db.relationship('PromptParameter', ...)
parent = db.relationship('PromptTemplate', remote_side=[id])
children = db.relationship('PromptTemplate', backref='parent_template')
```

### 1.3. Трансформация ChecklistParameter → PromptParameter

**Файл:** `app/models/checklist.py` (ChecklistParameter) → `app/models/prompt_template.py` (PromptParameter)

#### Изменения полей:
```python
# БЫЛО (ChecklistParameter)
search_query = db.Column(db.String(255), nullable=False)
llm_query = db.Column(db.String(255), nullable=True)
search_limit = db.Column(db.Integer, default=3)

# СТАНЕТ (PromptParameter)
variable_name = db.Column(db.String(100), nullable=False)  # {variable_name} в шаблоне
variable_type = db.Column(db.String(50), default='text')  # text, number, boolean, file, list
default_value = db.Column(db.Text)
validation_rules = db.Column(db.JSON)  # {'min_length': 10, 'max_length': 500}
```

#### Удаляемые поля (специфичные для поиска в документах):
```python
# Убираем все поля, связанные с семантическим поиском
use_reranker, rerank_limit, use_full_scan, llm_model, 
llm_prompt_template, llm_temperature, llm_max_tokens
```

### 1.4. Новые модели

#### 1.4.1. Conversation (новая модель)
```python
class Conversation(db.Model):
    """Диалог пользователя с помощником"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    assistant_id = db.Column(db.Integer, db.ForeignKey('assistants.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255))
    
    # Статистика
    message_count = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    
    # Контекст диалога
    context_summary = db.Column(db.Text)  # Сводка предыдущих сообщений
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    messages = db.relationship('Message', backref='conversation', lazy='dynamic')
```

#### 1.4.2. Message (новая модель)
```python
class Message(db.Model):
    """Сообщение в диалоге"""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user, assistant, system
    content = db.Column(db.Text, nullable=False)
    
    # Метаданные
    tokens_count = db.Column(db.Integer, default=0)
    processing_time = db.Column(db.Float)  # время обработки в секундах
    
    # Файлы и вложения
    attachments = db.Column(db.JSON)  # список файлов
    
    # LLM запрос (для отладки)
    llm_request = db.Column(db.JSON)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

#### 1.4.3. KnowledgeChunk (трансформация из File)
```python
class KnowledgeChunk(db.Model):
    """Чанк знаний помощника"""
    __tablename__ = 'knowledge_chunks'
    
    id = db.Column(db.Integer, primary_key=True)
    assistant_id = db.Column(db.Integer, db.ForeignKey('assistants.id'), nullable=False)
    
    # Содержание чанка
    content = db.Column(db.Text, nullable=False)
    metadata = db.Column(db.JSON)  # источник, теги, дата создания и т.д.
    
    # Векторная индексация
    vector_id = db.Column(db.String(100))  # ID в Qdrant
    embedding_model = db.Column(db.String(100))
    
    # Статистика использования
    retrieval_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### 1.5. Изменения модели User

**Файл:** `app/models/user.py`

#### Изменения в ролях:
```python
# БЫЛО
role = db.Column(db.String(20), default='user')  # admin, prompt_engineer, user

# СТАНЕТ
role = db.Column(db.String(20), default='user')  # admin, template_creator, user
```

#### Обновление методов:
```python
# Переименовываем методы
def is_prompt_engineer(self) -> def is_template_creator(self)
def can_edit_checklist(self, checklist) -> def can_edit_template(self, template)
def can_view_application(self, application) -> def can_view_assistant(self, assistant)
def get_accessible_applications(self) -> def get_accessible_assistants(self)
def get_applications_count(self) -> def get_assistants_count(self)
def get_checklists_count(self) -> def get_templates_count(self)
```

#### Новые методы:
```python
def can_create_assistant(self):
    """Проверяет, может ли пользователь создавать помощников"""
    return self.is_admin() or self.is_template_creator()

def can_use_assistant(self, assistant):
    """Проверяет, может ли пользователь использовать помощника"""
    if assistant.is_public:
        return True
    return assistant.user_id == self.id or self.is_admin()

def get_conversation_count(self):
    """Возвращает количество диалогов пользователя"""
    from app.models import Conversation
    return Conversation.query.filter_by(user_id=self.id).count()
```

---

## 2. BLUEPRINTS (app/blueprints/)

### 2.1. Переименования и трансформации

| Текущий Blueprint | Новый Blueprint | Статус |
|------------------|----------------|---------|
| `applications/` | `assistants/` | **ПЕРЕИМЕНОВАТЬ** |
| `checklists/` | `templates/` | **ПЕРЕИМЕНОВАТЬ** |
| `search/` | `chat/` | **ПЕРЕИМЕНОВАТЬ + КАРДИНАЛЬНО ПЕРЕДЕЛАТЬ** |
| `llm_management/` | `models/` | **ПЕРЕИМЕНОВАТЬ** |
| `auth/` | `auth/` | **ОСТАВИТЬ БЕЗ ИЗМЕНЕНИЙ** |
| `users/` | `users/` | **МИНИМАЛЬНЫЕ ИЗМЕНЕНИЯ** |
| `main/` | `main/` | **ПЕРЕДЕЛАТЬ ДАШБОРД** |
| `stats/` | `analytics/` | **ПЕРЕИМЕНОВАТЬ + ПЕРЕДЕЛАТЬ** |

### 2.2. Новые Blueprints

#### 2.2.1. `conversations/` (новый)
```
app/blueprints/conversations/
├── __init__.py
├── routes.py       # управление диалогами
└── forms.py        # формы для диалогов (опционально)
```

#### 2.2.2. `knowledge/` (новый)
```
app/blueprints/knowledge/
├── __init__.py
├── routes.py       # управление базой знаний
└── forms.py
```

### 2.3. Детальные изменения по Blueprint'ам

#### 2.3.1. applications/ → assistants/

**Файл:** `app/blueprints/applications/routes.py` → `app/blueprints/assistants/routes.py`

**Маршруты для изменения:**
```python
# БЫЛО
@bp.route('/')  # Список заявок
@bp.route('/create')  # Создание заявки
@bp.route('/<int:id>')  # Просмотр заявки
@bp.route('/<int:id>/upload')  # Загрузка файлов
@bp.route('/<int:id>/analyze')  # Запуск анализа

# СТАНЕТ
@bp.route('/')  # Список помощников
@bp.route('/create')  # Создание помощника
@bp.route('/<int:id>')  # Настройки помощника
@bp.route('/<int:id>/knowledge')  # Управление знаниями
@bp.route('/<int:id>/test')  # Тестирование помощника
@bp.route('/<int:id>/publish')  # Публикация помощника
@bp.route('/<int:id>/clone')  # Клонирование помощника
```

#### 2.3.2. checklists/ → templates/

**Файл:** `app/blueprints/checklists/routes.py` → `app/blueprints/templates/routes.py`

**Маршруты для изменения:**
```python
# БЫЛО
@bp.route('/')  # Список чек-листов
@bp.route('/create')  # Создание чек-листа
@bp.route('/<int:id>')  # Просмотр чек-листа
@bp.route('/<int:id>/parameter/create')  # Создание параметра

# СТАНЕТ
@bp.route('/')  # Библиотека шаблонов
@bp.route('/create')  # Создание шаблона
@bp.route('/<int:id>')  # Редактор шаблона
@bp.route('/<int:id>/preview')  # Предварительный просмотр
@bp.route('/<int:id>/variables')  # Управление переменными
@bp.route('/marketplace')  # Маркетплейс шаблонов
```

#### 2.3.3. search/ → chat/

**Файл:** `app/blueprints/search/routes.py` → `app/blueprints/chat/routes.py`

**Полная переделка функционала:**
```python
@bp.route('/')  # Главная страница чата
@bp.route('/assistant/<int:id>')  # Чат с конкретным помощником
@bp.route('/conversation/<int:id>')  # Продолжение диалога
@bp.route('/api/send_message', methods=['POST'])  # API для отправки сообщений
@bp.route('/api/upload_file', methods=['POST'])  # Загрузка файлов в чат
@bp.route('/api/stream/<task_id>')  # Стриминг ответов
```

---

## 3. ЗАДАЧИ CELERY (app/tasks/)

### 3.1. Трансформация существующих задач

#### 3.1.1. indexing_tasks.py → knowledge_tasks.py

```python
# БЫЛО
@celery.task(bind=True, base=BaseTask)
def index_document_task(self, application_id, files_info):
    """Индексация документов для анализа"""

# СТАНЕТ
@celery.task(bind=True, base=BaseTask)
def index_knowledge_task(self, assistant_id, knowledge_data):
    """Индексация знаний для помощника"""
```

#### 3.1.2. llm_tasks.py → chat_tasks.py

```python
# БЫЛО
@celery.task(bind=True, base=BaseTask)
def analyze_application_task(self, application_id, checklist_ids):
    """Анализ документов по чек-листам"""

# СТАНЕТ
@celery.task(bind=True, base=BaseTask)
def process_message_task(self, conversation_id, message_id):
    """Обработка сообщения помощником"""

@celery.task(bind=True, base=BaseTask)
def generate_response_task(self, conversation_id, prompt_template_id=None):
    """Генерация ответа с использованием шаблона"""
```

#### 3.1.3. search_tasks.py → retrieval_tasks.py

```python
# БЫЛО
@celery.task(bind=True, base=BaseTask)
def semantic_search_task(self, application_ids, query, model_name):
    """Семантический поиск по документам"""

# СТАНЕТ
@celery.task(bind=True, base=BaseTask)
def knowledge_retrieval_task(self, assistant_id, query, limit=5):
    """Поиск релевантных знаний для помощника"""
```

### 3.2. Новые задачи

#### 3.2.1. template_tasks.py (новый файл)
```python
@celery.task(bind=True, base=BaseTask)
def render_template_task(self, template_id, variables):
    """Рендеринг шаблона промпта с переменными"""

@celery.task(bind=True, base=BaseTask)
def validate_template_task(self, template_id):
    """Валидация шаблона промпта"""
```

#### 3.2.2. training_tasks.py (новый файл)
```python
@celery.task(bind=True, base=BaseTask)  
def fine_tune_assistant_task(self, assistant_id, training_data):
    """Дообучение помощника на специфичных данных"""

@celery.task(bind=True, base=BaseTask)
def evaluate_assistant_task(self, assistant_id, test_cases):
    """Оценка качества работы помощника"""
```

---

## 4. ШАБЛОНЫ (app/templates/)

### 4.1. Переименования директорий

| Текущая директория | Новая директория | Статус |
|-------------------|-----------------|---------|
| `applications/` | `assistants/` | **ПЕРЕИМЕНОВАТЬ + ПЕРЕДЕЛАТЬ** |
| `checklists/` | `templates/` | **ПЕРЕИМЕНОВАТЬ + ПЕРЕДЕЛАТЬ** |
| `search/` | `chat/` | **ПЕРЕИМЕНОВАТЬ + ПОЛНАЯ ПЕРЕДЕЛКА** |
| `llm_management/` | `models/` | **ПЕРЕИМЕНОВАТЬ** |

### 4.2. Новые шаблоны

#### 4.2.1. chat/ (новая директория)
```
app/templates/chat/
├── index.html              # Главная страница чата
├── conversation.html       # Интерфейс диалога
├── assistant_selector.html # Выбор помощника
├── message_bubble.html     # Компонент сообщения
└── file_upload.html        # Загрузка файлов
```

#### 4.2.2. conversations/ (новая директория)
```
app/templates/conversations/
├── index.html              # Список диалогов
├── history.html           # История диалогов
└── export.html            # Экспорт диалогов
```

#### 4.2.3. knowledge/ (новая директория)
```
app/templates/knowledge/
├── upload.html            # Загрузка знаний
├── manage.html           # Управление базой знаний
└── chunks.html           # Просмотр чанков
```

---

## 5. БАЗА ДАННЫХ И МИГРАЦИИ

### 5.1. Миграции для переименования таблиц

```python
# Файл: migrations/versions/xxx_rename_tables.py

def upgrade():
    # Переименовываем таблицы
    op.rename_table('applications', 'assistants')
    op.rename_table('checklists', 'prompt_templates')  
    op.rename_table('checklist_parameters', 'prompt_parameters')
    op.rename_table('parameter_results', 'template_results')
    op.rename_table('files', 'knowledge_chunks')
    
    # Переименовываем связующую таблицу
    op.rename_table('application_checklists', 'assistant_templates')

def downgrade():
    # Обратные операции
    pass
```

### 5.2. Миграции для изменения структуры

```python
# Файл: migrations/versions/xxx_transform_structure.py

def upgrade():
    # Добавляем новые столбцы в assistants
    op.add_column('assistants', sa.Column('assistant_type', sa.String(50), default='chat'))
    op.add_column('assistants', sa.Column('system_prompt', sa.Text))
    op.add_column('assistants', sa.Column('llm_model', sa.String(100)))
    # ... другие новые поля
    
    # Удаляем старые столбцы
    op.drop_column('assistants', 'task_id')
    op.drop_column('assistants', 'last_operation')
    # ... другие удаляемые поля
    
    # Изменяем prompt_templates
    op.add_column('prompt_templates', sa.Column('prompt_text', sa.Text))
    op.add_column('prompt_templates', sa.Column('variables', sa.JSON))
    # ...
```

### 5.3. Создание новых таблиц

```python
# Файл: migrations/versions/xxx_create_new_tables.py

def upgrade():
    # Создаем таблицу conversations
    op.create_table('conversations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('assistant_id', sa.Integer(), sa.ForeignKey('assistants.id')),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        # ... другие поля
    )
    
    # Создаем таблицу messages
    op.create_table('messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id')),
        # ... другие поля
    )
```

---

## 6. ИНТЕГРАЦИЯ С ВНЕШНИМИ СЕРВИСАМИ

### 6.1. FastAPI сервис

#### Новые эндпоинты для добавления:
```python
# chat.py
@app.post("/chat/message")
async def send_message(message: MessageRequest)

@app.get("/chat/stream/{conversation_id}")  
async def stream_response(conversation_id: int)

# templates.py
@app.post("/templates/render")
async def render_template(template: TemplateRenderRequest)

@app.post("/templates/validate")
async def validate_template(template: TemplateValidateRequest)

# knowledge.py
@app.post("/knowledge/index")
async def index_knowledge(knowledge: KnowledgeIndexRequest)

@app.get("/knowledge/search")
async def search_knowledge(assistant_id: int, query: str)
```

### 6.2. Qdrant

#### Новые коллекции:
```python
# БЫЛО
QDRANT_COLLECTION = 'ppee_applications'

# СТАНЕТ  
ASSISTANT_COLLECTIONS = {
    'knowledge': 'assistant_knowledge',  # знания помощников
    'conversations': 'assistant_conversations',  # история диалогов для поиска
    'templates': 'prompt_templates'  # индексированные шаблоны
}
```

---

## 7. КОНФИГУРАЦИЯ

### 7.1. Изменения в config.py

```python
# ДОБАВИТЬ новые настройки
class Config:
    # ... существующие настройки
    
    # Настройки чата
    MAX_CONVERSATION_HISTORY = int(os.environ.get('MAX_CONVERSATION_HISTORY') or 50)
    ENABLE_MESSAGE_STREAMING = os.environ.get('ENABLE_MESSAGE_STREAMING', '1') == '1'
    
    # Настройки шаблонов
    MAX_TEMPLATE_VARIABLES = int(os.environ.get('MAX_TEMPLATE_VARIABLES') or 20)
    ENABLE_TEMPLATE_MARKETPLACE = os.environ.get('ENABLE_TEMPLATE_MARKETPLACE', '0') == '1'
    
    # Настройки помощников
    MAX_ASSISTANTS_PER_USER = int(os.environ.get('MAX_ASSISTANTS_PER_USER') or 10)
    ENABLE_ASSISTANT_TRAINING = os.environ.get('ENABLE_ASSISTANT_TRAINING', '0') == '1'
    
    # Обновляем шаблон промпта по умолчанию
    DEFAULT_SYSTEM_PROMPT = """Ты полезный ИИ-помощник. Отвечай на вопросы пользователя честно и точно.
    
Твои возможности:
- Отвечать на общие вопросы
- Помогать с написанием текстов  
- Анализировать предоставленную информацию
- Объяснять сложные концепции простым языком

Правила:
1. Будь вежливым и дружелюбным
2. Если не знаешь ответ, так и скажи
3. Не придумывай информацию
4. Структурируй ответы для лучшего понимания"""
```

---

## 8. СТАТИЧЕСКИЕ ФАЙЛЫ И FRONTEND

### 8.1. JavaScript файлы

#### Новые файлы:
```
app/static/js/
├── chat.js                 # Функционал чата
├── message-streaming.js    # Стриминг сообщений
├── template-editor.js      # Редактор шаблонов
├── assistant-config.js     # Конфигурация помощников
└── knowledge-upload.js     # Загрузка знаний
```

#### Обновить существующие:
```
app/static/js/
├── script.js              # Общий функционал (ОБНОВИТЬ)
├── task-progress.js       # Прогресс задач (АДАПТИРОВАТЬ)
└── ...
```

### 8.2. CSS файлы

#### Новые стили:
```
app/static/css/
├── chat.css               # Стили чата
├── templates.css          # Стили шаблонов  
├── assistants.css         # Стили помощников
└── ...
```

---

## 9. ПОШАГОВЫЙ ПЛАН ТРАНСФОРМАЦИИ

### Этап 1: Подготовка (1-2 дня)
1. ✅ Создание плана трансформации (текущий документ)
2. 🔄 Создание резервной копии базы данных
3. 🔄 Создание ветки для трансформации в Git
4. 🔄 Настройка тестовой среды

### Этап 2: Модели данных (2-3 дня)
1. 🔄 Создание новых моделей (Conversation, Message, KnowledgeChunk)
2. 🔄 Трансформация Application → Assistant
3. 🔄 Трансформация Checklist → PromptTemplate
4. 🔄 Трансформация ChecklistParameter → PromptParameter
5. 🔄 Обновление модели User
6. 🔄 Создание и применение миграций

### Этап 3: Backend логика (3-4 дня)
1. 🔄 Трансформация задач Celery
2. 🔄 Переделка applications → assistants blueprint
3. 🔄 Переделка checklists → templates blueprint
4. 🔄 Создание chat blueprint
5. 🔄 Создание conversations blueprint
6. 🔄 Создание knowledge blueprint
7. 🔄 Обновление интеграции с FastAPI

### Этап 4: Frontend интерфейсы (3-4 дня)
1. 🔄 Создание интерфейса чата
2. 🔄 Переделка интерфейсов помощников
3. 🔄 Переделка интерфейсов шаблонов
4. 🔄 Создание интерфейса управления диалогами
5. 🔄 Адаптация дашборда
6. 🔄 Обновление JavaScript функционала

### Этап 5: Интеграции (2-3 дня)
1. 🔄 Обновление FastAPI сервиса
2. 🔄 Настройка новых коллекций Qdrant
3. 🔄 Адаптация работы с Ollama
4. 🔄 Тестирование интеграций

### Этап 6: Тестирование и отладка (2-3 дня)
1. 🔄 Функциональное тестирование
2. 🔄 Тестирование производительности
3. 🔄 Исправление ошибок
4. 🔄 Оптимизация

### Этап 7: Документация и деплой (1 день)
1. 🔄 Обновление документации
2. 🔄 Подготовка к продакшену
3. 🔄 Деплой и мониторинг

---

## 10. РИСКИ И РЕКОМЕНДАЦИИ

### 10.1. Основные риски
1. **Потеря данных** при миграции БД
2. **Конфликты зависимостей** при крупных изменениях
3. **Сложность отката** из-за масштаба изменений
4. **Производительность** новой архитектуры

### 10.2. Рекомендации
1. **Создать полную резервную копию** перед началом
2. **Работать поэтапно** с возможностью отката на каждом этапе
3. **Тестировать на каждом этапе** функциональность
4. **Сохранить возможность запуска** старой версии параллельно
5. **Подготовить скрипты миграции данных** пользователей

---

## 11. ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ

### 11.1. Функциональные улучшения
- ✅ Универсальная система помощников вместо узкоспециализированного анализа документов
- ✅ Интерактивные диалоги с помощниками
- ✅ Библиотека и маркетплейс шаблонов промптов
- ✅ Гибкая настройка помощников под разные задачи
- ✅ История диалогов и аналитика использования

### 11.2. Технические улучшения  
- ✅ Более модульная архитектура
- ✅ Лучшая масштабируемость
- ✅ Упрощение добавления новых типов помощников
- ✅ Улучшенная работа с векторной БД

### 11.3. Пользовательский опыт
- ✅ Интуитивный интерфейс чата
- ✅ Быстрое создание и настройка помощников
- ✅ Удобное управление диалогами
- ✅ Возможность делиться шаблонами между пользователями

---

**ИТОГО:** Трансформация затронет практически все компоненты системы, но результатом станет универсальная платформа для создания и использования LLM-помощников вместо узкоспециализированного инструмента анализа документов ППЭЭ.

## 12. ФАЙЛЫ ДЛЯ ИЗМЕНЕНИЯ

### 12.1. Переименование файлов

**Модели:**
- `/home/user/cc-agents/ppee-flask/app/models/application.py` → `assistant.py`
- `/home/user/cc-agents/ppee-flask/app/models/checklist.py` → `prompt_template.py`
- `/home/user/cc-agents/ppee-flask/app/models/user.py` - **ОБНОВИТЬ**

**Blueprints:**
- `/home/user/cc-agents/ppee-flask/app/blueprints/applications/` → `assistants/`
- `/home/user/cc-agents/ppee-flask/app/blueprints/checklists/` → `templates/`
- `/home/user/cc-agents/ppee-flask/app/blueprints/search/` → `chat/`
- `/home/user/cc-agents/ppee-flask/app/blueprints/llm_management/` → `models/`
- `/home/user/cc-agents/ppee-flask/app/blueprints/stats/` → `analytics/`

**Tasks:**
- `/home/user/cc-agents/ppee-flask/app/tasks/indexing_tasks.py` → `knowledge_tasks.py`
- `/home/user/cc-agents/ppee-flask/app/tasks/llm_tasks.py` → `chat_tasks.py`
- `/home/user/cc-agents/ppee-flask/app/tasks/search_tasks.py` → `retrieval_tasks.py`

**Templates:**
- `/home/user/cc-agents/ppee-flask/app/templates/applications/` → `assistants/`
- `/home/user/cc-agents/ppee-flask/app/templates/checklists/` → `templates/`
- `/home/user/cc-agents/ppee-flask/app/templates/search/` → `chat/`
- `/home/user/cc-agents/ppee-flask/app/templates/llm_management/` → `models/`

### 12.2. Новые файлы для создания

**Модели:**
- `/home/user/cc-agents/ppee-flask/app/models/conversation.py` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/models/message.py` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/models/knowledge_chunk.py` - **СОЗДАТЬ**

**Blueprints:**
- `/home/user/cc-agents/ppee-flask/app/blueprints/conversations/` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/blueprints/knowledge/` - **СОЗДАТЬ**

**Tasks:**
- `/home/user/cc-agents/ppee-flask/app/tasks/template_tasks.py` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/tasks/training_tasks.py` - **СОЗДАТЬ**

**Templates:**
- `/home/user/cc-agents/ppee-flask/app/templates/chat/` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/templates/conversations/` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/templates/knowledge/` - **СОЗДАТЬ**

**JavaScript:**
- `/home/user/cc-agents/ppee-flask/app/static/js/chat.js` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/static/js/message-streaming.js` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/static/js/template-editor.js` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/static/js/assistant-config.js` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/static/js/knowledge-upload.js` - **СОЗДАТЬ**

**CSS:**
- `/home/user/cc-agents/ppee-flask/app/static/css/chat.css` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/static/css/templates.css` - **СОЗДАТЬ**
- `/home/user/cc-agents/ppee-flask/app/static/css/assistants.css` - **СОЗДАТЬ**

### 12.3. Файлы для значительного обновления

**Конфигурация:**
- `/home/user/cc-agents/ppee-flask/config.py` - **ОБНОВИТЬ**
- `/home/user/cc-agents/ppee-flask/app/__init__.py` - **ОБНОВИТЬ**

**Сервисы:**
- `/home/user/cc-agents/ppee-flask/app/services/fastapi_client.py` - **ОБНОВИТЬ**

**Утилиты:**
- `/home/user/cc-agents/ppee-flask/app/utils/db_utils.py` - **ОБНОВИТЬ**
- `/home/user/cc-agents/ppee-flask/app/utils/chunk_utils.py` → `knowledge_utils.py`

**JavaScript (существующие):**
- `/home/user/cc-agents/ppee-flask/app/static/js/script.js` - **АДАПТИРОВАТЬ**
- `/home/user/cc-agents/ppee-flask/app/static/js/task-progress.js` - **АДАПТИРОВАТЬ**

**CSS (существующие):**
- `/home/user/cc-agents/ppee-flask/app/static/css/style.css` - **ОБНОВИТЬ**
- `/home/user/cc-agents/ppee-flask/app/static/css/styles-additions.css` - **ОБНОВИТЬ**

**База данных:**
- `/home/user/cc-agents/ppee-flask/initialize_db.py` - **ОБНОВИТЬ**
- Создать миграции в `/home/user/cc-agents/ppee-flask/migrations/versions/`

---

**ОБЩЕЕ КОЛИЧЕСТВО ЗАТРАГИВАЕМЫХ ФАЙЛОВ:** ~60-80 файлов
**ВРЕМЯ ВЫПОЛНЕНИЯ:** 12-18 дней (при работе одного разработчика)