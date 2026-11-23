"""可选大模型参考层的安全测试：默认关闭、脱敏、拦截、不改分诊结论。"""

import json
import unittest
from types import SimpleNamespace

from app.services.llm_advisor import (
    build_reference_payload,
    configured_invoke,
    get_llm_reference,
    is_enabled,
    parse_reference,
    preflight_reasons,
)


def ticket(**overrides):
    base = dict(description="控制柜温度过高，风扇异常",
                equipment_type="CNC", safety_risk="NO", shutdown="NO")
    base.update(overrides)
    return SimpleNamespace(**base)


RULES = {"predicted_category": "THERMAL_COOLING", "priority": "HIGH",
         "missing_fields": [], "recommend_human": False}


def ok_invoke(payload):
    return json.dumps({
        "reference_category": payload["rule_category"],
        "customer_service_summary": "已记录温度异常，请客服核对风扇运行状态。",
        "next_question": "请补充报警代码和控制系统型号。",
    }, ensure_ascii=False)


class TestLlmAdvisor(unittest.TestCase):

    def test_default_disabled(self):
        self.assertFalse(is_enabled({"LLM_ENABLED": False, "LLM_ALLOW_EXTERNAL_CALLS": True}))
        self.assertFalse(is_enabled({"LLM_ENABLED": True, "LLM_ALLOW_EXTERNAL_CALLS": False}))
        self.assertTrue(is_enabled({"LLM_ENABLED": True, "LLM_ALLOW_EXTERNAL_CALLS": True}))

    def test_no_invoke_returns_disabled(self):
        r = get_llm_reference(ticket(), RULES, None)
        self.assertEqual(r["status"], "DISABLED")
        self.assertIsNone(r["reference"])
        self.assertTrue(r["needs_human_review"])

    def test_preflight_blocks_risk(self):
        self.assertTrue(preflight_reasons(ticket(safety_risk="YES"), RULES))
        self.assertTrue(preflight_reasons(ticket(shutdown="UNKNOWN"), RULES))
        self.assertTrue(preflight_reasons(ticket(), {**RULES, "missing_fields": ["equipment_model"]}))
        self.assertTrue(preflight_reasons(ticket(), {**RULES, "recommend_human": True}))

    def test_risk_never_calls_invoke(self):
        called = []
        def invoke(payload):
            called.append(payload)
            return ok_invoke(payload)
        r = get_llm_reference(ticket(safety_risk="YES"), RULES, invoke)
        self.assertEqual(r["status"], "BLOCKED")
        self.assertEqual(called, [])

    def test_deidentification_in_payload(self):
        payload, sensitive = build_reference_payload(
            ticket(description="请联系 13812345678 或 a@b.com"), RULES)
        self.assertIn("PHONE", sensitive)
        self.assertIn("EMAIL", sensitive)
        self.assertNotIn("13812345678", payload["description"])
        self.assertNotIn("a@b.com", payload["description"])

    def test_china_id_blocks_call(self):
        payload, reasons = build_reference_payload(
            ticket(description="身份证 110101199001011234 报修"), RULES)
        self.assertIsNone(payload)
        self.assertTrue(any("敏感身份信息" in r for r in reasons))

    def test_parse_rejects_wrong_category(self):
        raw = json.dumps({"reference_category": "MECHANICAL",
                          "customer_service_summary": "摘要", "next_question": "问题"})
        self.assertIsNone(parse_reference(raw, "THERMAL_COOLING"))

    def test_parse_rejects_extra_text_and_long(self):
        raw = json.dumps({"reference_category": "THERMAL_COOLING",
                          "customer_service_summary": "x" * 300, "next_question": "问题"})
        self.assertIsNone(parse_reference(raw, "THERMAL_COOLING"))
        self.assertIsNone(parse_reference("不是 JSON", "THERMAL_COOLING"))

    def test_parse_accepts_valid(self):
        raw = json.dumps({"reference_category": "THERMAL_COOLING",
                          "customer_service_summary": "摘要", "next_question": "问题"})
        parsed = parse_reference(raw, "THERMAL_COOLING")
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["needs_human_review"])

    def test_invoke_failure_is_blocked(self):
        def bad(payload):
            raise RuntimeError("network down")
        r = get_llm_reference(ticket(), RULES, bad)
        self.assertEqual(r["status"], "BLOCKED")

    def test_reference_does_not_change_rules(self):
        before = dict(RULES)
        r = get_llm_reference(ticket(), RULES, ok_invoke)
        self.assertEqual(r["status"], "REFERENCE")
        self.assertEqual(RULES, before)
        self.assertEqual(r["reference"]["reference_category"], before["predicted_category"])
        self.assertTrue(r["needs_human_review"])

    def test_configured_invoke_respects_switch(self):
        cfg = {"LLM_ENABLED": False, "LLM_ALLOW_EXTERNAL_CALLS": False,
               "LLM_PROVIDER": "deepseek"}
        self.assertIsNone(configured_invoke(cfg))


if __name__ == "__main__":
    unittest.main()
