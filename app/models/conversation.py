"""对话式报修信息采集的会话、消息与字段采用记录。"""

from datetime import datetime
import uuid

from app import db


class ConversationSession(db.Model):
    __tablename__ = "conversation_sessions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = db.Column(db.String(32), db.ForeignKey("tickets.ticket_id"), index=True)
    owner_username = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="OPEN")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    ticket = db.relationship("Ticket", back_populates="conversations")
    messages = db.relationship(
        "ConversationMessage", back_populates="session", cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(db.Model):
    __tablename__ = "conversation_messages"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), db.ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    speaker = db.Column(db.String(16), nullable=False)  # USER / ASSISTANT
    content = db.Column(db.Text, nullable=False)
    suggested_fields = db.Column(db.JSON, nullable=False, default=dict)
    needs_confirmation = db.Column(db.JSON, nullable=False, default=list)
    urgent_risk_hint = db.Column(db.Boolean, nullable=False, default=False)
    provider = db.Column(db.String(32))
    model_name = db.Column(db.String(128))
    applied_fields = db.Column(db.JSON, nullable=False, default=dict)
    applied_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    session = db.relationship("ConversationSession", back_populates="messages")
