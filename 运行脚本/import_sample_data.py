"""导入演示种子数据：把 5 条虚构工单样例写入 SQLite。

用法（在仓库根目录、虚拟环境已激活时）：
    python 运行脚本/import_sample_data.py

说明：
- 数据源：数据资料/样例工单/工单样例.csv（虚构演示样例，已带分诊结果）。
- 只导入 CSV 中存在、且数据库里还没有的工单；重复执行不会覆盖或清空已有数据。
- 所有内容均为虚构演示数据，不含真实客户信息。
"""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app, db
from app.models import Ticket  # noqa: E402

CSV_PATH = ROOT / "数据资料" / "样例工单" / "工单样例.csv"

# CSV 中这些字段是 JSON 字符串或布尔文本，导入前需要转换
JSON_FIELDS = [
    "symptom_tags", "evidence_codes", "missing_fields", "follow_up_questions",
    "knowledge_ids", "reference_knowledge_ids", "handoff_reasons",
]
DATETIME_FIELDS = ["occurred_at", "created_at", "triaged_at", "action_at"]
BOOL_FIELDS = ["recommend_human"]


def parse_value(field, raw):
    """把 CSV 字符串转换为模型字段需要的类型。"""
    if raw is None or raw == "":
        return None
    if field in JSON_FIELDS:
        return json.loads(raw)
    if field in DATETIME_FIELDS:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M")
    if field in BOOL_FIELDS:
        return raw.strip().lower() in ("true", "1", "yes")
    return raw


def import_sample_data():
    if not CSV_PATH.exists():
        print(f"未找到样例文件：{CSV_PATH}")
        return

    app = create_app()
    added, skipped = 0, 0
    with app.app_context():
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                ticket_id = (row.get("ticket_id") or "").strip()
                if not ticket_id:
                    continue
                if db.session.get(Ticket, ticket_id) is not None:
                    skipped += 1
                    continue

                data = {}
                for column, raw in row.items():
                    if column not in Ticket.__table__.columns:
                        continue
                    data[column] = parse_value(column, raw)

                db.session.add(Ticket(**data))
                added += 1

        db.session.commit()
        print(f"种子数据导入完成：新增 {added} 条，跳过已存在 {skipped} 条。")
        print(f"当前工单总数：{Ticket.query.count()} 条")


if __name__ == "__main__":
    import_sample_data()
