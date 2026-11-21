"""分类器训练与预测的最小自动检验。"""

import unittest
from unittest.mock import patch

from app.algorithms.classifier import predict_category, train_classifier
from app.algorithms.dataset_split import split_by_case_family
from app.services.triage_service import triage_ticket
from app.algorithms.deidentification import find_sensitive_patterns, redact_sensitive_patterns


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.model = train_classifier(
            ["控制柜温度过高冷却风扇异常", "主轴温度升高散热不足", "传动侧异响振动", "皮带跑偏卡滞"],
            ["THERMAL_COOLING", "THERMAL_COOLING", "MECHANICAL", "MECHANICAL"],
        )

    def test_predicts_trained_category(self):
        result = predict_category("设备出现异响和明显振动", self.model)
        self.assertEqual(result["category"], "MECHANICAL")
        self.assertGreater(result["confidence"], 0.5)

    def test_requires_multiple_categories(self):
        with self.assertRaises(ValueError):
            train_classifier(["温度过高"], ["THERMAL_COOLING"])

    def test_grouped_training_returns_calibrated_confidence(self):
        model = train_classifier(
            ["控制柜温度高", "冷却风扇异常", "传动机构异响", "设备振动明显"],
            ["THERMAL_COOLING", "THERMAL_COOLING", "MECHANICAL", "MECHANICAL"],
            ["T-1", "T-2", "M-1", "M-2"],
        )
        result = predict_category("设备传动异响", model)
        self.assertEqual(result["model_version"], "tfidf-calibrated-linearsvc-v0.2")
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_rule_model_conflict_requires_human_review(self):
        ticket = {
            "description": "控制柜温度过高，冷却风扇异常",
            "safety_risk": "NO", "shutdown": "NO",
            "operating_state": "RUNNING", "equipment_type": "CNC",
        }
        prediction = {"category": "MECHANICAL", "confidence": 0.95, "model_version": "test"}
        with patch("app.services.triage_service.predict_category", return_value=prediction):
            result = triage_ticket(ticket)
        self.assertTrue(result["recommend_human"])
        self.assertIn("规则与分类模型结果不一致", result["handoff_reasons"])

    def test_safety_rule_remains_human_review_with_model_prediction(self):
        ticket = {
            "description": "传动区域异响和振动",
            "safety_risk": "YES", "shutdown": "NO",
            "operating_state": "RUNNING", "equipment_type": "CNC",
        }
        prediction = {"category": "MECHANICAL", "confidence": 0.95, "model_version": "test"}
        with patch("app.services.triage_service.predict_category", return_value=prediction):
            result = triage_ticket(ticket)
        self.assertTrue(result["recommend_human"])
        self.assertIn("存在安全风险", result["handoff_reasons"])

    def test_high_confidence_unknown_rule_still_requires_human_review(self):
        ticket = {
            "description": "现场反馈设备情况异常但没有描述具体故障现象",
            "safety_risk": "NO", "shutdown": "NO",
            "operating_state": "RUNNING", "equipment_type": "CNC",
        }
        prediction = {"category": "ELECTRICAL_CONTROL", "confidence": 0.90, "model_version": "test"}
        with patch("app.services.triage_service.predict_category", return_value=prediction):
            result = triage_ticket(ticket)
        self.assertEqual(result["predicted_category"], "ELECTRICAL_CONTROL")
        self.assertTrue(result["recommend_human"])
        self.assertIn("故障类别信息不足", result["handoff_reasons"])


class DatasetSplitTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"sample_id": "T-1", "case_id": "THERMAL-1", "category": "THERMAL", "description": "温度升高", "review_status": "已审核"},
            {"sample_id": "T-2", "case_id": "THERMAL-1", "category": "THERMAL", "description": "风扇异常", "review_status": "已审核"},
            {"sample_id": "T-3", "case_id": "THERMAL-2", "category": "THERMAL", "description": "冷却液不足", "review_status": "已审核"},
            {"sample_id": "T-4", "case_id": "THERMAL-3", "category": "THERMAL", "description": "温控提示", "review_status": "已审核"},
            {"sample_id": "M-1", "case_id": "MECH-1", "category": "MECHANICAL", "description": "传动异响", "review_status": "已审核"},
            {"sample_id": "M-2", "case_id": "MECH-2", "category": "MECHANICAL", "description": "设备振动", "review_status": "已审核"},
            {"sample_id": "M-3", "case_id": "MECH-3", "category": "MECHANICAL", "description": "机构卡滞", "review_status": "已审核"},
        ]

    def test_case_families_are_isolated_and_repeatable(self):
        first_train, first_validation = split_by_case_family(self.rows, seed=7)
        second_train, second_validation = split_by_case_family(self.rows, seed=7)
        self.assertEqual(first_train, second_train)
        self.assertEqual(first_validation, second_validation)
        train_cases = {row["case_id"] for row in first_train}
        validation_cases = {row["case_id"] for row in first_validation}
        self.assertFalse(train_cases & validation_cases)
        self.assertEqual({"THERMAL", "MECHANICAL"}, {row["category"] for row in first_train})
        self.assertEqual({"THERMAL", "MECHANICAL"}, {row["category"] for row in first_validation})

    def test_rejects_unreviewed_rows(self):
        rows = self.rows.copy()
        rows[0] = {**rows[0], "review_status": "待审核"}
        with self.assertRaises(ValueError):
            split_by_case_family(rows)


class DeidentificationTests(unittest.TestCase):
    def test_detects_common_sensitive_patterns_without_returning_raw_value(self):
        found = find_sensitive_patterns("联系人电话13800138000，邮箱test@example.com")
        self.assertEqual(found, ["PHONE", "EMAIL"])

    def test_redacts_detected_values_with_type_placeholders(self):
        text, patterns = redact_sensitive_patterns("联系人13800138000，邮箱 service@example.com")
        self.assertEqual(patterns, ["PHONE", "EMAIL"])
        self.assertNotIn("13800138000", text)
        self.assertNotIn("service@example.com", text)
        self.assertIn("[PHONE_REDACTED]", text)
        self.assertIn("[EMAIL_REDACTED]", text)
