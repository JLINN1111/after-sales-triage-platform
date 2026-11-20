"""成员2知识分层匹配服务的自动检验。

覆盖交接 tl02 要求：精确匹配、仅参考匹配、无匹配、安全/停机优先。
"""

import unittest

from app.services.knowledge_matcher import match_knowledge
from app.services.triage_service import triage_ticket


def make_ticket(**overrides):
    ticket = {
        "equipment_type": "CNC",
        "equipment_model": "",
        "equipment_code": "",
        "description": "",
        "operating_state": "RUNNING",
        "shutdown": "NO",
        "safety_risk": "NO",
        "alarm_code_status": "NONE",
        "alarm_code": "",
    }
    ticket.update(overrides)
    return ticket


class KnowledgeMatchingTests(unittest.TestCase):
    def test_exact_when_ledger_and_alarm_confirmed(self):
        ticket = make_ticket(
            equipment_type="CNC", equipment_code="BASELINE-VF2-001",
            description="控制柜温度过高，风扇异常", alarm_code="253",
        )
        result = match_knowledge(ticket, {})
        self.assertEqual(result["knowledge_match_level"], "EXACT")
        self.assertEqual(result["knowledge_ids"], ["KB-HAAS-VF2-001"])
        self.assertEqual(result["reference_knowledge_ids"], [])

    def test_exact_requires_full_device_keys(self):
        # 报警码对不上时不得给 EXACT，降为参考
        ticket = make_ticket(
            equipment_type="CNC", equipment_code="BASELINE-VF2-001",
            description="控制柜温度过高", alarm_code="999",
        )
        result = match_knowledge(ticket, {})
        self.assertEqual(result["knowledge_match_level"], "REFERENCE")
        self.assertEqual(result["knowledge_ids"], [])

    def test_exact_forbidden_without_ledger_mapping(self):
        # 只有用户自填型号、无台账映射时禁止 EXACT
        ticket = make_ticket(
            equipment_type="CNC", equipment_model="VF-2",
            description="控制柜温度过高", alarm_code="253",
        )
        result = match_knowledge(ticket, {})
        self.assertNotEqual(result["knowledge_match_level"], "EXACT")

    def test_reference_when_only_category_matched(self):
        ticket = make_ticket(description="主轴运行温度过高，需要处理")
        result = match_knowledge(ticket, {})
        self.assertEqual(result["knowledge_match_level"], "REFERENCE")
        self.assertTrue(result["reference_knowledge_ids"])
        self.assertEqual(result["knowledge_ids"], [])

    def test_none_when_no_candidate(self):
        ticket = make_ticket(equipment_type="INJECTION", description="射胶动作异常需要检修")
        result = match_knowledge(ticket, {})
        self.assertEqual(result["knowledge_match_level"], "NONE")
        self.assertEqual(result["knowledge_ids"], [])
        self.assertEqual(result["reference_knowledge_ids"], [])

    def test_safety_takes_priority_over_exact(self):
        # 即使设备键完全匹配，安全风险存在时也降级，不输出确定结论
        ticket = make_ticket(
            equipment_type="CNC", equipment_code="BASELINE-VF2-001",
            description="控制柜温度过高", alarm_code="253", safety_risk="YES",
        )
        result = match_knowledge(ticket, {})
        self.assertEqual(result["knowledge_match_level"], "REFERENCE")

    def test_shutdown_takes_priority_over_exact(self):
        ticket = make_ticket(
            equipment_type="CNC", equipment_code="BASELINE-VF2-001",
            description="控制柜温度过高", alarm_code="253", shutdown="YES",
        )
        result = match_knowledge(ticket, {})
        self.assertEqual(result["knowledge_match_level"], "REFERENCE")


class UnifiedEntryTests(unittest.TestCase):
    def test_unified_entry_marks_human_for_reference(self):
        result = triage_ticket(make_ticket(description="主轴运行温度过高"), match_knowledge)
        self.assertEqual(result["knowledge_match_level"], "REFERENCE")
        self.assertTrue(result["recommend_human"])
        self.assertIn("仅命中参考知识，需人工核对设备信息", result["handoff_reasons"])
        self.assertFalse(result["knowledge_pending"])

    def test_unified_entry_exact_no_force_human(self):
        result = triage_ticket(
            make_ticket(
                equipment_type="CNC", equipment_code="BASELINE-VF2-001",
                description="控制柜温度过高，风扇异常", alarm_code="253",
                equipment_model="VF-2", operating_state="RUNNING",
            ),
            match_knowledge,
        )
        self.assertEqual(result["knowledge_match_level"], "EXACT")
        self.assertFalse(result["recommend_human"])


if __name__ == "__main__":
    unittest.main()
