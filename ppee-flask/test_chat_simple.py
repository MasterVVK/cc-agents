#!/usr/bin/env python
"""Простое тестирование обработки сообщений без Celery"""

from app import create_app, db
from app.models import User, Application, Conversation, Message
import requests

app = create_app()

def simple_chat_response(assistant, user_message):
    """Простая функция для генерации ответа без Celery"""
    
    # Формируем простой промпт
    prompt = f"""Ты - {assistant.name}. {assistant.get_system_prompt()}

Вопрос пользователя: {user_message}

Дай полезный и информативный ответ."""
    
    # Если нет внешних сервисов, возвращаем заглушку
    response = f"""Спасибо за ваш вопрос: "{user_message}"

Я - {assistant.name}, и я готов помочь вам. 

К сожалению, сейчас я работаю в тестовом режиме без подключения к базе знаний. 

Для полноценной работы необходимо:
1. Загрузить документы в базу знаний
2. Запустить сервисы (FastAPI, Qdrant, Ollama)
3. Настроить интеграцию

После настройки я смогу:
- Искать информацию в базе знаний
- Давать точные ответы на основе документов
- Предоставлять пошаговые инструкции

Пока что вы можете протестировать интерфейс чата и базовый функционал."""
    
    return response

with app.app_context():
    print("🧪 Простое тестирование чата\n")
    
    # Получаем данные
    user = User.query.filter_by(username='test_user').first()
    assistant = Application.query.filter_by(name='Помощник службы поддержки').first()
    
    if not user or not assistant:
        print("❌ Не найдены тестовые данные")
        exit(1)
    
    print(f"✓ Пользователь: {user.username}")
    print(f"✓ Помощник: {assistant.name}")
    print(f"  Тип: {assistant.assistant_type}")
    print(f"  Модель: {assistant.llm_model}")
    print(f"  Публичный: {'Да' if assistant.is_public else 'Нет'}")
    
    # Создаем или получаем диалог
    conversation = Conversation.query.filter_by(
        assistant_id=assistant.id,
        user_id=user.id,
        status='active'
    ).first()
    
    if not conversation:
        conversation = Conversation(
            assistant_id=assistant.id,
            user_id=user.id,
            title="Тестовый диалог",
            status='active'
        )
        db.session.add(conversation)
        db.session.commit()
        print(f"\n✓ Создан новый диалог ID: {conversation.id}")
    else:
        print(f"\n✓ Используется существующий диалог ID: {conversation.id}")
    
    # Тестовые сообщения
    test_messages = [
        "Как настроить уведомления?",
        "Что делать если забыл пароль?",
        "Как связаться с поддержкой?"
    ]
    
    print("\n" + "="*50)
    print("ТЕСТИРОВАНИЕ ДИАЛОГА")
    print("="*50)
    
    for test_text in test_messages:
        print(f"\n👤 Пользователь: {test_text}")
        
        # Сохраняем сообщение пользователя
        user_msg = Message(
            conversation_id=conversation.id,
            role='user',
            content=test_text
        )
        db.session.add(user_msg)
        db.session.commit()
        
        # Генерируем ответ
        response_text = simple_chat_response(assistant, test_text)
        
        # Сохраняем ответ помощника
        assistant_msg = Message(
            conversation_id=conversation.id,
            role='assistant',
            content=response_text
        )
        db.session.add(assistant_msg)
        db.session.commit()
        
        print(f"🤖 Помощник: {response_text[:200]}...")
        
        # Обновляем статистику
        conversation.update_statistics()
        assistant.increment_message_count()
    
    print("\n" + "="*50)
    print("СТАТИСТИКА")
    print("="*50)
    
    # Показываем статистику
    conversation = Conversation.query.get(conversation.id)
    print(f"Сообщений в диалоге: {conversation.message_count}")
    print(f"Последнее сообщение: {conversation.last_message_at}")
    
    assistant = Application.query.get(assistant.id)
    print(f"Всего сообщений помощника: {assistant.total_messages}")
    print(f"Всего диалогов: {assistant.total_conversations}")
    
    # Показываем последние сообщения
    print("\n" + "="*50)
    print("ИСТОРИЯ ДИАЛОГА")
    print("="*50)
    
    messages = conversation.get_last_messages(10)
    for msg in messages:
        role_icon = "👤" if msg.role == 'user' else "🤖"
        print(f"{role_icon} [{msg.created_at.strftime('%H:%M')}] {msg.content[:100]}...")
    
    print("\n✅ Тест завершен успешно!")
    print("\nТеперь вы можете:")
    print("1. Запустить приложение: python wsgi.py")
    print("2. Перейти в /chat")
    print("3. Увидеть созданный диалог в интерфейсе")