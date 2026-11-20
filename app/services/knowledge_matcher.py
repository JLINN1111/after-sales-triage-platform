"""知识分层匹配服务（成员2实现，供统一分诊入口回调）。

接口约定（见交接 tl02）：
    match_knowledge(ticket, rules_result) -> dict
返回至少包含 knowledge_ids / reference_knowledge_ids / knowledge_match_level。

两层匹配：
    第一层：equipment_category + subsystem 召回参考候选（REFERENCE）。
    第二层：品牌、型号、控制系统、版本范围与报警码可确认时，返回 EXACT。

安全边界：
    - 仅公开基准设备提供标准设备键，不得当作企业实际资产。
    - 无台账映射（工单设备编号未在台账登记）时禁止 EXACT。
    - 安全风险 / 已停机时降级为 REFERENCE，不输出确定结论。
"""

import csv
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.config import ROOT

KNOWLEDGE_CSV = ROOT / "数据资料" / "维修知识" / "知识库.csv"
LEDGER_CSV = ROOT / "数据资料" / "真实业务准备" / "设备台账.csv"

# 前台设备类型 → 后台设备大类（OTHER 不自动映射）
FRONT_TYPE_TO_CATEGORY = {
    "CNC": "CNC_MACHINING",
    "INJECTION": "INJECTION_MOLDING",
    "CONVEYOR": "CONVEYOR",
    "AIR_COMPRESSOR": "AIR_COMPRESSOR",
    "VFD": "VARIABLE_FREQUENCY_DRIVE",
}

# 数控工单出现这些线索时，额外召回 CNC_CONTROL 参考候选（不作精确匹配）
CNC_CONTROL_CLUES = ("控制屏", "程序", "通信", "通讯", "控制器", "报警画面", "触摸屏", "显示屏")

# 子系统关键词：从用户可观察现象推断，不猜测根因
SUBSYSTEM_KEYWORDS = {
    "THERMAL_COOLING": ("温度过高", "过热", "高温", "风扇", "散热", "温控", "电机温度", "控制柜温度"),
    "COOLANT_SYSTEM": ("冷却液", "冷却", "切削液", "喷嘴", "流量", "液位", "泵"),
    "PNEUMATIC": ("气压", "气流", "压缩空气", "气源"),
    "LUBRICATION": ("润滑", "残余压力", "残压", "油脂", "润滑油"),
    "DRIVE_MOTOR": ("电机过载", "电机", "过载", "OLF"),
    "DRIVE_ELECTRICAL": ("IGBT", "短路", "SCF", "电缆"),
    "DRIVE_SAFETY": ("安全转矩", "转矩关断", "STO", "5091"),
}


def _value(obj: Mapping[str, Any] | Any, field: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(field)
    return getattr(obj, field, None)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_knowledge() -> list[dict[str, str]]:
    return _read_csv(KNOWLEDGE_CSV)


def load_ledger() -> list[dict[str, str]]:
    return _read_csv(LEDGER_CSV)


def infer_subsystems(description: str) -> set[str]:
    """按可观察现象推断可能涉及的子系统集合（可多个）。"""
    text = description or ""
    return {
        subsystem
        for subsystem, keywords in SUBSYSTEM_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }


def alarm_match(knowledge_alarm: str, ticket_alarm: str) -> bool:
    """知识条目报警码支持用 | 分隔多个；两边逐个比对。"""
    if not knowledge_alarm or not ticket_alarm:
        return False
    knowledge_codes = {code.strip() for code in knowledge_alarm.split("|") if code.strip()}
    ticket_codes = {code.strip() for code in ticket_alarm.split("|") if code.strip()}
    return bool(knowledge_codes & ticket_codes)


def _reference_candidates(
    category: str | None, subsystems: set[str], description: str, rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """第一层：设备大类 + 子系统召回参考候选；数控控制线索额外召回 CNC_CONTROL。"""
    candidates = [
        row for row in rows
        if category and row["equipment_category"] == category and row["subsystem"] in subsystems
    ]
    if category == "CNC_MACHINING" and any(clue in (description or "") for clue in CNC_CONTROL_CLUES):
        seen = {row["knowledge_id"] for row in candidates}
        for row in rows:
            if row["equipment_category"] == "CNC_CONTROL" and row["knowledge_id"] not in seen:
                candidates.append(row)
                seen.add(row["knowledge_id"])
    return candidates


def _exact_candidates(
    ticket: Any, category: str | None, ledger: dict[str, str] | None, rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """第二层：台账映射确认设备键后，品牌/型号/控制系统/版本/报警码全部一致才算 EXACT。"""
    if ledger is None or not category:
        return []

    ticket_alarm = (str(_value(ticket, "alarm_code") or "")).strip()
    if not ticket_alarm:
        return []

    matched = []
    for row in rows:
        if row["equipment_category"] != category:
            continue
        if row["brand"] != ledger["brand"]:
            continue
        if row["equipment_model"] != ledger["equipment_model"]:
            continue
        if row["controller_system"] != ledger["controller_system"]:
            continue
        # software_version=ANY 表示原厂资料未限定具体版本，视为适配
        if row["software_version"] not in ("ANY", "", ledger["software_version"]):
            continue
        if not alarm_match(row["alarm_code"], ticket_alarm):
            continue
        matched.append(row)
    return matched


def match_knowledge(ticket: Any, rules_result: Mapping[str, Any]) -> dict[str, Any]:
    """返回知识匹配三字段，由统一分诊入口合并写入工单。"""
    category = FRONT_TYPE_TO_CATEGORY.get(str(_value(ticket, "equipment_type") or ""))
    description = str(_value(ticket, "description") or "")
    subsystems = infer_subsystems(description)

    rows = load_knowledge()
    references = _reference_candidates(category, subsystems, description, rows)

    # 工单设备编号 → 台账 asset_token；只有台账登记过的设备才做第二层确认
    asset_token = str(_value(ticket, "equipment_code") or "").strip()
    ledger = None
    if asset_token:
        ledger = next((r for r in load_ledger() if r["asset_token"] == asset_token), None)

    exact = _exact_candidates(ticket, category, ledger, rows)

    # 安全优先：安全风险或已停机时不输出确定维修结论
    unsafe = _value(ticket, "safety_risk") == "YES" or _value(ticket, "shutdown") == "YES"
    if unsafe:
        exact = []

    # 多个同等候选不算精确（约定：存在多个同等候选时改为参考 + 人工确认）
    if len(exact) == 1:
        return {
            "knowledge_ids": [exact[0]["knowledge_id"]],
            "reference_knowledge_ids": [],
            "knowledge_match_level": "EXACT",
        }

    reference_ids = [row["knowledge_id"] for row in references]
    reference_ids += [row["knowledge_id"] for row in exact]  # 被降级的精确候选转为参考
    reference_ids = list(dict.fromkeys(reference_ids))
    if reference_ids:
        return {
            "knowledge_ids": [],
            "reference_knowledge_ids": reference_ids,
            "knowledge_match_level": "REFERENCE",
        }

    return {
        "knowledge_ids": [],
        "reference_knowledge_ids": [],
        "knowledge_match_level": "NONE",
    }
