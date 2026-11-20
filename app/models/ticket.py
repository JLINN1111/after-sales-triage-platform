from app import db
from datetime import datetime


class Ticket(db.Model):
    __tablename__ = "tickets"

    # 一、报修人提交字段
    ticket_id = db.Column(db.String(32), primary_key=True)
    equipment_type = db.Column(db.String(32), nullable=False)
    equipment_model = db.Column(db.String(64))
    equipment_code = db.Column(db.String(64))
    description = db.Column(db.Text, nullable=False)
    occurred_at = db.Column(db.DateTime)
    operating_state = db.Column(db.String(16), default="UNKNOWN")
    shutdown = db.Column(db.String(8), default="UNKNOWN", nullable=False)
    safety_risk = db.Column(db.String(8), default="UNKNOWN", nullable=False)
    alarm_code_status = db.Column(db.String(16), default="UNKNOWN", nullable=False)
    alarm_code = db.Column(db.String(32))
    symptom_tags = db.Column(db.JSON)
    submitter_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # 二、系统分诊输出字段
    predicted_category = db.Column(db.String(32))
    category_confidence = db.Column(db.Float)
    priority = db.Column(db.String(16))
    evidence_codes = db.Column(db.JSON)
    missing_fields = db.Column(db.JSON)
    follow_up_questions = db.Column(db.JSON)
    knowledge_ids = db.Column(db.JSON)
    reference_knowledge_ids = db.Column(db.JSON)
    knowledge_match_level = db.Column(db.String(16))
    recommend_human = db.Column(db.Boolean, default=False)
    handoff_reasons = db.Column(db.JSON)
    model_version = db.Column(db.String(32))
    triaged_at = db.Column(db.DateTime)

    # 三、客服确认与处理字段
    confirmed_category = db.Column(db.String(32))
    confirmed_priority = db.Column(db.String(16))
    customer_follow_up = db.Column(db.Text)
    action_status = db.Column(db.String(16), default="NEW")
    action_type = db.Column(db.String(16))
    action_note = db.Column(db.Text)
    action_at = db.Column(db.DateTime)
    action_by = db.Column(db.String(32))

    actions = db.relationship(
        "TicketAction",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketAction.action_at",
    )


class TicketAction(db.Model):
    """客服对工单的单次操作留痕，不覆盖系统原始分诊结果。"""

    __tablename__ = "ticket_actions"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(32), db.ForeignKey("tickets.ticket_id"), nullable=False, index=True)
    action_type = db.Column(db.String(16), nullable=False)
    state_before = db.Column(db.String(16), nullable=False)
    state_after = db.Column(db.String(16), nullable=False)
    old_values = db.Column(db.JSON, nullable=False, default=dict)
    new_values = db.Column(db.JSON, nullable=False, default=dict)
    action_note = db.Column(db.Text)
    action_by = db.Column(db.String(32), nullable=False)
    action_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    ticket = db.relationship("Ticket", back_populates="actions")
