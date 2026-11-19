"""工单缺失信息识别与补问生成。"""

from collections.abc import Mapping
from typing import Any


_QUESTIONS = {
    "equipment_model": "请查看设备铭牌，补充设备品牌和型号；不方便查看时请说明设备外观或用途。",
    "operating_state": "故障发生时设备处于启动中、运行中、待机还是停机状态？",
    "shutdown": "请确认设备现在是否已经停机。",
    "safety_risk": "请确认现场是否存在人员或设备安全风险。",
    "alarm_code": "请查看设备屏幕，补充报警代码或报警提示文字。",
}


def _value(ticket: Mapping[str, Any] | Any, field: str) -> Any:
    if isinstance(ticket, Mapping):
        return ticket.get(field)
    return getattr(ticket, field, None)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def collect_missing_info(ticket: Mapping[str, Any] | Any) -> tuple[list[str], list[str]]:
    """返回待补充字段及对应问题。

    设备型号是可选字段：它会触发补问，但单独缺失不会升级安全优先级。
    """

    missing_fields: list[str] = []

    if _is_blank(_value(ticket, "equipment_model")):
        missing_fields.append("equipment_model")
    if _value(ticket, "operating_state") in (None, "", "UNKNOWN"):
        missing_fields.append("operating_state")
    if _value(ticket, "shutdown") in (None, "", "UNKNOWN"):
        missing_fields.append("shutdown")
    if _value(ticket, "safety_risk") in (None, "", "UNKNOWN"):
        missing_fields.append("safety_risk")

    alarm_status = _value(ticket, "alarm_code_status")
    if alarm_status in (None, "", "UNKNOWN") or (
        alarm_status == "PRESENT" and _is_blank(_value(ticket, "alarm_code"))
    ):
        missing_fields.append("alarm_code")

    questions = [_QUESTIONS[field] for field in missing_fields]
    return missing_fields, questions
