import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from app.services.training_dataset import build_versioned_snapshot


def accepted_review(review_id=1, family="COURSE-THERMAL-001", category="THERMAL_COOLING"):
    ticket = SimpleNamespace(description="冷却风扇异常，设备已按流程停止。")
    outcome_review = SimpleNamespace(decision="APPROVED", reviewed_at=datetime(2026, 11, 22, 10, 0, 0))
    outcome = SimpleNamespace(id=10 + review_id, final_category="THERMAL_COOLING", resolution_status="RESOLVED", ticket=ticket, review=outcome_review)
    outcome_review.outcome = outcome
    return SimpleNamespace(id=review_id, decision="ACCEPTED", data_scope="COURSE_SYNTHETIC", case_family_id=family, reviewed_category=category, outcome_review_id=20 + review_id, outcome_review=outcome_review)


class VersionedTrainingSnapshotTests(unittest.TestCase):
    def test_builds_traceable_course_snapshot_without_training(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, location = build_versioned_snapshot([accepted_review()], Path(directory))
            self.assertEqual(manifest["status"], "SNAPSHOT_ONLY_NOT_TRAINED")
            self.assertEqual(manifest["sample_count"], 1)
            self.assertTrue(location.is_dir())
            with (location / "正式训练候选快照.csv").open(encoding="utf-8-sig") as file:
                row = next(csv.DictReader(file))
            self.assertEqual(row["case_id"], "COURSE-THERMAL-001")
            self.assertEqual(row["review_status"], "已审核")
            self.assertEqual(len(row["sample_sha256"]), 64)
            saved_manifest = json.loads((location / "构建清单.json").read_text(encoding="utf-8"))
            self.assertIn("未自动训练或评测模型", saved_manifest["constraints"])

    def test_excludes_unconfirmed_scope_and_conflicting_case_family(self):
        unconfirmed = accepted_review(); unconfirmed.data_scope = None
        conflicting = accepted_review(review_id=2, family="COURSE-THERMAL-001", category="MECHANICAL")
        with tempfile.TemporaryDirectory() as directory:
            manifest, location = build_versioned_snapshot([unconfirmed, accepted_review(), conflicting], Path(directory))
        self.assertIsNone(location)
        self.assertEqual(manifest["sample_count"], 0)
        self.assertEqual({item["reason"] for item in manifest["exclusions"]}, {"未明确确认为课程虚构样本", "同一案例家族类别不一致"})
