"""Задачи Celery для обработки чата с помощниками"""

from app import celery, db, create_app
from app.models import Application, Message, Conversation, Checklist
from app.services.fastapi_client import FastAPIClient
import logging
import requests
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def process_chat_message_impl(conversation_id, message_id, template_id=None):
    """Синхронная обработка сообщения (ядро логики для чата)."""
    app = create_app()
    with app.app_context():
        # Получаем данные
        conversation = Conversation.query.get(conversation_id)
        message = Message.query.get(message_id)
        if not conversation or not message:
            return {'status': 'error', 'message': 'Диалог или сообщение не найдены'}
        assistant = conversation.assistant
        if not assistant:
            return {'status': 'error', 'message': 'Помощник не найден'}

        fastapi_url = app.config.get('FASTAPI_URL', 'http://localhost:8002')
        logger.info(f"[CHAT] FASTAPI_URL={fastapi_url}")

        # Поиск
        search_results = []
        if assistant.enable_search and assistant.status in ['indexed', 'analyzed']:
            try:
                logger.info(f"[CHAT] POST {fastapi_url}/search application_id={assistant.id} query='{message.content[:50]}'")
                search_response = requests.post(
                    f"{fastapi_url}/search",
                    json={
                    "application_id": str(assistant.id),
                    "query": message.content,
                    "limit": assistant.search_limit or 10,
                    "use_reranker": assistant.use_reranker,
                    "rerank_limit": 20 if assistant.use_reranker else None,
                    "use_smart_search": True,
                    "vector_weight": 0.5,
                    "text_weight": 0.5,
                        "hybrid_threshold": 10
                    },
                    timeout=10
                )
                if search_response.status_code == 200:
                    data = search_response.json()
                    search_results = data.get("results", [])
                    sample_text = ''
                    if search_results:
                        sample_text = (search_results[0].get('text') or '')[:120].replace('\n', ' ')
                    logger.info(f"[CHAT] /search resp status=200 results={len(search_results)} sample='{sample_text}'")
                else:
                    body = (search_response.text or '')[:200].replace('\n', ' ')
                    logger.warning(f"[CHAT] /search resp status={search_response.status_code} body='{body}'")
            except Exception as e:
                logger.error(f"Ошибка при поиске: {e}")

        # Шаблон
        prompt_template = None
        # 1) Явно выбранный шаблон из UI
        if template_id:
            template = Checklist.query.get(template_id)
            prompt_template = template.get_prompt_template() if template else None
        # 2) Иначе — первая привязанная к ассистенту заготовка (если есть)
        if not prompt_template and assistant.checklists:
            try:
                first_template = assistant.checklists[0] if isinstance(assistant.checklists, list) else assistant.checklists.first()
                if first_template:
                    prompt_template = first_template.get_prompt_template()
            except Exception:
                pass
        # 3) Фоллбек по типу ассистента
        if not prompt_template:
            if assistant.assistant_type == 'support':
                prompt_template = """Ты - эксперт службы поддержки. На основе предоставленной информации помоги решить проблему клиента.

Запрос клиента: {query}

Информация из базы знаний:
{context}

Предоставь структурированный ответ с конкретными шагами решения."""
            else:
                prompt_template = """Ты - помощник. Ответь на вопрос пользователя.

Вопрос: {query}

Доступная информация:
{context}

Дай полезный и информативный ответ."""

        context = format_search_context(search_results)
        history_context = conversation.get_context_for_llm(limit=5)
        if history_context:
            context = f"История диалога:\n{history_context}\n\n" + context

        final_prompt = prompt_template.format(
            query=message.content,
            context=context if context else "Информация не найдена в базе знаний."
        )
        system_prompt = assistant.get_system_prompt()
        if system_prompt:
            final_prompt = f"{system_prompt}\n\n{final_prompt}"

        # Вызов LLM
        try:
            model_to_use = _resolve_llm_model_for_message(assistant, template_id)
            logger.info(f"[CHAT] POST {fastapi_url}/llm/process model={model_to_use}")
            llm_response = requests.post(
                f"{fastapi_url}/llm/process",
                json={
                # Если в выбранном/связанном шаблоне задан тег llm:MODEL — используем его, иначе модель ассистента
                "model_name": model_to_use,
                "prompt": final_prompt,
                "context": "",
                "parameters": {
                    'temperature': assistant.temperature or 0.7,
                    'max_tokens': assistant.max_tokens or 2000,
                    'search_query': message.content
                },
                    "query": message.content
                },
                timeout=60
            )
            if llm_response.status_code == 200:
                llm_data = llm_response.json()
                response_text = llm_data.get("response", "Не удалось сгенерировать ответ")
                tokens_info = llm_data.get("tokens", {})
                # Добавляем полный сырой ответ API в скрываемый блок для диагностики
                raw = (llm_response.text or '')
                safe_raw = raw.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                response_text = (
                    f"{response_text}\n\n"
                    f"<div class=\"tech-details\" style=\"display:none;margin-top:8px\"><small>API raw:</small>"
                    f"<pre style=\"white-space:pre-wrap\">{safe_raw}</pre></div>"
                )
            else:
                # Добавляем тело ошибки в скрываемый блок
                body = llm_response.text or ''
                safe_body = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                response_text = (
                    "Извините, произошла ошибка при генерации ответа. Попробуйте еще раз."
                    f"\n\n<div class=\"tech-details\" style=\"display:none;margin-top:8px\"><small>API error {llm_response.status_code}:</small>"
                    f"<pre style=\"white-space:pre-wrap\">{safe_body}</pre></div>"
                )
                tokens_info = {}
        except Exception as e:
            logger.error(f"Ошибка при вызове LLM: {e}")
            response_text = "Извините, сервис временно недоступен. Попробуйте позже."
            tokens_info = {}

        # Сохранение
        assistant_message = Message(
            conversation_id=conversation_id,
            role='assistant',
            content=response_text,
            search_results=search_results[:5] if search_results else None,
            search_query=message.content,
            llm_request={
                'prompt': final_prompt[:1000],
                'model': assistant.llm_model,
                'temperature': assistant.temperature,
                'max_tokens': assistant.max_tokens
            },
            llm_response=tokens_info,
            tokens_count=tokens_info.get('total_tokens', 0),
            processing_time=time.time() - message.created_at.timestamp() if message.created_at else 0
        )
        db.session.add(assistant_message)
        conversation.update_statistics()
        assistant.increment_message_count()
        if template_id:
            template = Checklist.query.get(template_id)
            if template:
                template.increment_usage()
        db.session.commit()

        return {
            'status': 'success',
            'message': response_text,
            'message_id': assistant_message.id,
            'search_results_count': len(search_results),
            'tokens_used': tokens_info.get('total_tokens', 0),
            'processing_time': assistant_message.processing_time
        }


@celery.task(bind=True)
def process_chat_message(self, conversation_id, message_id, template_id=None):
    """Celery-обертка с прогрессом вокруг синхронной имплементации."""
    try:
        self.update_state(state='PROGRESS', meta={'status': 'progress', 'progress': 5, 'message': 'Старт...'})
        result = process_chat_message_impl(conversation_id, message_id, template_id)
        if isinstance(result, dict) and result.get('status') == 'success':
            self.update_state(state='SUCCESS', meta={'status': 'success', 'progress': 100, 'message': 'Готово'})
        else:
            self.update_state(state='FAILURE', meta={'status': 'error', 'message': result.get('message') if isinstance(result, dict) else 'Ошибка'})
        return result
    except Exception as e:
        logger.exception(f"Критическая ошибка в process_chat_message: {e}")
        self.update_state(state='FAILURE', meta={'status': 'error', 'message': str(e)})
        return {'status': 'error', 'message': f'Произошла ошибка: {str(e)}'}


def format_search_context(search_results, max_results=5):
    """Форматирует результаты поиска для контекста LLM"""
    if not search_results:
        return ""
    
    context_parts = []
    for i, result in enumerate(search_results[:max_results], 1):
        text = result.get('text', '')
        metadata = result.get('metadata', {})
        
        # Форматируем каждый результат
        part = f"[Документ {i}]\n"
        if metadata.get('document_id'):
            part += f"Источник: {metadata['document_id']}\n"
        if metadata.get('page_number'):
            part += f"Страница: {metadata['page_number']}\n"
        part += f"Текст: {text[:500]}..."  # Ограничиваем длину текста
        
        context_parts.append(part)
    
    return "\n\n".join(context_parts)


@celery.task(bind=True)
def process_support_query(self, assistant_id, query_text, context_info=None):
    """
    Упрощенная задача для обработки запроса поддержки без сохранения в диалог
    Используется для быстрых одноразовых запросов
    """
    
    app = create_app()
    with app.app_context():
        try:
            assistant = Application.query.get(assistant_id)
            if not assistant:
                return {'status': 'error', 'message': 'Помощник не найден'}
            
            # Получаем настройки FastAPI
            fastapi_url = app.config.get('FASTAPI_URL', 'http://localhost:8002')
            
            # Выполняем поиск
            search_results = []
            if assistant.enable_search and assistant.status == 'indexed':
                try:
                    search_response = requests.post(f"{fastapi_url}/search", json={
                        "application_id": str(assistant_id),
                        "query": query_text,
                        "limit": 15,  # Больше результатов для одноразового запроса
                        "use_reranker": True,
                        "rerank_limit": 30
                    })
                    
                    if search_response.status_code == 200:
                        search_results = search_response.json().get("results", [])
                except Exception as e:
                    logger.error(f"Ошибка при поиске: {e}")
            
            # Формируем контекст
            context = format_search_context(search_results, max_results=10)
            
            # Добавляем дополнительный контекст если есть
            if context_info:
                context = f"Дополнительная информация:\n{context_info}\n\n{context}"
            
            # Специальный промпт для поддержки
            support_prompt = """Ты - эксперт службы поддержки. Помоги решить проблему клиента.

Запрос: {query}

База знаний:
{context}

Предоставь ответ в формате:

## 📋 Анализ
[Что понял из запроса]

## ✅ Решение
[Конкретные шаги]

## ℹ️ Примечания
[Дополнительная информация если нужно]"""
            
            final_prompt = support_prompt.format(
                query=query_text,
                context=context if context else "База знаний пуста."
            )
            
            # Отправляем в LLM
            try:
                llm_response = requests.post(
                    f"{fastapi_url}/llm/process",
                    json={
                    "model_name": assistant.llm_model or 'gemma3:27b',
                    "prompt": final_prompt,
                    "context": "",
                    "parameters": {
                        'temperature': 0.3,  # Низкая температура для консистентности
                        'max_tokens': 2500
                    },
                        "query": query_text
                    },
                    timeout=60
                )
                
                if llm_response.status_code == 200:
                    response_text = llm_response.json().get("response", "Ошибка генерации")
                else:
                    response_text = "Ошибка при обращении к LLM"
                    
            except Exception as e:
                logger.error(f"Ошибка LLM: {e}")
                response_text = "Сервис временно недоступен"
            
            return {
                'status': 'success',
                'response': response_text,
                'sources': [r.get('metadata', {}).get('document_id') for r in search_results[:5]]
            }
            
        except Exception as e:
            logger.exception(f"Ошибка в process_support_query: {e}")
            return {'status': 'error', 'message': str(e)}


def _resolve_llm_model_for_message(assistant: Application, template_id: int = None) -> str:
    """Определяет модель LLM для обработки сообщения.
    Приоритет:
      1) Если выбран шаблон и у него есть тег вида llm:MODEL — использовать его
      2) Если у ассистента привязан первый шаблон с тегом llm:MODEL — использовать его
      3) Иначе — модель ассистента
    """
    try:
        # 1) Явно выбранный шаблон
        if template_id:
            t = Checklist.query.get(template_id)
            if t and t.tags:
                for tag in t.tags:
                    if isinstance(tag, str) and tag.startswith('llm:'):
                        return tag.split(':', 1)[1]
        # 2) Любой привязанный к ассистенту шаблон с тегом llm
        if assistant.checklists:
            candidates = assistant.checklists if isinstance(assistant.checklists, list) else assistant.checklists.all()
            for t in candidates:
                if t.tags:
                    for tag in t.tags:
                        if isinstance(tag, str) and tag.startswith('llm:'):
                            return tag.split(':', 1)[1]
    except Exception:
        pass
    # 3) Модель ассистента по умолчанию
    return assistant.llm_model or 'gemma3:27b'