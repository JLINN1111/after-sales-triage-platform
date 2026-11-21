"""训练本地 TF-IDF + 朴素贝叶斯模型；训练数据必须是已审核的虚构样本。"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.algorithms.classifier import save_classifier, train_classifier

DATASET = ROOT / "数据资料" / "训练数据" / "正式训练集_案例族隔离.csv"


def main():
    if not DATASET.exists():
        raise SystemExit(f"未找到训练数据：{DATASET}。请先运行 build_train_validation_split.py。")
    with DATASET.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if any(row.get("review_status") != "已审核" for row in rows):
        raise SystemExit("训练集存在未审核样本，已停止训练。")
    texts = [row["description"].strip() for row in rows]
    labels = [row["category"].strip() for row in rows]
    groups = [row["case_id"].strip() for row in rows]
    model = train_classifier(texts, labels, groups)
    save_classifier(model)
    print(f"模型训练完成：{len(texts)} 条训练样本，版本 {model['version']}。")


if __name__ == "__main__":
    main()
