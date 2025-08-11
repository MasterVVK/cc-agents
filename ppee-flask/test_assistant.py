#!/usr/bin/env python
"""Скрипт для создания тестового помощника и проверки функционала"""

from app import create_app, db
from app.models import User, Application, Checklist
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    print("Создание тестовых данных для системы помощников...")
    
    # Проверяем/создаем тестового пользователя
    test_user = User.query.filter_by(username='test_user').first()
    if not test_user:
        test_user = User(
            username='test_user',
            email='test@example.com',
            password_hash=generate_password_hash('password123'),
            role='admin'
        )
        db.session.add(test_user)
        db.session.commit()
        print(f"✓ Создан пользователь: {test_user.username}")
    else:
        print(f"✓ Пользователь уже существует: {test_user.username}")
    
    # Создаем тестового помощника (Application как Assistant)
    test_assistant = Application.query.filter_by(name='Помощник службы поддержки').first()
    if not test_assistant:
        test_assistant = Application(
            name='Помощник службы поддержки',
            description='Тестовый помощник для ответов на вопросы пользователей',
            status='indexed',  # Помечаем как проиндексированный
            user_id=test_user.id,
            assistant_type='support',
            system_prompt='Ты - дружелюбный помощник службы поддержки. Отвечай на вопросы пользователей вежливо и информативно.',
            llm_model='gemma3:27b',
            temperature=0.7,
            max_tokens=2000,
            is_public=True,
            enable_search=True,
            search_limit=10,
            use_reranker=True
        )
        db.session.add(test_assistant)
        db.session.commit()
        print(f"✓ Создан помощник: {test_assistant.name}")
    else:
        # Обновляем настройки существующего помощника
        test_assistant.assistant_type = 'support'
        test_assistant.is_public = True
        test_assistant.status = 'indexed'
        db.session.commit()
        print(f"✓ Обновлен помощник: {test_assistant.name}")
    
    # Создаем тестовый шаблон промпта (Checklist как PromptTemplate)
    test_template = Checklist.query.filter_by(name='Шаблон поддержки').first()
    if not test_template:
        test_template = Checklist(
            name='Шаблон поддержки',
            description='Шаблон для структурированных ответов службы поддержки',
            user_id=test_user.id,
            is_public=True,
            template_type='support',
            prompt_text="""Ты - эксперт службы поддержки. На основе предоставленной информации помоги решить проблему клиента.

Запрос клиента: {query}

Информация из базы знаний:
{context}

Предоставь структурированный ответ:

## 📋 Анализ проблемы
[Кратко опиши суть проблемы]

## ✅ Решение
[Пошаговое решение или ответ на вопрос]

## ℹ️ Дополнительная информация
[Если нужно что-то уточнить или есть рекомендации]""",
            response_format='markdown'
        )
        db.session.add(test_template)
        db.session.commit()
        print(f"✓ Создан шаблон промпта: {test_template.name}")
    else:
        print(f"✓ Шаблон уже существует: {test_template.name}")
    
    # Создаем еще одного помощника для разнообразия
    qa_assistant = Application.query.filter_by(name='Q&A Помощник').first()
    if not qa_assistant:
        qa_assistant = Application(
            name='Q&A Помощник',
            description='Помощник для ответов на часто задаваемые вопросы',
            status='indexed',
            user_id=test_user.id,
            assistant_type='qa',
            llm_model='gemma3:27b',
            temperature=0.5,
            max_tokens=1500,
            is_public=True,
            enable_search=True,
            search_limit=5,
            use_reranker=False
        )
        db.session.add(qa_assistant)
        db.session.commit()
        print(f"✓ Создан помощник: {qa_assistant.name}")
    else:
        qa_assistant.assistant_type = 'qa'
        qa_assistant.is_public = True
        qa_assistant.status = 'indexed'
        db.session.commit()
        print(f"✓ Обновлен помощник: {qa_assistant.name}")
    
    print("\n✅ Тестовые данные успешно созданы!")
    print("\nТеперь вы можете:")
    print("1. Запустить приложение: python wsgi.py")
    print("2. Войти с учетными данными: test_user / password123")
    print("3. Перейти в раздел /chat для начала диалога с помощником")
    print("\nДоступные помощники:")
    print(f"  - {test_assistant.name} (ID: {test_assistant.id})")
    print(f"  - {qa_assistant.name} (ID: {qa_assistant.id})")
    print(f"\nДоступные шаблоны:")
    print(f"  - {test_template.name} (ID: {test_template.id})")