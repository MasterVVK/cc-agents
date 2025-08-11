from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.blueprints.chat import bp
from app.models import Application, Conversation, Message, Checklist
from app import db
from app.tasks.chat_tasks import process_chat_message, process_chat_message_impl
from celery import current_app as celery_app
import requests
import json
from datetime import datetime


@bp.route('/')
@login_required
def index():
    """Главная страница чата - выбор помощника"""
    # Получаем доступных помощников (Applications с indexed статусом)
    assistants = Application.query.filter(
        db.or_(
            Application.is_public == True,
            Application.user_id == current_user.id
        )
    ).order_by(Application.created_at.desc()).all()
    
    # Рассчитываем эффективную модель для отображения на карточке помощника
    # Приоритет: тег llm:MODEL в любом привязанном шаблоне → модель помощника
    resolved_models = {}
    try:
        for a in assistants:
            model = None
            try:
                if a.checklists:
                    templates = list(a.checklists) if not hasattr(a.checklists, 'all') else a.checklists.all()
                    for t in templates:
                        if t and t.tags:
                            for tag in t.tags:
                                if isinstance(tag, str) and tag.startswith('llm:'):
                                    model = tag.split(':', 1)[1]
                                    break
                        if model:
                            break
            except Exception:
                pass
            resolved_models[a.id] = model or a.llm_model or 'gemma3:27b'
    except Exception:
        # Фоллбек: если что-то пошло не так, используем модель помощника
        for a in assistants:
            resolved_models[a.id] = a.llm_model or 'gemma3:27b'

    # Получаем последние диалоги пользователя
    recent_conversations = Conversation.query.filter_by(
        user_id=current_user.id
    ).order_by(Conversation.updated_at.desc()).limit(10).all()
    
    return render_template('chat/index.html',
                         assistants=assistants,
                         recent_conversations=recent_conversations,
                         resolved_models=resolved_models,
                         title='Чат с помощником')


@bp.route('/assistant/<int:assistant_id>')
@login_required
def chat_with_assistant(assistant_id):
    """Страница чата с конкретным помощником"""
    assistant = Application.query.get_or_404(assistant_id)
    selected_template_id = request.args.get('template_id', type=int)
    
    # Проверяем доступ
    if not assistant.can_user_access(current_user):
        flash('У вас нет доступа к этому помощнику', 'error')
        return redirect(url_for('chat.index'))
    
    # Создаем или получаем активный диалог
    conversation = Conversation.query.filter_by(
        assistant_id=assistant_id,
        user_id=current_user.id,
        status='active'
    ).order_by(Conversation.updated_at.desc()).first()
    
    if not conversation:
        # Создаем новый диалог
        conversation = Conversation(
            assistant_id=assistant_id,
            user_id=current_user.id,
            title=f"Диалог с {assistant.name}",
            status='active'
        )
        db.session.add(conversation)
        db.session.commit()
        assistant.increment_conversation_count()
    
    # Получаем последние сообщения
    messages = conversation.get_last_messages(50)
    
    # Получаем шаблоны, назначенные этому помощнику (связанные чек-листы)
    prompt_templates = []
    try:
        # Если у ассистента есть привязанные шаблоны — показываем их
        if assistant.checklists:
            # assistant.checklists может быть динамическим; приводим к списку
            prompt_templates = list(assistant.checklists)
        # Если ничего не привязано — показываем публичные и свои как запасной вариант
        if not prompt_templates:
            prompt_templates = Checklist.query.filter(
                db.or_(
                    Checklist.is_public == True,
                    Checklist.user_id == current_user.id
                )
            ).all()
    except Exception as e:
        current_app.logger.error(f"Ошибка получения шаблонов для помощника {assistant_id}: {e}")
        prompt_templates = []
    
    # Если явный выбор не задан, а у помощника ровно один шаблон — подставляем его
    hide_template_select = False
    if not selected_template_id and prompt_templates and len(prompt_templates) == 1:
        selected_template_id = prompt_templates[0].id
        hide_template_select = True

    # Валидируем выбранный шаблон
    if selected_template_id:
        valid_ids = {tpl.id for tpl in prompt_templates}
        if selected_template_id not in valid_ids:
            selected_template_id = None

    # Определяем модель LLM для отображения (с учетом выбранного шаблона)
    resolved_llm_model = assistant.llm_model
    try:
        if selected_template_id:
            sel_tpl = next((t for t in prompt_templates if t.id == selected_template_id), None)
            if sel_tpl and sel_tpl.tags:
                for tag in sel_tpl.tags:
                    if isinstance(tag, str) and tag.startswith('llm:'):
                        resolved_llm_model = tag.split(':', 1)[1]
                        break
    except Exception:
        pass

    return render_template('chat/conversation.html',
                         assistant=assistant,
                         conversation=conversation,
                         messages=messages,
                         prompt_templates=prompt_templates,
                         selected_template_id=selected_template_id,
                         hide_template_select=hide_template_select,
                         resolved_llm_model=resolved_llm_model,
                         title=f'Чат с {assistant.name}')


@bp.route('/conversation/<int:conversation_id>')
@login_required
def continue_conversation(conversation_id):
    """Продолжение существующего диалога"""
    conversation = Conversation.query.get_or_404(conversation_id)
    
    # Проверяем доступ
    if conversation.user_id != current_user.id:
        flash('У вас нет доступа к этому диалогу', 'error')
        return redirect(url_for('chat.index'))
    
    return redirect(url_for('chat.chat_with_assistant', 
                          assistant_id=conversation.assistant_id))


@bp.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    """API endpoint для отправки сообщения помощнику"""
    data = request.get_json()
    current_app.logger.info("[CHAT] send_message called")
    
    conversation_id = data.get('conversation_id')
    message_text = data.get('message')
    template_id = data.get('template_id')  # Опциональный ID шаблона промпта
    
    if not conversation_id or not message_text:
        return jsonify({'status': 'error', 'message': 'Не указан диалог или сообщение'}), 400
    
    # Получаем диалог
    conversation = Conversation.query.get(conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Диалог не найден'}), 404
    
    # Получаем помощника
    assistant = conversation.assistant
    if not assistant:
        return jsonify({'status': 'error', 'message': 'Помощник не найден'}), 404
    
    # Сохраняем сообщение пользователя
    user_message = Message(
        conversation_id=conversation_id,
        role='user',
        content=message_text
    )
    db.session.add(user_message)
    db.session.commit()
    current_app.logger.info(f"[CHAT] user_message saved id={user_message.id} conv={conversation_id}")
    
    # Обновляем статистику
    conversation.update_statistics()
    assistant.increment_message_count()
    
    # Получаем шаблон промпта если указан
    prompt_template = None
    if template_id:
        prompt_template = Checklist.query.get(template_id)
        if prompt_template:
            prompt_template.increment_usage()
    
    # Если Celery работает в eager-режиме (dev), обрабатываем синхронно сразу
    celery_eager = current_app.config.get('CELERY_CONFIG', {}).get('task_always_eager', False)
    current_app.logger.info(f"[CHAT] celery_eager={celery_eager}")
    if celery_eager:
        try:
            result = process_chat_message_impl(conversation_id=conversation_id,
                                               message_id=user_message.id,
                                               template_id=template_id)
            if isinstance(result, dict) and result.get('status') == 'success':
                current_app.logger.info(f"[CHAT] sync result ok msg_id={result.get('message_id')}")
                return jsonify({
                    'status': 'success',
                    'message_id': result.get('message_id'),
                    'message': result.get('message', 'Готово')
                })
            return jsonify({'status': 'error', 'message': result.get('message', 'Ошибка') if isinstance(result, dict) else 'Ошибка'}), 500
        except Exception as e2:
            current_app.logger.error(f"Ошибка при синхронной обработке (eager): {e2}")
            return jsonify({'status': 'error', 'message': f'Ошибка при обработке сообщения: {str(e2)}'}), 500

    # Иначе — обычный асинхронный запуск через Celery
    try:
        task = process_chat_message.delay(
            conversation_id=conversation_id,
            message_id=user_message.id,
            template_id=template_id
        )
        current_app.logger.info(f"[CHAT] task scheduled id={task.id} msg_id={user_message.id}")
        return jsonify({
            'status': 'pending',
            'task_id': task.id,
            'message_id': user_message.id,
            'message': 'Обрабатываю запрос...'
        })
    except Exception as e:
        # Фоллбек: выполняем обработку синхронно, чтобы чат работал без Celery/Redis
        current_app.logger.warning(f"Celery недоступен, выполняю обработку синхронно: {e}")
        try:
            result = process_chat_message_impl(conversation_id=conversation_id,
                                               message_id=user_message.id,
                                               template_id=template_id)
            if isinstance(result, dict) and result.get('status') == 'success':
                return jsonify({
                    'status': 'success',
                    'message_id': result.get('message_id'),
                    'message': result.get('message', 'Готово')
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': result.get('message', 'Ошибка при синхронной обработке') if isinstance(result, dict) else 'Ошибка при синхронной обработке'
                }), 500
        except Exception as e2:
            current_app.logger.error(f"Ошибка при синхронной обработке сообщения: {e2}")
            return jsonify({
                'status': 'error',
                'message': f'Ошибка при обработке сообщения: {str(e2)}'
            }), 500


@bp.route('/api/task_status/<task_id>')
@login_required
def check_task_status(task_id):
    """Проверка статуса задачи обработки сообщения"""
    task = process_chat_message.AsyncResult(task_id)
    current_app.logger.info(f"[CHAT] task_status {task_id} state={task.state}")
    
    if task.state == 'PENDING':
        # Если результат уже сохранен в БД — добираем его
        message_id = request.args.get('message_id', type=int)
        if message_id:
            try:
                db_message = Message.query.get(message_id)
                if db_message:
                    assistant_msg = Message.query.filter(
                        Message.conversation_id == db_message.conversation_id,
                        Message.role == 'assistant',
                        Message.created_at >= db_message.created_at
                    ).order_by(Message.created_at.desc()).first()
                    if assistant_msg:
                        current_app.logger.info(f"[CHAT] PENDING fallback fetched msg_id={assistant_msg.id}")
                        return jsonify({'status': 'success', 'message': assistant_msg.content, 'message_id': assistant_msg.id})

                    # Если воркер недоступен/задержка — выполняем обработку синхронно как аварийный фоллбек
                    # Это устраняет зависание на "Помощник печатает..." без Celery
                    try:
                        result = process_chat_message_impl(
                            conversation_id=db_message.conversation_id,
                            message_id=db_message.id,
                            template_id=None
                        )
                        if isinstance(result, dict) and result.get('status') == 'success':
                            current_app.logger.info(f"[CHAT] PENDING sync processed msg_id={result.get('message_id')}")
                            return jsonify({
                                'status': 'success',
                                'message': result.get('message'),
                                'message_id': result.get('message_id')
                            })
                    except Exception as e2:
                        current_app.logger.warning(f"Синхронный фоллбек из статуса PENDING не удался: {e2}")
            except Exception as e:
                current_app.logger.debug(f"Fallback по БД не удался: {e}")

        response = {
            'status': 'pending',
            'progress': 0,
            'message': 'Задача ожидает выполнения...'
        }
    elif task.state == 'PROGRESS':
        response = task.info
        response['status'] = 'progress'
    elif task.state == 'SUCCESS':
        # Если брокер не возвращает payload, пробуем достать ответ из БД по message_id
        result = task.result if isinstance(task.result, dict) else {}
        message = result.get('message')
        message_id = result.get('message_id') or request.args.get('message_id', type=int)
        if not message and message_id:
            try:
                db_message = Message.query.get(message_id)
                if db_message and db_message.role == 'assistant':
                    message = db_message.content
            except Exception as e:
                current_app.logger.warning(f"Не удалось загрузить сообщение из БД: {e}")

        response = {
            'status': 'success',
            'message': message or 'Готово',
            'message_id': message_id,
            'search_results_count': result.get('search_results_count', 0),
            'tokens_used': result.get('tokens_used', 0),
            'processing_time': result.get('processing_time', 0)
        }
    elif task.state == 'FAILURE':
        response = {
            'status': 'error',
            'message': str(task.info) if task.info else 'Неизвестная ошибка'
        }
    else:
        response = {
            'status': 'unknown',
            'message': f'Неизвестный статус: {task.state}'
        }
    
    return jsonify(response)


@bp.route('/api/diagnostics/fastapi')
@login_required
def fastapi_diagnostics():
    """Диагностика доступности FastAPI из веб‑процесса Flask."""
    try:
        base_url = current_app.config.get('FASTAPI_URL', 'http://localhost:8002')
        info = {'fastapi_url': base_url}
        # /llm/models
        try:
            r = requests.get(f"{base_url}/llm/models", timeout=5)
            info['llm_models_status'] = r.status_code
            info['llm_models_preview'] = (r.text or '')[:200]
        except Exception as e:
            info['llm_models_error'] = str(e)
        # /search (пробный пустой вызов с безопасными данными)
        try:
            r2 = requests.post(f"{base_url}/search", json={
                'application_id': '0', 'query': 'ping', 'limit': 1
            }, timeout=5)
            info['search_status'] = r2.status_code
            info['search_preview'] = (r2.text or '')[:200]
        except Exception as e:
            info['search_error'] = str(e)
        return jsonify({'status': 'ok', 'info': info})
    except Exception as e:
        current_app.logger.error(f"[CHAT] fastapi_diagnostics error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/api/conversation/<int:conversation_id>/messages')
@login_required
def get_messages(conversation_id):
    """Получить сообщения диалога"""
    conversation = Conversation.query.get_or_404(conversation_id)
    
    if conversation.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Нет доступа'}), 403
    
    limit = request.args.get('limit', 50, type=int)
    messages = conversation.get_last_messages(limit)
    
    return jsonify({
        'status': 'success',
        'messages': [msg.to_dict() for msg in messages]
    })


@bp.route('/api/message/<int:message_id>/rate', methods=['POST'])
@login_required
def rate_message(message_id):
    """Оценить сообщение помощника"""
    message = Message.query.get_or_404(message_id)
    
    # Проверяем доступ
    if message.conversation.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Нет доступа'}), 403
    
    data = request.get_json()
    rating = data.get('rating')
    feedback = data.get('feedback')
    
    if rating:
        message.rating = rating
        # Обновляем рейтинг помощника
        message.conversation.assistant.update_rating(rating)
    
    if feedback:
        message.feedback = feedback
    
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Оценка сохранена'})


@bp.route('/api/conversation/<int:conversation_id>/clear', methods=['POST'])
@login_required
def clear_conversation(conversation_id):
    """Очистить историю диалога"""
    conversation = Conversation.query.get_or_404(conversation_id)
    
    if conversation.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Нет доступа'}), 403
    
    try:
        # Удаляем все сообщения
        Message.query.filter_by(conversation_id=conversation_id).delete()
        conversation.message_count = 0
        conversation.total_tokens = 0
        db.session.commit()
        current_app.logger.info(f"[CHAT] conversation {conversation_id} cleared")
        return jsonify({'status': 'success', 'message': 'История очищена'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[CHAT] clear error: {e}")
        return jsonify({'status': 'error', 'message': 'Не удалось очистить историю'}), 500