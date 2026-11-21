"""对冻结最终测试集执行一次性验收；已有输出时拒绝重复运行。"""

import csv
import json
import sys
from pathlib import Path

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATASET = ROOT / "数据资料" / "训练数据" / "冻结最终测试集.csv"
OUTPUT = ROOT / "测试留存" / "阶段三" / "分类模型冻结最终测试验收.json"

from app.algorithms.classifier import load_classifier, predict_category


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit("冻结最终测试集已验收，拒绝重复运行。")
    model = load_classifier()
    if model is None:
        raise SystemExit("未找到本地冻结方案模型，请先训练。")
    with DATASET.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = [row["category"] for row in rows]
    predicted = [predict_category(row["description"], model)["category"] for row in rows]
    labels = sorted(set(expected))
    report = {
        "data_scope": "冻结最终测试集；课程虚构、人工审核样本，不代表真实企业准确率。",
        "execution_policy": "模型、参数和阈值冻结后执行一次；脚本拒绝重复运行。",
        "model_version": model.get("version"),
        "sample_count": len(rows),
        "accuracy": accuracy_score(expected, predicted),
        "macro_f1": f1_score(expected, predicted, average="macro"),
        "labels": labels,
        "confusion_matrix": confusion_matrix(expected, predicted, labels=labels).tolist(),
        "classification_report": classification_report(expected, predicted, labels=labels, output_dict=True, zero_division=0),
        "limitations": "样本量仅 12 条，且均为课程虚构样本；结果不能作为真实业务上线依据。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"冻结最终测试验收完成：Accuracy={report['accuracy']:.3f}，Macro-F1={report['macro_f1']:.3f}")


if __name__ == "__main__":
    main()
