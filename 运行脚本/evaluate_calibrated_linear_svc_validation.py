"""对已选校准 LinearSVC 在固定验证集确认阈值表现，不接入服务。"""

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "数据资料" / "训练数据"
OUTPUT = ROOT / "测试留存" / "阶段三" / "calibrated_linear_svc固定验证集阈值确认.json"
THRESHOLD = 0.70


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        result = list(csv.DictReader(handle))
    if any(row.get("review_status") != "已审核" for row in result):
        raise SystemExit(f"{path.name} 存在未审核样本。")
    return result


def main() -> None:
    train = rows(DATA / "正式训练集_案例族隔离.csv")
    validation = rows(DATA / "正式验证集_案例族隔离.csv")
    texts = np.array([row["description"] for row in train])
    labels = np.array([row["category"] for row in train])
    groups = np.array([row["case_id"] for row in train])
    cv = list(StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=20261121).split(texts, labels, groups))
    model = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(2, 4), sublinear_tf=True)),
        ("model", CalibratedClassifierCV(LinearSVC(C=1.0, class_weight="balanced", random_state=20261121), method="sigmoid", cv=cv)),
    ])
    model.fit(texts, labels)
    expected = np.array([row["category"] for row in validation])
    probability = model.predict_proba([row["description"] for row in validation])
    predicted = model.classes_[probability.argmax(axis=1)]
    confidence = probability.max(axis=1)
    accepted = confidence >= THRESHOLD
    report = {
        "data_scope": "固定案例家族隔离验证集，仅确认阈值；冻结最终测试集未读取。",
        "threshold": THRESHOLD,
        "sample_count": len(validation),
        "accepted_count": int(accepted.sum()),
        "coverage": float(accepted.mean()),
        "accepted_precision": float((predicted[accepted] == expected[accepted]).mean()) if accepted.any() else None,
        "rejected_count": int((~accepted).sum()),
        "policy": "阈值以下、规则冲突、高风险、停机、状态未知或信息不完整均应人工复核；本结果不授权自动放行。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"固定验证阈值确认：覆盖={report['coverage']:.3f}，接受精度={report['accepted_precision']:.3f}")


if __name__ == "__main__":
    main()
