#!/usr/bin/env python
"""Скрипт для исправления NULL значений в новых полях"""

from app import create_app, db
from app.models import Application, Checklist

app = create_app()

with app.app_context():
    print("Исправление NULL значений в базе данных...")
    
    # Исправляем поля для Applications (Assistants)
    applications = Application.query.all()
    for app_item in applications:
        # Устанавливаем значения по умолчанию для новых полей если они NULL
        if app_item.assistant_type is None:
            app_item.assistant_type = 'support'
        if app_item.llm_model is None:
            app_item.llm_model = 'gemma3:27b'
        if app_item.temperature is None:
            app_item.temperature = 0.7
        if app_item.max_tokens is None:
            app_item.max_tokens = 2000
        if app_item.is_public is None:
            app_item.is_public = False
        if app_item.enable_search is None:
            app_item.enable_search = True
        if app_item.enable_web_search is None:
            app_item.enable_web_search = False
        if app_item.search_limit is None:
            app_item.search_limit = 10
        if app_item.use_reranker is None:
            app_item.use_reranker = True
        if app_item.total_conversations is None:
            app_item.total_conversations = 0
        if app_item.total_messages is None:
            app_item.total_messages = 0
        if app_item.average_rating is None:
            app_item.average_rating = 0.0
        
        print(f"✓ Обновлена заявка/помощник: {app_item.name}")
    
    # Исправляем поля для Checklists (PromptTemplates)
    checklists = Checklist.query.all()
    for checklist in checklists:
        if checklist.template_type is None:
            checklist.template_type = 'support'
        if checklist.usage_count is None:
            checklist.usage_count = 0
        if checklist.rating is None:
            checklist.rating = 0.0
        
        print(f"✓ Обновлен чек-лист/шаблон: {checklist.name}")
    
    # Сохраняем изменения
    db.session.commit()
    print("\n✅ Все NULL значения исправлены!")