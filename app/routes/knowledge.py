"""管理员维护公开来源设备处理参考资料。"""

from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.models import KnowledgeEntry
from app.services.access_control import current_user, login_required, permission_required
from app.services.knowledge_matcher import SUBSYSTEM_KEYWORDS


knowledge_bp = Blueprint("knowledge", __name__)

EQUIPMENT_CATEGORIES = ("CNC_MACHINING", "CNC_CONTROL", "INJECTION_MOLDING", "CONVEYOR", "AIR_COMPRESSOR", "VARIABLE_FREQUENCY_DRIVE")
FAULT_CATEGORIES = ("ELECTRICAL_CONTROL", "MECHANICAL", "THERMAL_COOLING", "SENSOR_COMMUNICATION", "OTHER_UNKNOWN")
FORM_FIELDS = (
    "brand", "equipment_model", "controller_system", "software_version", "equipment_category", "subsystem",
    "title", "symptoms", "alarm_code", "fault_category", "summary", "source_name", "source_page", "source_url",
)


def _values(entry=None):
    return {field: (getattr(entry, field, "") or "") if entry else request.form.get(field, "").strip() for field in FORM_FIELDS}


def _validate(values):
    required = set(FORM_FIELDS) - {"alarm_code"}
    missing = [field for field in required if not values[field]]
    if missing:
        return "请补全除报警代码外的所有字段。"
    if values["equipment_category"] not in EQUIPMENT_CATEGORIES:
        return "设备类别不符合平台范围。"
    if values["subsystem"] not in SUBSYSTEM_KEYWORDS:
        return "请选择对应的设备子系统。"
    if values["fault_category"] not in FAULT_CATEGORIES:
        return "故障类别不符合平台范围。"
    if urlparse(values["source_url"]).scheme not in {"http", "https"}:
        return "资料链接必须是有效的 http 或 https 地址。"
    return None


def _next_knowledge_id():
    prefix = f"KB-MANUAL-{datetime.now():%Y%m%d}-"
    count = KnowledgeEntry.query.filter(KnowledgeEntry.knowledge_id.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:03d}"


def _apply_values(entry, values):
    for field, value in values.items():
        setattr(entry, field, value or None if field == "alarm_code" else value)


@knowledge_bp.get("/knowledge")
@login_required
@permission_required("user:manage")
def list_entries():
    entries = KnowledgeEntry.query.order_by(KnowledgeEntry.is_active.desc(), KnowledgeEntry.updated_at.desc()).all()
    return render_template(
        "knowledge/list.html", entries=entries, values=_values(), equipment_categories=EQUIPMENT_CATEGORIES,
        subsystems=tuple(SUBSYSTEM_KEYWORDS), fault_categories=FAULT_CATEGORIES,
    )


@knowledge_bp.post("/knowledge")
@login_required
@permission_required("user:manage")
def create_entry():
    values = _values()
    error = _validate(values)
    if error:
        flash(error)
        return render_template("knowledge/list.html", entries=KnowledgeEntry.query.all(), values=values,
                               equipment_categories=EQUIPMENT_CATEGORIES, subsystems=tuple(SUBSYSTEM_KEYWORDS), fault_categories=FAULT_CATEGORIES), 400
    entry = KnowledgeEntry(knowledge_id=_next_knowledge_id(), created_by=current_user().username)
    _apply_values(entry, values)
    db.session.add(entry)
    db.session.commit()
    flash("公开知识资料已加入知识库，可用于后续报修参考。")
    return redirect(url_for("knowledge.list_entries"))


@knowledge_bp.route("/knowledge/<knowledge_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("user:manage")
def edit_entry(knowledge_id):
    entry = db.session.get(KnowledgeEntry, knowledge_id)
    if entry is None:
        return "未找到知识条目。", 404
    if request.method == "POST":
        values = _values()
        error = _validate(values)
        if not error:
            _apply_values(entry, values)
            db.session.commit()
            flash("知识资料已更新。")
            return redirect(url_for("knowledge.list_entries"))
        flash(error)
    return render_template("knowledge/edit.html", entry=entry, values=_values(entry) if request.method == "GET" else _values(),
                           equipment_categories=EQUIPMENT_CATEGORIES, subsystems=tuple(SUBSYSTEM_KEYWORDS), fault_categories=FAULT_CATEGORIES)


@knowledge_bp.post("/knowledge/<knowledge_id>/status")
@login_required
@permission_required("user:manage")
def toggle_status(knowledge_id):
    entry = db.session.get(KnowledgeEntry, knowledge_id)
    if entry is None:
        return "未找到知识条目。", 404
    entry.is_active = not entry.is_active
    db.session.commit()
    flash("知识资料已启用。" if entry.is_active else "知识资料已停用，不再参与后续报修参考。")
    return redirect(url_for("knowledge.list_entries"))
