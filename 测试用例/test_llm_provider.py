import json
import os
import unittest
from unittest.mock import patch

from app.services.llm_provider import configured_llm_invoke


class _Response:
    def __init__(self, value): self.value = value
    def read(self): return json.dumps(self.value).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *_): return False


class LlmProviderTests(unittest.TestCase):
    def test_disabled_never_builds_external_invoke(self):
        self.assertIsNone(configured_llm_invoke({"LLM_ENABLED": False, "LLM_ALLOW_EXTERNAL_CALLS": True}))

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    def test_deepseek_uses_configured_endpoint_and_json_mode(self):
        seen = {}
        def opener(request, timeout):
            seen["url"], seen["body"], seen["timeout"] = request.full_url, json.loads(request.data), timeout
            return _Response({"choices": [{"message": {"content": "{}"}}]})
        invoke = configured_llm_invoke({"LLM_ENABLED": True, "LLM_ALLOW_EXTERNAL_CALLS": True, "LLM_PROVIDER": "deepseek", "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com", "LLM_DEEPSEEK_MODEL": "deepseek-flash", "LLM_TIMEOUT_SECONDS": 9}, opener)
        self.assertEqual(invoke({"description": "仅测试"}), "{}")
        self.assertEqual(seen["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(seen["body"]["response_format"], {"type": "json_object"})
        self.assertEqual(seen["timeout"], 9)

    @patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}, clear=False)
    def test_aliyun_requires_explicit_workspace_base_url(self):
        self.assertIsNone(configured_llm_invoke({"LLM_ENABLED": True, "LLM_ALLOW_EXTERNAL_CALLS": True, "LLM_PROVIDER": "aliyun", "LLM_ALIYUN_BASE_URL": ""}))
