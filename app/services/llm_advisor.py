"""可选的大模型客服参考层：默认不调用外部服务，输出仅作参考、不改变分诊结论。

设计要点：
- 只有 LLM_ENABLED 与 LLM_ALLOW_EXTERNAL_CALLS 同时为真，且密钥已配置时才可能调用。
- 调用前先脱敏；含身份证等敏感身份信息直接放弃调用。
- 安全风险、停机、缺关键信息、规则已要求人工时，前置拦截不调用。
- 模型输出必须是受约束的 JSON，且类别与规则结论一致，否则一律丢弃。
- 返回结构中 needs_human_review 恒为 True，调用方不得据此自动放行。
"""

import json
import os
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.algorithms.deidentification import redact_sensitive_patterns

ALLOWED_CATEGORIES = {
    "ELECTRICAL_CONTROL", "MECHANICAL", "SENSOR_COMMUNICATION",
    "THERMAL_COOLING", "OTHER_UNKNOWN",
}
MAX_TEXT_LENGTH = 240

SYSTEM_PROMPT = (
    "你是售后客服文本整理助手。只输出用户要求的 JSON，不提供维修步骤、"
    "根因判断或安全放行结论。"
)


class LlmAdvisorError(RuntimeError):
    """不向前端暴露上游原始错误或密钥。"""


def is_enabled(config: Mapping[str, Any]) -> bool:
    """是否显式允许调用外部大模型。默认关闭。"""
    return bool(config.get("LLM_ENABLED")) and bool(config.get("LLM_ALLOW_EXTERNAL_CALLS"))


def configured_invoke(
    config: Mapping[str, Any], opener: Callable[..., Any] = urlopen
) -> Callable[[Mapping[str, Any]], str] | None:
    """返回已显式启用的供应商调用器；配置不完整时保持禁用。"""
    if not is_enabled(config):
        return None
    provider = str(config.get("LLM_PROVIDER") or "").lower()
    if provider == "aliyun":
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        base_url = str(config.get("LLM_ALIYUN_BASE_URL") or "").rstrip("/")
        model = str(config.get("LLM_ALIYUN_MODEL") or "qwen-plus")
    elif provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = str(config.get("LLM_DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        model = str(config.get("LLM_DEEPSEEK_MODEL") or "deepseek-flash")
    else:
        return None
    if not api_key or not base_url:
        return None
    timeout = int(config.get("LLM_TIMEOUT_SECONDS", 12))

    def invoke(payload: Mapping[str, Any]) -> str:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            with opener(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise LlmAdvisorError("上游语言模型调用失败") from error
        try:
            content = value["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LlmAdvisorError("上游语言模型响应无有效内容") from error
        if not isinstance(content, str):
            raise LlmAdvisorError("上游语言模型响应格式无效")
        return content

    return invoke


def _value(obj: Mapping[str, Any] | Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, Mapping) else getattr(obj, name, None)


def preflight_reasons(
    ticket: Mapping[str, Any] | Any, rules_result: Mapping[str, Any]
) -> list[str]:
    """返回不宜调用大模型的理由；非空时一律不调用。"""
    reasons = []
    if _value(ticket, "safety_risk") in ("YES", "UNKNOWN"):
        reasons.append("安全风险需人工确认")
    if _value(ticket, "shutdown") in ("YES", "UNKNOWN"):
        reasons.append("停机状态需人工确认")
    if rules_result.get("missing_fields"):
        reasons.append("关键信息不完整")
    if rules_result.get("recommend_human"):
        reasons.append("规则已要求人工确认")
    return list(dict.fromkeys(reasons))


def parse_reference(raw_response: str, expected_category: str) -> dict[str, Any] | None:
    """严格校验模型输出，任何一个条件不满足都返回 None。"""
    try:
        value = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("reference_category") not in ALLOWED_CATEGORIES:
        return None
    if value.get("reference_category") != expected_category:
        return None
    summary = value.get("customer_service_summary")
    next_question = value.get("next_question")
    if not isinstance(summary, str) or not isinstance(next_question, str):
        return None
    if not summary.strip() or not next_question.strip():
        return None
    if len(summary) > MAX_TEXT_LENGTH or len(next_question) > MAX_TEXT_LENGTH:
        return None
    return {
        "reference_category": value["reference_category"],
        "customer_service_summary": summary.strip(),
        "next_question": next_question.strip(),
        "needs_human_review": True,
    }


def build_reference_payload(
    ticket: Mapping[str, Any] | Any, rules_result: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    """脱敏并构造调用载荷；含敏感身份信息时放弃调用。"""
    description, sensitive_types = redact_sensitive_patterns(
        str(_value(ticket, "description") or "")
    )
    if "CHINA_ID" in sensitive_types:
        return None, ["描述含需人工处理的敏感身份信息，未调用语言模型"]
    category = rules_result.get("predicted_category")
    payload = {
        "description": description,
        "rule_category": category,
        "instruction": (
            "只输出一个 JSON 对象，不使用 Markdown 代码块或额外字段。"
            "JSON 必须且只能包含 reference_category、customer_service_summary、next_question 三个字段；"
            "reference_category 必须与 rule_category 完全一致；两个文本字段均为不超过 240 字的客服参考文字。"
            "不得给出维修步骤、根因判断、安全放行结论或自动处置建议。"
        ),
        "required_schema": {
            "reference_category": category,
            "customer_service_summary": "字符串，客服摘要",
            "next_question": "字符串，下一步需客户补充的问题",
        },
    }
    return payload, sensitive_types


def get_llm_reference(
    ticket: Mapping[str, Any] | Any,
    rules_result: Mapping[str, Any],
    invoke: Callable[[Mapping[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """返回受控参考；默认关闭、前置风险或无效输出均保守退回，不改分诊结论。

    返回结构:
      status: REFERENCE / DISABLED / BLOCKED
      reasons: 状态原因列表
      reference: 合规输出（仅 REFERENCE 时非 None）
      needs_human_review: 恒为 True
    """
    preflight = preflight_reasons(ticket, rules_result)
    if preflight:
        return {"status": "BLOCKED", "reasons": preflight, "reference": None,
                "needs_human_review": True}
    if invoke is None:
        return {"status": "DISABLED", "reasons": ["未配置或显式关闭语言模型调用器"],
                "reference": None, "needs_human_review": True}
    payload, sensitive_types = build_reference_payload(ticket, rules_result)
    if payload is None:
        return {"status": "BLOCKED", "reasons": sensitive_types, "reference": None,
                "needs_human_review": True}
    try:
        raw = invoke(payload)
    except Exception:
        return {"status": "BLOCKED", "reasons": ["语言模型调用失败，未采用任何输出"],
                "reference": None, "needs_human_review": True}
    parsed = parse_reference(raw, str(rules_result.get("predicted_category") or ""))
    if parsed is None:
        return {"status": "BLOCKED", "reasons": ["语言模型输出不符合结构化安全约定"],
                "reference": None, "needs_human_review": True}
    reasons = ["仅供客服参考，仍需人工确认"]
    if sensitive_types:
        reasons.append("已对描述中的可识别联系方式脱敏后发送")
    return {"status": "REFERENCE", "reasons": reasons, "reference": parsed,
            "needs_human_review": True}
