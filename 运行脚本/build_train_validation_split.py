"""从正式已审核样本生成案例家族隔离的训练集和验证集。"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.algorithms.dataset_split import split_by_case_family

DATA = ROOT / "数据资料" / "训练数据"
SOURCE = DATA / "正式训练样本_已审核.csv"
TRAIN_OUTPUT = DATA / "正式训练集_案例族隔离.csv"
VALIDATION_OUTPUT = DATA / "正式验证集_案例族隔离.csv"
SEED = 20261121
FIELDNAMES = [
    "sample_id", "case_id", "category", "description", "source_id",
    "human_review_required", "review_status",
]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    train_rows, validation_rows = split_by_case_family(rows, seed=SEED)
    write_rows(TRAIN_OUTPUT, train_rows)
    write_rows(VALIDATION_OUTPUT, validation_rows)
    print(
        f"已按案例家族切分：训练集 {len(train_rows)} 条，"
        f"验证集 {len(validation_rows)} 条，固定种子 {SEED}。"
    )


if __name__ == "__main__":
    main()
