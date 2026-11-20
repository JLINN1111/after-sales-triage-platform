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
from app.services.knowledge_matcher import load_knowledge, match_knowledge
from app.services.triage_service import triage_ticket

tickets_bp = Blueprint("tickets", __name__)

# 内部代码 → 中文展示（依据《展示词映射.md》，仅用于显示，不参与判断）
DISPLAY = {
    "category": {
        "ELECTRICAL_CONTROL": "电气或控制异常",
        "MECHANICAL": "机械或传动异常",
        "THERMAL_COOLING": "温度或冷却异常",
        "SENSOR_COMMUNICATION": "传感或通信异常",
        "OTHER_UNKNOWN": "其他或暂无法判断",
    },
    "priority": {"NORMAL": "普通", "HIGH": "优先处理", "URGENT": "紧急处理"},
    "match": {
        "EXACT": ("已匹配对应设备知识", "已找到与当前设备信息相符的参考资料。"),
        "REFERENCE": ("找到参考信息，需人工核对", "找到同类设备参考资料，请人工核对型号和控制系统。"),
        "NONE": ("暂未找到适用知识", "暂未找到对应资料，请补充设备信息或转人工处理。"),
    },
    "equipment": {
        "CNC": "数控机床/加工设备", "INJECTION": "注塑机", "CONVEYOR": "输送线/传送带",
        "AIR_COMPRESSOR": "空压机", "VFD": "电机控制箱/变频器", "OTHER": "其他设备/不清楚",
    },
    "tri": {"YES": "是", "NO": "否", "UNKNOWN": "未知"},
    "operating": {
        "STARTING": "启动中", "RUNNING": "运行中", "STANDBY": "待机",
        "STOPPED": "停机", "UNKNOWN": "未知",
    },
    "alarm_status": {"PRESENT": "有报警代码", "NONE": "无报警", "UNKNOWN": "不清楚"},
    "category_code": {
        "ELECTRICAL_CONTROL": "电气或控制异常", "MECHANICAL": "机械或传动异常",
        "THERMAL_COOLING": "温度或冷却异常", "SENSOR_COMMUNICATION": "传感或通信异常",
        "OTHER_UNKNOWN": "其他或暂无法判断",
    },
    "evidence": {
        "RULE-SAFETY-YES": "存在安全风险，需人工处理",
        "RULE-SHUTDOWN-YES": "设备已停机，需优先处理",
        "RULE-SAFETY-UNKNOWN": "请先确认现场是否存在安全风险",
        "RULE-SHUTDOWN-UNKNOWN": "请确认设备目前是否停机",
        "RULE-CATEGORY-NO-DIRECT-EVIDENCE": "现象信息不足，暂无法判断故障类别",
        "RULE-CATEGORY-CONFLICT": "现象可能涉及多个方向，需人工核对",
        "RULE-KNOWLEDGE-REFERENCE": "仅找到参考资料，不能作为确定结论",
        "RULE-KNOWLEDGE-NONE": "未找到适用知识，建议补充设备信息",
    },
}


def translate_evidence(codes):
    """把判断依据代码翻译成中文；含关键词后缀的按前缀匹配。"""
    out = []
    for code in codes or []:
        if code in DISPLAY["evidence"]:
            out.append(DISPLAY["evidence"][code])
            continue
        base, _, keyword = code.partition(":")
        if base.startswith("RULE-CATEGORY-") and keyword:
            category = base.split("RULE-CATEGORY-", 1)[1]
            zh = DISPLAY["category_code"].get(category, category)
            out.append(f"命中“{keyword}”，判为{zh}")
            continue
        out.append(DISPLAY["evidence"].get(base) or code)
    return out


def knowledge_details(ids, fallback_ids=None):
    """按知识编号取出标题与处置方向，供页面展示。"""
    if not ids and not fallback_ids:
        return []
    index = {row["knowledge_id"]: row for row in load_knowledge()}
    picked = ids or fallback_ids or []
    return [
        {
            "id": kid,
            "title": index[kid]["title"],
            "summary": index[kid]["summary"],
            "source": index[kid]["source_name"],
        }
        for kid in picked if kid in index
    ]

# 统一分诊结果写回工单的字段（triaged_at 是字符串，需转 datetime）
RESULT_FIELDS = [
    "symptom_tags", "predicted_category", "category_confidence", "priority",
    "evidence_codes", "missing_fields", "follow_up_questions",
    "knowledge_ids", "reference_knowledge_ids", "knowledge_match_level",
    "recommend_human", "handoff_reasons", "model_version", "triaged_at",
]


def apply_triage(ticket):
    """调用成员1的统一分诊入口（规则 + 知识匹配），把结果写回工单。"""
    result = triage_ticket(ticket, match_knowledge)
    for field in RESULT_FIELDS:
        if field not in result:
            continue
        value = result[field]
        if field == "triaged_at" and value:
            value = datetime.fromisoformat(value)
        setattr(ticket, field, value)
    return result

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
    apply_triage(ticket)
    db.session.add(ticket)
    db.session.commit()
    flash(f"报修提交成功，工单编号：{ticket.ticket_id}")
    return redirect(url_for("tickets.list_tickets"))


@tickets_bp.route("/tickets")
def list_tickets():
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    return render_template("tickets/list.html", tickets=tickets)


@tickets_bp.route("/tickets/<ticket_id>/delete", methods=["POST"])
def delete_ticket(ticket_id):
    """删除一张工单；仅接受 POST，避免误操作与搜索引擎抓取触发。"""
    ticket = Ticket.query.get_or_404(ticket_id)
    db.session.delete(ticket)
    db.session.commit()
    flash(f"工单 {ticket_id} 已删除。")
    return redirect(url_for("tickets.list_tickets"))


@tickets_bp.route("/tickets/<ticket_id>")
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    match_level = ticket.knowledge_match_level
    return render_template(
        "tickets/detail.html",
        ticket=ticket,
        display=DISPLAY,
        category_zh=DISPLAY["category"].get(ticket.predicted_category, "待分诊"),
        priority_zh=DISPLAY["priority"].get(ticket.priority, "待分诊"),
        match_zh=DISPLAY["match"].get(match_level),
        match_pending=(match_level is None),
        exact_items=knowledge_details(ticket.knowledge_ids),
        reference_items=knowledge_details(ticket.reference_knowledge_ids),
        evidence_zh=translate_evidence(ticket.evidence_codes),
        handoff_zh=[DISPLAY["evidence"].get(r, r) for r in (ticket.handoff_reasons or [])],
    )
