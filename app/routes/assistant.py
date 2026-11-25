"""报修信息采集对话接口：只生成追问与字段建议，不执行工单操作。"""

from flask import Blueprint, current_app, jsonify, request

from app import db
from app.models import ConversationMessage, ConversationSession, Ticket
from app.services.access_control import can, can_access_ticket, current_user, login_required, permission_required
from app.services.assistant_service import AssistantUnavailable, generate_turn, mark_suggestion_applied


assistant_bp = Blueprint("assistant", __name__)


def _owner():
    return current_user().username if current_user() else "SYSTEM"


def _payload():
    return request.get_json(silent=True) or {}


def _session_or_404(session_id):
    session = db.session.get(ConversationSession, session_id)
    if session is None:
        return None, (jsonify({"error": "未找到对话会话。"}), 404)
    if session.ticket_id:
        ticket = db.session.get(Ticket, session.ticket_id)
        if ticket is None or not can_access_ticket(ticket):
            return None, (jsonify({"error": "无权访问该对话。"}), 403)
        if ticket.action_status != "NEED_INFO" or not can("ticket:supplement"):
            return None, (jsonify({"error": "当前工单不允许继续补充对话。"}), 409)
    elif session.owner_username != _owner():
        return None, (jsonify({"error": "无权访问该对话。"}), 403)
    return session, None


@assistant_bp.post("/assistant/sessions")
@login_required
@permission_required("ticket:submit")
def create_draft_session():
    session = ConversationSession(owner_username=_owner())
    db.session.add(session)
    db.session.commit()
    return jsonify({"session_id": session.id})


@assistant_bp.post("/assistant/tickets/<ticket_id>/session")
@login_required
@permission_required("ticket:supplement")
def create_ticket_session(ticket_id):
    ticket = db.get_or_404(Ticket, ticket_id)
    if not can_access_ticket(ticket):
        return jsonify({"error": "无权访问该工单。"}), 403
    if ticket.action_status != "NEED_INFO":
        return jsonify({"error": "仅待补充信息的工单可使用该对话。"}), 409
    session = ConversationSession.query.filter_by(ticket_id=ticket_id, owner_username=_owner(), status="OPEN").first()
    if session is None:
        session = ConversationSession(ticket_id=ticket_id, owner_username=_owner())
        db.session.add(session)
        db.session.commit()
    return jsonify({"session_id": session.id})


@assistant_bp.post("/assistant/sessions/<session_id>/messages")
@login_required
def send_message(session_id):
    session, error = _session_or_404(session_id)
    if error:
        return error
    data = _payload()
    user_text = str(data.get("message", ""))
    form_context = data.get("form_context") if isinstance(data.get("form_context"), dict) else {}
    if session.ticket_id:
        ticket = db.session.get(Ticket, session.ticket_id)
        form_context = {
            "equipment_type": ticket.equipment_type, "equipment_model": ticket.equipment_model,
            "occurred_at": ticket.occurred_at, "operating_state": ticket.operating_state,
            "shutdown": ticket.shutdown, "safety_risk": ticket.safety_risk,
            "alarm_code_status": ticket.alarm_code_status, "alarm_code": ticket.alarm_code,
            "submitter_note": ticket.submitter_note, "description": ticket.description,
            "customer_follow_up": ticket.customer_follow_up,
        }
    user_message = ConversationMessage(session=session, speaker="USER", content=user_text)
    db.session.add(user_message)
    db.session.flush()
    try:
        turn, provider, model = generate_turn(session, user_text, form_context)
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
    except AssistantUnavailable as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 503
    assistant_message = ConversationMessage(
        session=session, speaker="ASSISTANT", content=turn["reply"], suggested_fields=turn["field_suggestions"],
        needs_confirmation=turn["needs_confirmation"], urgent_risk_hint=turn["urgent_risk_hint"], provider=provider, model_name=model,
    )
    db.session.add(assistant_message)
    db.session.commit()
    return jsonify({"message_id": assistant_message.id, **turn})


@assistant_bp.post("/assistant/sessions/<session_id>/apply")
@login_required
def apply_suggestion(session_id):
    session, error = _session_or_404(session_id)
    if error:
        return error
    data = _payload()
    message = db.session.get(ConversationMessage, data.get("message_id"))
    if message is None or message.session_id != session.id or message.speaker != "ASSISTANT":
        return jsonify({"error": "未找到可采用的字段建议。"}), 404
    selected = data.get("fields") if isinstance(data.get("fields"), list) else []
    applied = mark_suggestion_applied(message, [str(field) for field in selected])
    db.session.commit()
    return jsonify({"applied_fields": applied})
