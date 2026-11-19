"""成员1规则分诊的自动检验。"""

import unittest

from app.algorithms.rules import triage_ticket


def make_ticket(**overrides):
    ticket = {
        "equipment_type": "CONVEYOR",
        "equipment_model": "2200 Series",
        "description": "传动侧出现异响和振动。",
        "operating_state": "RUNNING",
        "shutdown": "NO",
        "safety_risk": "NO",
        "alarm_code_status": "NONE",
        "alarm_code": None,
    }
    ticket.update(overrides)
    return ticket


class RulesTriageTests(unittest.TestCase):
    def test_shutdown_is_urgent_and_requires_human_review(self):
        result = triage_ticket(make_ticket(shutdown="YES"))
        self.assertEqual(result["priority"], "URGENT")
        self.assertTrue(result["recommend_human"])
        self.assertIn("设备已停机", result["handoff_reasons"])

    def test_known_safety_risk_is_urgent_and_requires_human_review(self):
        result = triage_ticket(make_ticket(safety_risk="YES"))
        self.assertEqual(result["priority"], "URGENT")
        self.assertTrue(result["recommend_human"])
        self.assertIn("存在安全风险", result["handoff_reasons"])

    def test_unknown_safety_risk_is_high_and_requires_human_review(self):
        result = triage_ticket(make_ticket(safety_risk="UNKNOWN"))
        self.assertEqual(result["priority"], "HIGH")
        self.assertTrue(result["recommend_human"])
        self.assertIn("安全风险尚未确认", result["handoff_reasons"])

    def test_unknown_fault_is_high_and_requires_human_review(self):
        result = triage_ticket(make_ticket(description="设备工作时感觉和平时不一样，具体原因不清楚。"))
        self.assertEqual(result["predicted_category"], "OTHER_UNKNOWN")
        self.assertEqual(result["priority"], "HIGH")
        self.assertTrue(result["recommend_human"])

    def test_missing_safety_and_shutdown_is_high_and_generates_questions(self):
        result = triage_ticket(make_ticket(safety_risk="UNKNOWN", shutdown="UNKNOWN"))
        self.assertEqual(result["priority"], "HIGH")
        self.assertTrue(result["recommend_human"])
        self.assertIn("safety_risk", result["missing_fields"])
        self.assertIn("shutdown", result["missing_fields"])
        self.assertGreaterEqual(len(result["follow_up_questions"]), 2)

    def test_normal_mechanical_ticket_is_normal_without_human_review(self):
        result = triage_ticket(make_ticket())
        self.assertEqual(result["predicted_category"], "MECHANICAL")
        self.assertEqual(result["priority"], "NORMAL")
        self.assertFalse(result["recommend_human"])
        self.assertEqual(result["model_version"], "rules-v0.1")


if __name__ == "__main__":
    unittest.main()
