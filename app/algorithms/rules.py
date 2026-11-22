"""首版规则分诊：安全优先、保守分类，不输出维修结论。"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.algorithms.missing_info import collect_missing_info


MODEL_VERSION = "rules-v0.1"

_CATEGORY_KEYWORDS = {
    "ELECTRICAL_CONTROL": (
        "控制面板", "控制器", "触摸屏", "显示屏", "黑屏", "供电", "电源",
        "电压", "控制指令", "按键", "无显示",
    ),
    "MECHANICAL": (
        "异响", "振动", "卡滞", "卡住", "松动", "传动", "磨损", "跑偏",
    ),
    "THERMAL_COOLING": (
        "过热", "温度过高", "温度升高", "高温", "冷却风扇", "冷却不足",
        "散热", "温控",
    ),
    "SENSOR_COMMUNICATION": (
        "传感器", "读数异常", "信号丢失", "信号中断", "通信中断", "通讯中断",
        "无法接收数据", "数据无法接收",
    ),
}

_SYMPTOM_TAGS = {
    "CANNOT_START": ("无法启动", "不能启动", "启动不了"),
    "ABNORMAL_TEMPERATURE": ("过热", "温度过高", "温度升高", "高温"),
    "ABNORMAL_NOISE": ("异响",),
    "VIBRATION": ("振动",),
    "JAMMING": ("卡滞", "卡住"),
    "ALARM": ("报警", "告警"),
    "SENSOR_READING": ("传感器", "读数异常"),
    "SIGNAL_LOSS": ("信号丢失", "信号中断"),
    "COMMUNICATION_LOSS": ("通信中断", "通讯中断", "无法接收数据", "数据无法接收"),
}


def _value(ticket: Mapping[str, Any] | Any, field: str) -> Any:
    if isinstance(ticket, Mapping):
        return ticket.get(field)
    return getattr(ticket, field, None)


def _description(ticket: Mapping[str, Any] | Any) -> str:
    value = _value(ticket, "description")
    return value.strip() if isinstance(value, str) else ""


def extract_symptom_tags(description: str) -> list[str]:
    """只提取用户已描述的可观察现象，不猜测维修根因。"""

    return [
        tag for tag, keywords in _SYMPTOM_TAGS.items()
        if any(keyword in description for keyword in keywords)
    ] or ["UNKNOWN_SYMPTOM"]


def classify_description(description: str) -> tuple[str, list[str], bool]:
    """返回类别、命中依据和是否存在类别冲突。"""

    matched = {
        category: [keyword for keyword in keywords if keyword in description]
        for category, keywords in _CATEGORY_KEYWORDS.items()
    }
    matched = {category: words for category, words in matched.items() if words}

    if len(matched) == 1:
        category, words = next(iter(matched.items()))
        return category, [f"RULE-CATEGORY-{category}:{word}" for word in words], False

    if len(matched) > 1:
        evidence = [
            f"RULE-CATEGORY-CONFLICT:{category}:{word}"
            for category, words in matched.items()
            for word in words
        ]
        return "OTHER_UNKNOWN", evidence, True

    return "OTHER_UNKNOWN", ["RULE-CATEGORY-NO-DIRECT-EVIDENCE"], False


def triage_ticket(ticket: Mapping[str, Any] | Any) -> dict[str, Any]:
    """根据单张工单生成规则分诊结果。

    该函数暂不进行知识匹配，知识相关字段由成员2的服务在后续编排时补充。
    """

    missing_fields, follow_up_questions = collect_missing_info(ticket)
    description = _description(ticket)
    predicted_category, category_evidence, category_conflict = classify_description(description)
    symptom_tags = extract_symptom_tags(description)

    safety_risk = _value(ticket, "safety_risk")
    shutdown = _value(ticket, "shutdown")
    evidence_codes = list(category_evidence)
    handoff_reasons: list[str] = []

    if safety_risk == "YES" or shutdown == "YES":
        priority = "URGENT"
        evidence_codes.append("RULE-SAFETY-YES" if safety_risk == "YES" else "RULE-SHUTDOWN-YES")
        if safety_risk == "YES":
            handoff_reasons.append("存在安全风险")
        if shutdown == "YES":
            handoff_reasons.append("设备已停机")
    elif safety_risk == "UNKNOWN" or shutdown == "UNKNOWN":
        priority = "HIGH"
        if safety_risk == "UNKNOWN":
            evidence_codes.append("RULE-SAFETY-UNKNOWN")
            handoff_reasons.append("安全风险尚未确认")
        if shutdown == "UNKNOWN":
            evidence_codes.append("RULE-SHUTDOWN-UNKNOWN")
            handoff_reasons.append("停机状态尚未确认")
    elif category_conflict:
        priority = "HIGH"
        handoff_reasons.append("故障类别线索冲突")
    elif predicted_category == "OTHER_UNKNOWN":
        priority = "HIGH"
        handoff_reasons.append("故障类别信息不足")
    else:
        priority = "NORMAL"

    recommend_human = bool(handoff_reasons)
    return {
        "symptom_tags": symptom_tags,
        "predicted_category": predicted_category,
        "priority": priority,
        "evidence_codes": evidence_codes,
        "missing_fields": missing_fields,
        "follow_up_questions": follow_up_questions,
        "recommend_human": recommend_human,
        "handoff_reasons": handoff_reasons,
        "model_version": MODEL_VERSION,
        "triaged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
