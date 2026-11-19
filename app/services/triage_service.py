"""统一分诊入口：合并规则分诊与可插拔的知识匹配结果。"""

from collections.abc import Callable, Mapping
from typing import Any

from app.algorithms.rules import triage_ticket as run_rules


KnowledgeMatcher = Callable[[Mapping[str, Any] | Any, Mapping[str, Any]], Mapping[str, Any]]
_MATCH_LEVELS = {"EXACT", "REFERENCE", "NONE"}


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _knowledge_defaults() -> dict[str, Any]:
    """知识匹配器尚未接入时的诚实占位，不把未检索误报成无匹配。"""

    return {
        "knowledge_ids": [],
        "reference_knowledge_ids": [],
        "knowledge_match_level": None,
        "knowledge_pending": True,
    }


def _merge_knowledge_result(result: dict[str, Any], knowledge: Mapping[str, Any]) -> None:
    """校验成员2服务的返回值，并按匹配级别补充人工确认规则。"""

    level = knowledge.get("knowledge_match_level")
    if level not in _MATCH_LEVELS:
        raise ValueError("知识匹配服务必须返回 EXACT、REFERENCE 或 NONE。")

    result["knowledge_ids"] = list(knowledge.get("knowledge_ids") or [])
    result["reference_knowledge_ids"] = list(knowledge.get("reference_knowledge_ids") or [])
    result["knowledge_match_level"] = level
    result["knowledge_pending"] = False

    if level == "REFERENCE":
        result["recommend_human"] = True
        _append_once(result["handoff_reasons"], "仅命中参考知识，需人工核对设备信息")
        _append_once(result["evidence_codes"], "RULE-KNOWLEDGE-REFERENCE")
    elif level == "NONE":
        result["recommend_human"] = True
        _append_once(result["handoff_reasons"], "未找到适用知识")
        _append_once(result["evidence_codes"], "RULE-KNOWLEDGE-NONE")


def triage_ticket(
    ticket: Mapping[str, Any] | Any,
    knowledge_matcher: KnowledgeMatcher | None = None,
) -> dict[str, Any]:
    """返回可写入工单的统一分诊结果。

    `knowledge_matcher` 由成员2实现，调用签名为
    ``knowledge_matcher(ticket, rules_result) -> knowledge_result``。
    未提供匹配器时只返回规则分诊，`knowledge_pending=True` 表示尚未检索。
    """

    result = run_rules(ticket)
    result.update(_knowledge_defaults())

    if knowledge_matcher is not None:
        _merge_knowledge_result(result, knowledge_matcher(ticket, result))

    return result
