#!/usr/bin/env python
"""Тестирование полного цикла обработки сообщений в чате"""

from app import create_app, db
from app.models import User, Application, Conversation, Message
from app.tasks.chat_tasks import process_chat_message

app = create_app()

with app.app_context():
    print("🧪 Тестирование полного цикла чата\n")
    
    # Получаем тестового пользователя и помощника
    user = User.query.filter_by(username='test_user').first()
    assistant = Application.query.filter_by(name='Помощник службы поддержки').first()
    
    if not user or not assistant:
        print("❌ Не найден тестовый пользователь или помощник")
        print("   Запустите test_assistant.py для создания тестовых данных")
        exit(1)
    
    print(f"✓ Пользователь: {user.username}")
    print(f"✓ Помощник: {assistant.name}")
    
    # Создаем тестовый диалог
    conversation = Conversation(
        assistant_id=assistant.id,
        user_id=user.id,
        title="Тестовый диалог",
        status='active'
    )
    db.session.add(conversation)
    db.session.commit()
    print(f"✓ Создан диалог ID: {conversation.id}")
    
    # Создаем тестовое сообщение
    test_message = Message(
        conversation_id=conversation.id,
        role='user',
        content='Как мне настроить уведомления в системе?'
    )
    db.session.add(test_message)
    db.session.commit()
    print(f"✓ Создано сообщение ID: {test_message.id}")
    
    print("\n📤 Отправка сообщения на обработку...")
    print(f"   Текст: '{test_message.content}'")
    
    # Запускаем обработку синхронно для теста
    try:
        result = process_chat_message(
            conversation_id=conversation.id,
            message_id=test_message.id
        )
        
        print("\n📥 Результат обработки:")
        print(f"   Статус: {result.get('status')}")
        
        if result['status'] == 'success':
            print(f"   Ответ: {result.get('message', 'Нет ответа')[:200]}...")
            print(f"   Найдено документов: {result.get('search_results_count', 0)}")
            print(f"   Использовано токенов: {result.get('tokens_used', 0)}")
            print(f"   Время обработки: {result.get('processing_time', 0):.2f} сек")
            
            # Проверяем, что ответ сохранен в БД
            assistant_message = Message.query.filter_by(
                conversation_id=conversation.id,
                role='assistant'
            ).first()
            
            if assistant_message:
                print(f"\n✅ Ответ успешно сохранен в БД")
                print(f"   ID сообщения: {assistant_message.id}")
            else:
                print(f"\n⚠️ Ответ не найден в БД")
                
        else:
            print(f"   Ошибка: {result.get('message')}")
            
    except Exception as e:
        print(f"\n❌ Ошибка при обработке: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*50)
    print("Тест завершен!")
    print("\nДля полного тестирования:")
    print("1. Убедитесь, что запущен FastAPI сервис (порт 8002)")
    print("2. Убедитесь, что запущен Qdrant (порт 6333)")
    print("3. Убедитесь, что запущен Ollama с моделью")
    print("4. Загрузите документы в помощника для поиска")