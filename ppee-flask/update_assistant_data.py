#!/usr/bin/env python
"""
Скрипт для обновления данных помощника в БД
"""

from app import create_app, db
from app.models import Application

def update_assistant_data():
    """Обновляет данные помощника для корректного отображения"""
    app = create_app()
    
    with app.app_context():
        # Получаем первого помощника
        assistant = Application.query.first()
        
        if assistant:
            print(f"\n=== Обновление данных помощника ID={assistant.id} ===")
            print(f"Текущее имя: {assistant.name}")
            print(f"Текущее описание: {assistant.description or '(пусто)'}")
            
            # Обновляем данные
            if not assistant.description:
                assistant.description = "Интеллектуальный помощник для ответов на вопросы и помощи в решении задач"
            
            # Убеждаемся, что все поля заполнены корректно
            if not assistant.assistant_type:
                assistant.assistant_type = 'support'
            
            if not assistant.llm_model:
                assistant.llm_model = 'gemma3:27b'
            
            if assistant.temperature is None:
                assistant.temperature = 0.7
            
            if assistant.enable_search is None:
                assistant.enable_search = True
            
            if assistant.search_limit is None:
                assistant.search_limit = 10
            
            if assistant.use_reranker is None:
                assistant.use_reranker = True
                
            if assistant.max_tokens is None:
                assistant.max_tokens = 2000
            
            # Обновляем статистику (если нужно для тестирования)
            if not assistant.total_conversations:
                assistant.total_conversations = 1
            if not assistant.total_messages:
                assistant.total_messages = 5
            
            db.session.commit()
            
            print("\n✅ Данные обновлены:")
            print(f"  Имя: {assistant.name}")
            print(f"  Описание: {assistant.description}")
            print(f"  Тип: {assistant.assistant_type}")
            print(f"  Модель: {assistant.llm_model}")
            print(f"  Температура: {assistant.temperature}")
            print(f"  Поиск включен: {assistant.enable_search}")
            print(f"  Лимит поиска: {assistant.search_limit}")
            print(f"  Ререйтинг: {assistant.use_reranker}")
            print(f"  Макс. токенов: {assistant.max_tokens}")
            print(f"  Публичный: {assistant.is_public}")
            print(f"  Диалогов: {assistant.total_conversations}")
            print(f"  Сообщений: {assistant.total_messages}")
            
        else:
            print("❌ Помощники не найдены в БД")
            print("\nСоздаём тестового помощника...")
            
            assistant = Application(
                name="Универсальный помощник",
                description="Интеллектуальный AI-помощник для ответов на вопросы, анализа документов и помощи в решении различных задач",
                assistant_type='support',
                llm_model='gemma3:27b',
                temperature=0.7,
                enable_search=True,
                search_limit=10,
                use_reranker=True,
                max_tokens=2000,
                is_public=True,
                total_conversations=0,
                total_messages=0,
                status='active'
            )
            
            db.session.add(assistant)
            db.session.commit()
            
            print(f"✅ Создан новый помощник ID={assistant.id}")

if __name__ == '__main__':
    update_assistant_data()