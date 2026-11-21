import unittest
from types import SimpleNamespace
from datetime import datetime
from app.services.feedback_export import candidate_from_outcome

class FeedbackExportTests(unittest.TestCase):
    def outcome(self, **changes):
        ticket = SimpleNamespace(description="控制柜温度过高，冷却风扇异常。")
        review = SimpleNamespace(decision="APPROVED", reviewed_at=datetime(2026, 11, 21, 10, 0))
        value = SimpleNamespace(id=1, ticket=ticket, review=review, resolution_status="RESOLVED", final_category="THERMAL_COOLING")
        for key, item in changes.items(): setattr(value, key, item)
        return value
    def test_exports_only_approved_resolved_and_sanitized_candidate(self):
        row, reason = candidate_from_outcome(self.outcome())
        self.assertIsNone(reason); self.assertEqual(row["candidate_status"], "待人工样本审核")
    def test_excludes_identity_number(self):
        value = self.outcome(); value.ticket.description = "身份证110101199003071234，风扇异常"
        row, reason = candidate_from_outcome(value)
        self.assertIsNone(row); self.assertIn("身份证", reason)
