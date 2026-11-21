"""导出已批准反馈为本地训练候选；不会训练模型或修改源数据。"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.models import TicketOutcome
from app.services.feedback_export import candidate_from_outcome

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "本地运行数据" / "训练候选"

app = create_app()
with app.app_context():
    OUT.mkdir(parents=True, exist_ok=True)
    candidates, excluded = [], []
    for outcome in TicketOutcome.query.order_by(TicketOutcome.id).all():
        row, reason = candidate_from_outcome(outcome)
        if row:
            candidates.append(row)
        else:
            excluded.append({"source_outcome_id": outcome.id, "reason": reason})
    with (OUT / "已批准反馈_训练候选.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["source_outcome_id", "description", "category", "reviewed_at", "sensitive_patterns_redacted", "candidate_status"])
        writer.writeheader(); writer.writerows(candidates)
    with (OUT / "已批准反馈_排除清单.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["source_outcome_id", "reason"])
        writer.writeheader(); writer.writerows(excluded)
print(f"训练候选导出完成：{len(candidates)} 条；排除 {len(excluded)} 条。仅供人工样本审核，未训练模型。")
