"""在案例家族隔离验证集上评测本地分类模型。"""

import csv
import json
import sys
import argparse
from pathlib import Path

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.algorithms.classifier import load_classifier, predict_category

DATASET = ROOT / "数据资料" / "训练数据" / "正式验证集_案例族隔离.csv"
OUTPUT = ROOT / "测试留存" / "阶段三" / "分类模型验证集评测.json"


def main():
    argparse.ArgumentParser().parse_args()
    model = load_classifier()
    if model is None:
        raise SystemExit("未找到本地模型，请先运行 train_model.py。")
    with DATASET.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if any(row.get("review_status") != "已审核" for row in rows):
        raise SystemExit("验证集存在未审核样本，已停止评测。")
    expected = [row["category"] for row in rows]
    predicted = [predict_category(row["description"], model)["category"] for row in rows]
    labels = sorted(set(expected))
    result = {
        "data_scope": "课程虚构、人工审核、案例家族隔离验证集；不代表真实业务准确率",
        "split": "validation",
        "sample_count": len(rows),
        "accuracy": accuracy_score(expected, predicted),
        "macro_f1": f1_score(expected, predicted, average="macro"),
        "labels": labels,
        "confusion_matrix": confusion_matrix(expected, predicted, labels=labels).tolist(),
        "classification_report": classification_report(expected, predicted, labels=labels, output_dict=True, zero_division=0),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"验证完成：{len(rows)} 条案例家族隔离的虚构验证样本，Accuracy={result['accuracy']:.3f}，Macro-F1={result['macro_f1']:.3f}")
    print(f"结果已保存：{OUTPUT}")


if __name__ == "__main__":
    main()
