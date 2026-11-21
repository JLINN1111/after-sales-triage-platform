"""受规则约束的语言模型参考层；默认不调用任何外部服务。"""

import json
from collections.abc import Callable, Mapping
from typing import Any


ALLOWED_CATEGORIES = {
    "ELECTRICAL_CONTROL", "MECHANICAL", "SENSOR_COMMUNICATION", "THERMAL_COOLING", "OTHER_UNKNOWN",
}
MAX_TEXT_LENGTH = 240


def _ticket_value(ticket: Mapping[str, Any] | Any, name: str) -> Any:
    return ticket.get(name) if isinstance(ticket, Mapping) else getattr(ticket, name, None)


def _preflight_reasons(ticket: Mapping[str, Any] | Any, rules_result: Mapping[str, Any]) -> list[str]:
    reasons = []
    if _ticket_value(ticket, "safety_risk") in ("YES", "UNKNOWN"):
        reasons.append("安全风险需人工确认")
    if _ticket_value(ticket, "shutdown") in ("YES", "UNKNOWN"):
        reasons.append("停机状态需人工确认")
    if rules_result.get("missing_fields"):
        reasons.append("关键信息不完整")
    if rules_result.get("recommend_human"):
        reasons.append("规则已要求人工确认")
    return list(dict.fromkeys(reasons))


def _parse_response(raw_response: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("reference_category") not in ALLOWED_CATEGORIES:
        return None
    summary = value.get("customer_service_summary")
    next_question = value.get("next_question")
    if not isinstance(summary, str) or not isinstance(next_question, str):
        return None
    if len(summary) > MAX_TEXT_LENGTH or len(next_question) > MAX_TEXT_LENGTH:
        return None
    return {
        "reference_category": value["reference_category"],
        "customer_service_summary": summary.strip(),
        "next_question": next_question.strip(),
        "needs_human_review": True,
    }


def guarded_llm_reference(
    ticket: Mapping[str, Any] | Any,
    rules_result: Mapping[str, Any],
    invoke: Callable[[Mapping[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """返回受控参考；无调用器、前置风险或无效输出均保守退回人工。"""
    preflight = _preflight_reasons(ticket, rules_result)
    if preflight:
        return {"status": "BLOCKED", "reasons": preflight, "reference": None}
    if invoke is None:
        return {"status": "DISABLED", "reasons": ["未配置语言模型调用器"], "reference": None}
    payload = {
        "description": str(_ticket_value(ticket, "description") or ""),
        "rule_category": rules_result.get("predicted_category"),
        "instruction": (
            "只输出一个 JSON 对象，不使用 Markdown 代码块或额外字段。"
            "JSON 必须且只能包含 reference_category、customer_service_summary、next_question 三个字段；"
            "reference_category 必须与 rule_category 完全一致；两个文本字段均为不超过 240 字的客服参考文字。"
            "不得给出维修步骤、根因判断、安全放行结论或自动处置建议。"
        ),
        "required_schema": {
            "reference_category": rules_result.get("predicted_category"),
            "customer_service_summary": "字符串，客服摘要",
            "next_question": "字符串，下一步需客户补充的问题",
        },
    }
    try:
        raw_response = invoke(payload)
    except Exception:
        return {"status": "BLOCKED", "reasons": ["语言模型调用失败，未采用任何输出"], "reference": None}
    parsed = _parse_response(raw_response)
    if parsed is None:
        return {"status": "BLOCKED", "reasons": ["语言模型输出不符合结构化安全约定"], "reference": None}
    if parsed["reference_category"] != rules_result.get("predicted_category"):
        return {"status": "BLOCKED", "reasons": ["语言模型与规则类别不一致"], "reference": None}
    return {"status": "REFERENCE", "reasons": ["仅供客服参考，仍需人工确认"], "reference": parsed}
