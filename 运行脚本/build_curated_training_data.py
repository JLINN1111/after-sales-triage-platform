"""整合已审核训练候选；冻结最终测试集不参与本脚本。"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "数据资料" / "训练数据"
SOURCES = [
    "温度冷却训练样本_已审核.csv", "电气控制训练样本_已审核.csv",
    "机械传动训练样本_已审核.csv", "传感通信训练样本_已审核.csv",
    "电气控制混淆专项候选样本.csv",
    "三类边界专项训练样本_已审核.csv",
]
OUTPUT = DATA / "正式训练样本_已审核.csv"

rows = []
for name in SOURCES:
    with (DATA / name).open(encoding="utf-8-sig", newline="") as handle:
        rows.extend(csv.DictReader(handle))
if any(row.get("review_status") != "已审核" for row in rows):
    raise SystemExit("存在未审核样本，停止整合。")
with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
    fieldnames = ["sample_id", "case_id", "category", "description", "source_id", "human_review_required", "review_status"]
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows({field: row.get(field, "") for field in fieldnames} for row in rows)
print(f"已整合 {len(rows)} 条已审核训练样本：{OUTPUT}")
