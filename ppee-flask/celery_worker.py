import os
from app import create_app, celery

app = create_app(os.getenv('FLASK_CONFIG') or 'default')
app.app_context().push()

# ВАЖНО: Импортируем модули задач, чтобы Celery зарегистрировал их при запуске воркера
# Без этого Celery может не видеть задачи (unregistered task)
from app.tasks import indexing_tasks  # noqa: F401
from app.tasks import llm_tasks       # noqa: F401
from app.tasks import search_tasks    # noqa: F401
from app.tasks import chat_tasks      # noqa: F401