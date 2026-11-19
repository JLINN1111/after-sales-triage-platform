"""报修工单路由：提交表单、工单列表、工单详情。

服务端校验遵循《报修字段与标签定义.md》V1 约定：
- 必填项不得为空；描述不少于 10 字。
- shutdown / safety_risk / alarm_code_status 只允许枚举值，默认 UNKNOWN。
- alarm_code_status=PRESENT 时 alarm_code 必填。
- ticket_id 由系统生成，不接受用户输入。
"""

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.models import Ticket

tickets_bp = Blueprint("tickets", __name__)

TRI_STATE = {"YES", "NO", "UNKNOWN"}
ALARM_STATUS = {"PRESENT", "NONE", "UNKNOWN"}
OPERATING_STATE = {"STARTING", "RUNNING", "STANDBY", "STOPPED", "UNKNOWN"}
EQUIPMENT_TYPE = {"CNC", "INJECTION", "CONVEYOR", "AIR_COMPRESSOR", "VFD", "OTHER"}

# 表单需要回显的字段（系统生成字段不在此列）
FORM_FIELDS = [
    "equipment_type", "equipment_model", "equipment_code", "description",
    "occurred_at", "operating_state", "shutdown", "safety_risk",
    "alarm_code_status", "alarm_code", "submitter_note",
]


def default_form():
    return {
        "equipment_type": "OTHER",
        "equipment_model": "",
        "equipment_code": "",
        "description": "",
        "occurred_at": "",
        "operating_state": "UNKNOWN",
        "shutdown": "UNKNOWN",
        "safety_risk": "UNKNOWN",
        "alarm_code_status": "UNKNOWN",
        "alarm_code": "",
        "submitter_note": "",
    }


def generate_ticket_id():
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"T{today}-"
    count = Ticket.query.filter(Ticket.ticket_id.like(prefix + "%")).count()
    return f"{prefix}{count + 1:04d}"


def validate(form):
    errors = []

    if form["equipment_type"] not in EQUIPMENT_TYPE:
        errors.append("设备类型取值无效。")
    if len(form["description"].strip()) < 10:
        errors.append("故障现象描述不能为空，且不少于 10 个字。")
    if form["shutdown"] not in TRI_STATE:
        errors.append("设备是否停机只能是 是/否/未知。")
    if form["safety_risk"] not in TRI_STATE:
        errors.append("安全风险只能是 是/否/未知。")
    if form["alarm_code_status"] not in ALARM_STATUS:
        errors.append("报警代码状态取值无效。")
    if form["operating_state"] not in OPERATING_STATE:
        errors.append("运行状态取值无效。")
    if form["alarm_code_status"] == "PRESENT" and not form["alarm_code"].strip():
        errors.append("报警代码状态为“有代码”时，必须填写报警代码。")

    return errors


@tickets_bp.route("/tickets/new", methods=["GET", "POST"])
def new_ticket():
    if request.method == "GET":
        return render_template("tickets/form.html", form=default_form(), errors=[])

    form = {field: request.form.get(field, "") for field in FORM_FIELDS}
    errors = validate(form)
    if errors:
        return render_template("tickets/form.html", form=form, errors=errors), 400

    ticket = Ticket(
        ticket_id=generate_ticket_id(),
        equipment_type=form["equipment_type"],
        equipment_model=form["equipment_model"].strip() or None,
        equipment_code=form["equipment_code"].strip() or None,
        description=form["description"].strip(),
        occurred_at=form["occurred_at"].strip() or None,
        operating_state=form["operating_state"],
        shutdown=form["shutdown"],
        safety_risk=form["safety_risk"],
        alarm_code_status=form["alarm_code_status"],
        alarm_code=form["alarm_code"].strip() or None,
        submitter_note=form["submitter_note"].strip() or None,
        action_status="NEW",
    )
    db.session.add(ticket)
    db.session.commit()
    flash(f"报修提交成功，工单编号：{ticket.ticket_id}")
    return redirect(url_for("tickets.list_tickets"))


@tickets_bp.route("/tickets")
def list_tickets():
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    return render_template("tickets/list.html", tickets=tickets)


@tickets_bp.route("/tickets/<ticket_id>")
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    return render_template("tickets/detail.html", ticket=ticket)
