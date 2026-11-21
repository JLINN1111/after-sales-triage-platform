"""阿里百炼和 DeepSeek 的最小 OpenAI 兼容调用器；默认不向外发送数据。"""

import json
import os
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LlmProviderError(RuntimeError):
    """不向前端暴露上游原始错误或密钥。"""


def _enabled(config: Mapping[str, Any]) -> bool:
    return bool(config.get("LLM_ENABLED")) and bool(config.get("LLM_ALLOW_EXTERNAL_CALLS"))


def configured_llm_invoke(
    config: Mapping[str, Any],
    opener: Callable[..., Any] = urlopen,
) -> Callable[[Mapping[str, Any]], str] | None:
    """返回已显式启用的供应商调用器；配置不完整时保持禁用。"""
    if not _enabled(config):
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
                {"role": "system", "content": "你是售后客服文本整理助手。只输出用户要求的 JSON，不提供维修步骤、根因判断或安全放行结论。"},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{base_url}/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            with opener(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise LlmProviderError("上游语言模型调用失败") from error
        try:
            content = value["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LlmProviderError("上游语言模型响应无有效内容") from error
        if not isinstance(content, str):
            raise LlmProviderError("上游语言模型响应格式无效")
        return content

    return invoke
