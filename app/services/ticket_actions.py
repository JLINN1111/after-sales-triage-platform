"""客服操作、状态流转与留痕服务。

规则以《报修字段与标签定义.md》4.1 节为准。服务只修改人工确认
字段和处理状态；系统的原始分诊字段保持只读。
"""

from datetime import datetime
from typing import Any, Mapping

from app.models import Ticket, TicketAction


STATES = {"NEW", "NEED_INFO", "HUMAN_REVIEW", "CONFIRMED", "CLOSED"}
ACTIONS = {"FOLLOW_UP", "HANDOFF", "CONFIRM", "EDIT", "CLOSE"}
CATEGORIES = {
    "ELECTRICAL_CONTROL", "MECHANICAL", "THERMAL_COOLING",
    "SENSOR_COMMUNICATION", "OTHER_UNKNOWN",
}
PRIORITIES = {"NORMAL", "HIGH", "URGENT"}


def initial_action_status(triage_result: Mapping[str, Any]) -> str:
    """根据已完成的系统分诊结果选择客服处理入口。"""

    if triage_result.get("recommend_human"):
        return "HUMAN_REVIEW"
    if triage_result.get("missing_fields"):
        return "NEED_INFO"
    return "NEW"


def _text(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field, "")
    return value.strip() if isinstance(value, str) else ""


def _require(data: Mapping[str, Any], field: str, message: str) -> str:
    value = _text(data, field)
    if not value:
        raise ValueError(message)
    return value


def _require_status(ticket: Ticket, allowed: set[str], action: str) -> None:
    if ticket.action_status not in allowed:
        raise ValueError(f"当前状态不允许执行{action}操作。")


def _confirmation_values(ticket: Ticket, data: Mapping[str, Any], *, require_both: bool) -> dict[str, str]:
    category = _text(data, "confirmed_category")
    priority = _text(data, "confirmed_priority")
    if require_both and (not category or not priority):
        raise ValueError("确认分诊时必须填写确认类别和确认优先级。")
    if category and category not in CATEGORIES:
        raise ValueError("确认类别取值无效。")
    if priority and priority not in PRIORITIES:
        raise ValueError("确认优先级取值无效。")
    return {
        "confirmed_category": category or ticket.confirmed_category,
        "confirmed_priority": priority or ticket.confirmed_priority,
    }


def needs_handoff_before_close(ticket: Ticket) -> bool:
    return ticket.safety_risk in {"YES", "UNKNOWN"} or ticket.shutdown in {"YES", "UNKNOWN"}


def apply_ticket_action(ticket: Ticket, data: Mapping[str, Any]) -> TicketAction:
    """校验并应用单次客服操作，返回待提交的操作日志。"""

    action_type = _text(data, "action_type")
    if action_type not in ACTIONS:
        raise ValueError("操作类型无效。")
    action_by = _require(data, "action_by", "必须填写操作人标识。")
    note = _text(data, "action_note")
    before = ticket.action_status
    old_values = {
        "confirmed_category": ticket.confirmed_category,
        "confirmed_priority": ticket.confirmed_priority,
        "customer_follow_up": ticket.customer_follow_up,
    }
    new_values = dict(old_values)

    if action_type == "FOLLOW_UP":
        _require_status(ticket, {"NEW", "NEED_INFO", "HUMAN_REVIEW"}, "补问")
        follow_up = _require(data, "customer_follow_up", "补问时必须填写补问内容。")
        new_values["customer_follow_up"] = follow_up
        after = "NEED_INFO"
    elif action_type == "HANDOFF":
        _require_status(ticket, {"NEW", "NEED_INFO", "HUMAN_REVIEW", "CONFIRMED"}, "转人工")
        _require(data, "action_note", "转人工时必须填写原因。")
        after = "HUMAN_REVIEW"
    elif action_type == "CONFIRM":
        _require_status(ticket, {"NEW", "NEED_INFO", "HUMAN_REVIEW"}, "确认")
        new_values.update(_confirmation_values(ticket, data, require_both=True))
        differs = (
            new_values["confirmed_category"] != ticket.predicted_category
            or new_values["confirmed_priority"] != ticket.priority
        )
        if differs and not note:
            raise ValueError("确认结果与系统建议不一致时必须填写原因。")
        after = "CONFIRMED"
    elif action_type == "EDIT":
        _require_status(ticket, {"CONFIRMED"}, "修订")
        _require(data, "action_note", "修订时必须填写原因。")
        new_values.update(_confirmation_values(ticket, data, require_both=False))
        if new_values == old_values:
            raise ValueError("修订时至少需要修改一项人工确认结果。")
        after = "CONFIRMED"
    else:  # CLOSE
        _require_status(ticket, {"CONFIRMED"}, "关闭")
        _require(data, "action_note", "关闭工单时必须填写说明。")
        if needs_handoff_before_close(ticket) and not any(
            action.action_type == "HANDOFF" for action in ticket.actions
        ):
            raise ValueError("安全、停机或状态未知工单关闭前必须先记录转人工处理。")
        after = "CLOSED"

    ticket.confirmed_category = new_values["confirmed_category"]
    ticket.confirmed_priority = new_values["confirmed_priority"]
    ticket.customer_follow_up = new_values["customer_follow_up"]
    ticket.action_status = after
    ticket.action_type = action_type
    ticket.action_note = note or None
    ticket.action_by = action_by
    ticket.action_at = datetime.now()

    return TicketAction(
        ticket=ticket,
        action_type=action_type,
        state_before=before,
        state_after=after,
        old_values=old_values,
        new_values=new_values,
        action_note=note or None,
        action_by=action_by,
        action_at=ticket.action_at,
    )
