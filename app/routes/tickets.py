"""报修工单路由：提交表单、工单列表、工单详情。

服务端校验遵循《报修字段与标签定义.md》V1 约定：
- 必填项不得为空；描述不少于 10 字。
- shutdown / safety_risk / alarm_code_status 只允许枚举值，默认 UNKNOWN。
- alarm_code_status=PRESENT 时 alarm_code 必填。
- ticket_id 由系统生成，不接受用户输入。
"""

from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

from app import db
from app.models import ConversationSession, Ticket, TicketAction, TicketAttachment, TicketOutcome
from app.services.attachments import prepare_attachments, save_attachments
from app.services.knowledge_matcher import load_knowledge, match_knowledge
from app.services.ticket_actions import apply_ticket_action, initial_action_status, needs_handoff_before_close
from app.services.triage_service import triage_ticket
from app.services.access_control import action_permission_required, can_access_ticket, current_user, login_required, permission_required

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
        "NONE": ("暂未找到适用知识", "暂未找到对应资料，请补充设备信息或由售后处理。"),
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
    "action": {
        "FOLLOW_UP": "补问信息", "HANDOFF": "转现场处理", "CONFIRM": "确认分诊",
        "SUPPLEMENT": "录入客户补充信息", "EDIT": "修订确认结果", "CLOSE": "关闭工单",
    },
    "action_status": {
        "NEW": "待售后处理", "NEED_INFO": "待补充信息", "HUMAN_REVIEW": "售后处理中",
        "CONFIRMED": "处理中", "CLOSED": "已完成",
    },
    "category_code": {
        "ELECTRICAL_CONTROL": "电气或控制异常", "MECHANICAL": "机械或传动异常",
        "THERMAL_COOLING": "温度或冷却异常", "SENSOR_COMMUNICATION": "传感或通信异常",
        "OTHER_UNKNOWN": "其他或暂无法判断",
    },
    "evidence": {
        "RULE-SAFETY-YES": "存在安全风险，需售后处理",
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
    """将内部判断依据转换为业务可读说明，不向页面回退输出内部代码。"""

    out = []
    conflict_seen = False
    category_prefix = "RULE-CATEGORY-"
    conflict_prefix = "RULE-CATEGORY-CONFLICT:"

    for code in codes or []:
        if not isinstance(code, str):
            continue
        if code in DISPLAY["evidence"]:
            out.append(DISPLAY["evidence"][code])
            continue
        if code.startswith(conflict_prefix):
            # 冲突明细中携带的是内部类别代码，只保留可供售后判断的业务结论。
            if not conflict_seen:
                out.append("描述中存在多个异常方向的线索，需人工核对")
                conflict_seen = True
            continue
        if code.startswith(category_prefix) and ":" in code:
            category_and_keyword = code[len(category_prefix):]
            category, keyword = category_and_keyword.split(":", 1)
            category_zh = DISPLAY["category_code"].get(category)
            if category_zh and keyword:
                out.append(f"描述中提及“{keyword}”，与{category_zh}相关")

    return list(dict.fromkeys(out))


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


def action_detail(action):
    """把操作留痕中的结构化前后值转换为客服可读的说明。"""

    values = action.new_values or {}
    if action.action_type == "FOLLOW_UP":
        return values.get("customer_follow_up") or action.action_note or "-"
    if action.action_type == "SUPPLEMENT":
        fields = values.get("supplemental_fields", {})
        labels = {
            "equipment_model": "设备型号", "equipment_code": "设备编号",
            "operating_state": "运行状态", "shutdown": "是否停机",
            "safety_risk": "安全风险", "alarm_code_status": "报警代码状态",
            "alarm_code": "报警代码",
        }
        return "；".join(
            f"{labels[field]}：{DISPLAY['operating'].get(value, DISPLAY['tri'].get(value, DISPLAY['alarm_status'].get(value, value)))}"
            for field, value in fields.items() if field in labels
        ) or "-"
    if action.action_type in {"CONFIRM", "EDIT"}:
        parts = []
        if values.get("confirmed_category"):
            parts.append(f"确认类别：{DISPLAY['category'].get(values['confirmed_category'], values['confirmed_category'])}")
        if values.get("confirmed_priority"):
            parts.append(f"确认优先级：{DISPLAY['priority'].get(values['confirmed_priority'], values['confirmed_priority'])}")
        if action.action_note:
            parts.append(f"说明：{action.action_note}")
        return "；".join(parts) or "-"
    return action.action_note or "-"


def business_status(ticket):
    """将内部处理状态转换为报修业务人员可理解的进度。"""

    if ticket.action_status == "HUMAN_REVIEW" and any(action.action_type == "HANDOFF" for action in ticket.actions):
        return "已转现场处理"
    return DISPLAY["action_status"].get(ticket.action_status, "处理中")


def require_ticket_access(ticket):
    if not can_access_ticket(ticket):
        abort(403)

# 统一分诊结果写回工单的字段（triaged_at 是字符串，需转 datetime）
RESULT_FIELDS = [
    "symptom_tags", "predicted_category", "priority",
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
    ticket.action_status = initial_action_status(result)
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
@login_required
@permission_required("ticket:submit")
def new_ticket():
    if request.method == "GET":
        return render_template("tickets/form.html", form=default_form(), errors=[])

    form = {field: request.form.get(field, "") for field in FORM_FIELDS}
    errors = validate(form)
    try:
        prepared_attachments = prepare_attachments(
            request.files.getlist("attachments"),
            existing_count=0,
            max_count=current_app.config["MAX_ATTACHMENTS_PER_TICKET"],
            max_size=current_app.config["MAX_ATTACHMENT_SIZE"],
        )
    except ValueError as error:
        prepared_attachments = []
        errors.append(str(error))
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
        submitted_by=current_user().username if current_user() else "SYSTEM",
        action_status="NEW",
    )
    apply_triage(ticket)
    assistant_session_id = request.form.get("assistant_session_id", "")
    if assistant_session_id:
        session = db.session.get(ConversationSession, assistant_session_id)
        if session and session.ticket_id is None and session.owner_username == (current_user().username if current_user() else "SYSTEM"):
            session.ticket = ticket
    db.session.add(ticket)
    db.session.add_all(save_attachments(
        ticket,
        prepared_attachments,
        uploaded_by=current_user().username if current_user() else "SYSTEM",
        upload_dir=current_app.config["ATTACHMENT_UPLOAD_DIR"],
    ))
    db.session.commit()
    flash(f"报修提交成功，工单编号：{ticket.ticket_id}")
    return redirect(url_for("tickets.list_tickets"))


@tickets_bp.route("/tickets")
@login_required
@permission_required("ticket:view")
def list_tickets():
    user = current_user()
    query = Ticket.query
    if user and user.role == "AGENT":
        query = query.filter_by(submitted_by=user.username)
    tickets = query.order_by(Ticket.created_at.desc()).all()
    return render_template(
        "tickets/list.html", tickets=tickets, display=DISPLAY,
        page_title="我的报修" if user and user.role == "AGENT" else "工单列表",
        status_labels={ticket.ticket_id: business_status(ticket) for ticket in tickets},
    )


@tickets_bp.route("/tickets/<ticket_id>/delete", methods=["POST"])
@login_required
@permission_required("ticket:delete")
def delete_ticket(ticket_id):
    """删除一张工单；仅接受 POST，避免误操作与搜索引擎抓取触发。"""
    ticket = Ticket.query.get_or_404(ticket_id)
    require_ticket_access(ticket)
    db.session.delete(ticket)
    db.session.commit()
    flash(f"工单 {ticket_id} 已删除。")
    return redirect(url_for("tickets.list_tickets"))


@tickets_bp.route("/tickets/<ticket_id>/actions", methods=["POST"])
@login_required
@action_permission_required
def ticket_action(ticket_id):
    """接收客服补问、转人工、确认、修订或关闭操作并保存留痕。"""
    ticket = Ticket.query.get_or_404(ticket_id)
    require_ticket_access(ticket)
    payload = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    payload = dict(payload or {})
    if current_user() is not None:
        payload["action_by"] = current_user().username
    try:
        action = apply_ticket_action(ticket, payload or {})
    except ValueError as error:
        if request.is_json:
            return jsonify({"error": str(error)}), 400
        flash(str(error))
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.ticket_id))
    db.session.add(action)
    if action.action_type == "SUPPLEMENT":
        result = apply_triage(ticket)
        action.state_after = ticket.action_status
        action.new_values["retriaged_status"] = ticket.action_status
    db.session.commit()
    if request.is_json:
        return jsonify({
            "ticket_id": ticket.ticket_id,
            "action_type": action.action_type,
            "action_status": ticket.action_status,
            "action_id": action.id,
        }), 200
    flash("处理操作已保存。")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.ticket_id))


@tickets_bp.post("/tickets/<ticket_id>/attachments")
@login_required
@permission_required("ticket:attach")
def upload_attachment(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    require_ticket_access(ticket)
    try:
        prepared = prepare_attachments(
            request.files.getlist("attachments"),
            existing_count=len(ticket.attachments),
            max_count=current_app.config["MAX_ATTACHMENTS_PER_TICKET"],
            max_size=current_app.config["MAX_ATTACHMENT_SIZE"],
        )
        if not prepared:
            raise ValueError("请选择至少一个附件。")
        db.session.add_all(save_attachments(
            ticket,
            prepared,
            uploaded_by=current_user().username if current_user() else "SYSTEM",
            upload_dir=current_app.config["ATTACHMENT_UPLOAD_DIR"],
        ))
        db.session.commit()
        flash("附件已上传。")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.ticket_id))


@tickets_bp.get("/tickets/<ticket_id>/attachments/<int:attachment_id>/download")
@login_required
@permission_required("ticket:view")
def download_attachment(ticket_id, attachment_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    require_ticket_access(ticket)
    attachment = db.get_or_404(TicketAttachment, attachment_id)
    if attachment.ticket_id != ticket.ticket_id:
        abort(404)
    path = current_app.config["ATTACHMENT_UPLOAD_DIR"]
    if not (Path(path) / attachment.stored_name).is_file():
        abort(404)
    return send_from_directory(path, attachment.stored_name, as_attachment=True, download_name=attachment.original_name)


@tickets_bp.post("/tickets/<ticket_id>/outcomes")
@login_required
@permission_required("outcome:record")
def record_outcome(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    require_ticket_access(ticket)
    category = request.form.get("final_category", "")
    resolution_status = request.form.get("resolution_status", "")
    note = request.form.get("resolution_note", "").strip()
    if ticket.action_status not in {"CONFIRMED", "CLOSED"}:
        flash("请先完成复核确认后再记录处理结果。")
    elif category not in DISPLAY["category"]:
        flash("最终故障类别无效。")
    elif resolution_status not in {"RESOLVED", "PARTIALLY_RESOLVED", "UNRESOLVED", "UNKNOWN"}:
        flash("处理结果取值无效。")
    elif len(note) < 10:
        flash("请填写不少于 10 个字的处理结果依据。")
    else:
        db.session.add(TicketOutcome(
            ticket=ticket, final_category=category, resolution_status=resolution_status,
            resolution_note=note, recorded_by=current_user().username if current_user() else "SYSTEM",
        ))
        db.session.commit()
        flash("已记录处理结果；该记录不会自动用于训练模型。")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.ticket_id))


@tickets_bp.route("/tickets/<ticket_id>")
@login_required
@permission_required("ticket:view")
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    require_ticket_access(ticket)
    match_level = ticket.knowledge_match_level
    has_handoff = any(action.action_type == "HANDOFF" for action in ticket.actions)
    action_details = {action.id: action_detail(action) for action in ticket.actions}
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
        close_requires_handoff=needs_handoff_before_close(ticket),
        has_handoff=has_handoff,
        action_details=action_details,
        action_note_required=(ticket.action_status == "HUMAN_REVIEW" or needs_handoff_before_close(ticket)),
        resolution_status_zh={"RESOLVED": "已解决", "PARTIALLY_RESOLVED": "部分解决", "UNRESOLVED": "未解决", "UNKNOWN": "暂不确定"},
        status_label=business_status(ticket),
    )
