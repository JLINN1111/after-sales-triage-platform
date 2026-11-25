"""受限的对话式报修信息采集服务，不参与分诊或工单决策。"""

import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from app.algorithms.deidentification import redact_sensitive_patterns


class AssistantUnavailable(RuntimeError):
    """模型未配置、调用失败或输出不可用时的可恢复错误。"""


ALLOWED_FIELDS = {
    "equipment_type", "equipment_model", "occurred_at", "operating_state", "shutdown",
    "safety_risk", "alarm_code_status", "alarm_code", "submitter_note",
}
CONTEXT_FIELDS = ALLOWED_FIELDS | {"description", "customer_follow_up"}
ENUM_FIELDS = {
    "equipment_type": {"CNC", "INJECTION", "CONVEYOR", "AIR_COMPRESSOR", "VFD", "OTHER"},
    "operating_state": {"STARTING", "RUNNING", "STANDBY", "STOPPED", "UNKNOWN"},
    "shutdown": {"YES", "NO", "UNKNOWN"},
    "safety_risk": {"YES", "NO", "UNKNOWN"},
    "alarm_code_status": {"PRESENT", "NONE", "UNKNOWN"},
}
_RISK_TERMS = ("冒烟", "起火", "火花", "漏电", "触电", "燃烧", "受伤", "异味")


def _text(value, limit=800):
    value, _ = redact_sensitive_patterns(str(value or ""))
    return value.strip()[:limit]


def redact_context(values):
    """仅保留对话所需字段；设备编号、账户、附件和地址一律不外发。"""
    return {field: _text(values.get(field, ""), 500) for field in CONTEXT_FIELDS if values.get(field)}


def _provider_settings():
    provider = current_app.config["LLM_PROVIDER"]
    if provider == "deepseek":
        return (
            current_app.config["DEEPSEEK_API_KEY"],
            current_app.config["LLM_DEEPSEEK_BASE_URL"].rstrip("/") + "/chat/completions",
            current_app.config["LLM_DEEPSEEK_MODEL"],
        )
    if provider == "dashscope":
        base_url = current_app.config["LLM_DASHSCOPE_BASE_URL"].rstrip("/")
        return (current_app.config["DASHSCOPE_API_KEY"], f"{base_url}/chat/completions", current_app.config["LLM_DASHSCOPE_MODEL"])
    raise AssistantUnavailable("未识别的大模型服务商配置。")


def _system_prompt(context):
    return """你是制造设备售后报修的信息采集助手。你的唯一任务是通过对话补全用户已经描述的可观察信息。
不要判断故障类别、优先级，不要给维修步骤、知识资料、处理结论，不要声称系统会自动处理。
只在用户明确表达某字段时给出字段建议；不确定就放入 needs_confirmation。
如出现冒烟、起火、漏电、触电、受伤、火花或明显安全风险，立即提醒停止继续操作并联系现场售后，但仍不能给维修结论。
必须只返回 JSON 对象：reply（简短中文追问或确认语）、field_suggestions（对象）、needs_confirmation（字段名数组）、urgent_risk_hint（布尔值）。
field_suggestions 只允许 equipment_type、equipment_model、occurred_at、operating_state、shutdown、safety_risk、alarm_code_status、alarm_code、submitter_note。
当前已知的、已脱敏的表单信息如下：""" + json.dumps(context, ensure_ascii=False)


def _normalize_turn(value, user_text):
    if not isinstance(value, dict):
        raise AssistantUnavailable("模型返回格式不正确，请改为手工填写。")
    reply = _text(value.get("reply"), 500)
    if not reply:
        raise AssistantUnavailable("模型未返回可用追问，请改为手工填写。")
    suggestions = value.get("field_suggestions") or {}
    if not isinstance(suggestions, dict):
        suggestions = {}
    clean = {}
    for field, raw in suggestions.items():
        if field not in ALLOWED_FIELDS:
            continue
        item = _text(raw, 120)
        if not item:
            continue
        if field in ENUM_FIELDS and item not in ENUM_FIELDS[field]:
            continue
        clean[field] = item
    needed = value.get("needs_confirmation") or []
    if not isinstance(needed, list):
        needed = []
    needed = [str(item) for item in needed if str(item) in ALLOWED_FIELDS][:5]
    risk = bool(value.get("urgent_risk_hint")) or any(term in user_text for term in _RISK_TERMS)
    return {"reply": reply, "field_suggestions": clean, "needs_confirmation": needed, "urgent_risk_hint": risk}


def _call_remote(messages):
    if not current_app.config["LLM_ENABLED"] or not current_app.config["LLM_ALLOW_EXTERNAL_CALLS"]:
        raise AssistantUnavailable("对话助手尚未启用；请继续使用表单填写报修信息。")
    api_key, endpoint, model = _provider_settings()
    if not api_key or not endpoint or endpoint == "/chat/completions":
        raise AssistantUnavailable("当前模型服务尚未完成本机配置。")
    payload = json.dumps({
        "model": model, "messages": messages, "temperature": 0.1,
        "max_tokens": current_app.config["LLM_MAX_OUTPUT_TOKENS"],
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    request = Request(endpoint, data=payload, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=current_app.config["LLM_TIMEOUT_SECONDS"]) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise AssistantUnavailable(f"模型服务暂时不可用（HTTP {error.code}），请改为手工填写。") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise AssistantUnavailable("模型服务连接失败或超时，请改为手工填写。") from error
    try:
        return json.loads(body["choices"][0]["message"]["content"]), current_app.config["LLM_PROVIDER"], model
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise AssistantUnavailable("模型未返回可解析内容，请改为手工填写。") from error


def generate_turn(session, user_text, form_context):
    """生成一次受限助手回复；测试可通过配置注入本地生成器。"""
    user_text = _text(user_text, 1000)
    if not user_text:
        raise ValueError("请输入需要补充的故障信息。")
    history = list(session.messages)[-current_app.config["LLM_MAX_HISTORY_MESSAGES"]:]
    messages = [{"role": "system", "content": _system_prompt(redact_context(form_context))}]
    messages.extend({"role": "user" if item.speaker == "USER" else "assistant", "content": _text(item.content, 800)} for item in history)
    generator = current_app.config.get("ASSISTANT_TURN_GENERATOR")
    if generator:
        raw = generator(messages)
        provider, model = "test", "test-generator"
    else:
        raw, provider, model = _call_remote(messages)
    return _normalize_turn(raw, user_text), provider, model


def mark_suggestion_applied(message, selected_fields):
    suggestions = message.suggested_fields or {}
    applied = {field: suggestions[field] for field in selected_fields if field in suggestions}
    message.applied_fields = applied
    message.applied_at = datetime.now()
    return applied
