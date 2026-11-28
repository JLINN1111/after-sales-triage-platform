"""工单详情只展示业务可读的分诊依据。"""

import unittest

from app.routes.tickets import translate_evidence


class TriageDisplayTests(unittest.TestCase):
    def test_known_category_evidence_is_business_text(self):
        evidence = translate_evidence(["RULE-CATEGORY-ELECTRICAL_CONTROL:显示屏"])
        self.assertEqual(evidence, ["描述中提及“显示屏”，与电气或控制异常相关"])

    def test_conflict_evidence_hides_internal_category_codes(self):
        evidence = translate_evidence([
            "RULE-CATEGORY-CONFLICT:ELECTRICAL_CONTROL:显示屏",
            "RULE-CATEGORY-CONFLICT:MECHANICAL:异响",
        ])
        self.assertEqual(evidence, ["描述中存在多个异常方向的线索，需人工核对"])
        self.assertNotIn("ELECTRICAL_CONTROL", "；".join(evidence))

    def test_unknown_internal_code_is_not_exposed(self):
        self.assertEqual(translate_evidence(["RULE-INTERNAL-ONLY:debug"]), [])


if __name__ == "__main__":
    unittest.main()
