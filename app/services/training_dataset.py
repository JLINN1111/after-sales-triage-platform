"""构建课程虚构、人工审核候选的本地版本化快照；不训练或评测模型。"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

from app.services.feedback_export import candidate_from_outcome


CASE_FAMILY_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9_-]{2,63}\Z")
FIELDS = ["sample_id", "case_id", "category", "description", "source_outcome_id", "outcome_review_id", "candidate_review_id", "sample_sha256", "human_review_required", "review_status"]


def _sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _row_from_review(review):
    if review.decision != "ACCEPTED":
        return None, "审核结论非接受"
    if review.data_scope != "COURSE_SYNTHETIC":
        return None, "未明确确认为课程虚构样本"
    if not CASE_FAMILY_PATTERN.fullmatch(review.case_family_id or ""):
        return None, "案例家族标识缺失或格式无效"
    if not review.reviewed_category:
        return None, "缺少审核后类别"
    candidate, reason = candidate_from_outcome(review.outcome_review.outcome)
    if not candidate:
        return None, reason
    identity = {
        "source_outcome_id": candidate["source_outcome_id"], "outcome_review_id": review.outcome_review_id,
        "candidate_review_id": review.id, "case_id": review.case_family_id,
        "category": review.reviewed_category, "description": candidate["description"],
    }
    sample_hash = _sha256(identity)
    return {
        "sample_id": f"COURSE-CAND-{review.id}", "case_id": review.case_family_id,
        "category": review.reviewed_category, "description": candidate["description"],
        "source_outcome_id": str(candidate["source_outcome_id"]), "outcome_review_id": str(review.outcome_review_id),
        "candidate_review_id": str(review.id), "sample_sha256": sample_hash,
        "human_review_required": "true", "review_status": "已审核",
    }, None


def build_versioned_snapshot(reviews: Iterable, output_root: Path) -> tuple[dict, Path | None]:
    """写入可追溯快照；调用者必须显式执行，函数不读取训练或冻结测试集。"""
    rows, exclusions = [], []
    for review in reviews:
        row, reason = _row_from_review(review)
        if row:
            rows.append(row)
        else:
            exclusions.append({"candidate_review_id": review.id, "reason": reason})
    rows.sort(key=lambda row: row["candidate_review_id"])
    families = {}
    for row in rows:
        families.setdefault(row["case_id"], set()).add(row["category"])
    conflicting_families = {family for family, categories in families.items() if len(categories) > 1}
    if conflicting_families:
        exclusions.extend(
            {"candidate_review_id": row["candidate_review_id"], "reason": "同一案例家族类别不一致"}
            for row in rows if row["case_id"] in conflicting_families
        )
        rows = [row for row in rows if row["case_id"] not in conflicting_families]
    content_hash = _sha256(rows)
    manifest = {
        "dataset_version": f"course-candidates-{content_hash[:12]}", "data_scope": "COURSE_SYNTHETIC_ONLY",
        "status": "SNAPSHOT_ONLY_NOT_TRAINED", "sample_count": len(rows), "case_family_count": len({row["case_id"] for row in rows}),
        "content_sha256": content_hash, "exclusions": exclusions,
        "constraints": ["仅课程虚构样本", "案例家族不可跨训练验证或最终测试集合", "未读取冻结最终测试集", "未自动训练或评测模型"],
    }
    if not rows:
        return manifest, None
    version_dir = output_root / manifest["dataset_version"]
    version_dir.mkdir(parents=True, exist_ok=True)
    with (version_dir / "正式训练候选快照.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    with (version_dir / "构建清单.json").open("w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
    return manifest, version_dir
