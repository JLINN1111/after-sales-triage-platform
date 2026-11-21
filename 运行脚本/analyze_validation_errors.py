"""导出案例家族隔离验证集的误判，供人工补样审核使用。"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.algorithms.classifier import load_classifier, predict_category

DATASET = ROOT / "数据资料" / "训练数据" / "正式验证集_案例族隔离.csv"
OUTPUT = ROOT / "测试留存" / "阶段三" / "分类模型验证集误判明细.csv"


def main() -> None:
    model = load_classifier()
    if model is None:
        raise SystemExit("未找到本地模型，请先运行 train_model.py。")
    with DATASET.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    errors = []
    for row in rows:
        prediction = predict_category(row["description"], model)
        if prediction["category"] != row["category"]:
            errors.append({
                "sample_id": row["sample_id"], "case_id": row["case_id"],
                "expected_category": row["category"], "predicted_category": prediction["category"],
                "confidence": f"{prediction['confidence']:.4f}", "description": row["description"],
            })
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "case_id", "expected_category", "predicted_category", "confidence", "description"])
        writer.writeheader()
        writer.writerows(errors)
    print(f"已导出 {len(errors)} 条误判：{OUTPUT}")


if __name__ == "__main__":
    main()
