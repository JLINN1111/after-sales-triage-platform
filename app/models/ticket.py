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
