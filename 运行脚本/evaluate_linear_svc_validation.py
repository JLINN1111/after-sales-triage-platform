"""对训练集内选出的 LinearSVC 候选做一次固定验证集确认。"""

import csv
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "数据资料" / "训练数据"
TRAIN = DATA / "正式训练集_案例族隔离.csv"
VALIDATION = DATA / "正式验证集_案例族隔离.csv"
OUTPUT = ROOT / "测试留存" / "阶段三" / "linear_svc固定验证集确认.json"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if any(row.get("review_status") != "已审核" for row in rows):
        raise SystemExit(f"{path.name} 存在未审核样本，停止评测。")
    return rows


def main() -> None:
    train_rows, validation_rows = read_rows(TRAIN), read_rows(VALIDATION)
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(2, 4), sublinear_tf=True)),
        ("model", LinearSVC(C=1.0, class_weight="balanced", random_state=20261121)),
    ])
    pipeline.fit([row["description"] for row in train_rows], [row["category"] for row in train_rows])
    expected = [row["category"] for row in validation_rows]
    predicted = pipeline.predict([row["description"] for row in validation_rows])
    labels = sorted(set(expected))
    report = {
        "data_scope": "课程虚构、人工审核、案例家族隔离固定验证集；仅用于候选确认，不代表真实业务准确率。",
        "model": "char_tfidf_linear_svc",
        "sample_count": len(validation_rows),
        "accuracy": accuracy_score(expected, predicted),
        "macro_f1": f1_score(expected, predicted, average="macro"),
        "labels": labels,
        "confusion_matrix": confusion_matrix(expected, predicted, labels=labels).tolist(),
        "classification_report": classification_report(expected, predicted, labels=labels, output_dict=True, zero_division=0),
        "integration_status": "未接入分诊服务：需要按案例家族完成置信度校准和安全闸门验证后，才可用于人工复核辅助。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"LinearSVC 固定验证完成：Accuracy={report['accuracy']:.3f}，Macro-F1={report['macro_f1']:.3f}")


if __name__ == "__main__":
    main()
