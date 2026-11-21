import json
import unittest

from app.services.llm_guard import guarded_llm_reference


def ticket(**overrides):
    value = {"description": "控制柜温度过高且风扇异常", "safety_risk": "NO", "shutdown": "NO"}
    value.update(overrides)
    return value


def rules(**overrides):
    value = {"predicted_category": "THERMAL_COOLING", "recommend_human": False, "missing_fields": []}
    value.update(overrides)
    return value


class LlmGuardTests(unittest.TestCase):
    def test_blocks_before_call_for_safety_risk(self):
        called = False
        def invoke(_):
            nonlocal called
            called = True
            return "{}"
        result = guarded_llm_reference(ticket(safety_risk="YES"), rules(), invoke)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(called)

    def test_rejects_non_json_response(self):
        result = guarded_llm_reference(ticket(), rules(), lambda _: "维修即可")
        self.assertEqual(result["status"], "BLOCKED")

    def test_rejects_conflicting_category(self):
        response = json.dumps({"reference_category": "MECHANICAL", "customer_service_summary": "仅供参考", "next_question": "请确认运行状态"})
        result = guarded_llm_reference(ticket(), rules(), lambda _: response)
        self.assertEqual(result["status"], "BLOCKED")

    def test_returns_reference_without_overriding_rule(self):
        response = json.dumps({"reference_category": "THERMAL_COOLING", "customer_service_summary": "记录到温度和风扇现象", "next_question": "请确认当前是否已停机"})
        result = guarded_llm_reference(ticket(), rules(), lambda _: response)
        self.assertEqual(result["status"], "REFERENCE")
        self.assertTrue(result["reference"]["needs_human_review"])

    def test_payload_requires_exact_safe_json_schema(self):
        captured = {}

        def invoke(payload):
            captured.update(payload)
            return json.dumps({"reference_category": "THERMAL_COOLING", "customer_service_summary": "客服参考", "next_question": "请确认是否持续报警"})

        result = guarded_llm_reference(ticket(), rules(), invoke)
        self.assertEqual(result["status"], "REFERENCE")
        self.assertEqual(captured["required_schema"]["reference_category"], "THERMAL_COOLING")
        self.assertIn("不使用 Markdown", captured["instruction"])

    def test_provider_failure_is_blocked_without_propagating_error(self):
        result = guarded_llm_reference(ticket(), rules(), lambda _: (_ for _ in ()).throw(RuntimeError("network")))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["reference"])
