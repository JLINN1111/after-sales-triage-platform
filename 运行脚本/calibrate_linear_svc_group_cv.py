"""按案例家族隔离评估 LinearSVC 概率校准，不接入分诊服务。"""

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "数据资料" / "训练数据" / "正式训练集_案例族隔离.csv"
OUTPUT = ROOT / "测试留存" / "阶段三" / "linear_svc分组校准评估.json"
SEED = 20261121


def expected_calibration_error(confidence: np.ndarray, correct: np.ndarray, bins: int = 10) -> float:
    total = len(confidence)
    error = 0.0
    for lower in np.linspace(0, 0.9, bins):
        upper = lower + 0.1
        mask = (confidence >= lower) & ((confidence < upper) if upper < 1 else (confidence <= upper))
        if mask.any():
            error += mask.mean() * abs(confidence[mask].mean() - correct[mask].mean())
    return float(error)


def main() -> None:
    with DATASET.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if any(row.get("review_status") != "已审核" for row in rows):
        raise SystemExit("训练集存在未审核样本，停止校准评估。")
    texts = np.array([row["description"] for row in rows])
    labels = np.array([row["category"] for row in rows])
    groups = np.array([row["case_id"] for row in rows])
    classes = np.unique(labels)
    probabilities = np.zeros((len(rows), len(classes)))
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    for train_index, test_index in outer.split(texts, labels, groups):
        train_groups = groups[train_index]
        train_labels = labels[train_index]
        inner = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED)
        calibration_splits = list(inner.split(texts[train_index], train_labels, train_groups))
        calibrated = Pipeline([
            ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(2, 4), sublinear_tf=True)),
            ("model", CalibratedClassifierCV(
                estimator=LinearSVC(C=1.0, class_weight="balanced", random_state=SEED),
                method="sigmoid", cv=calibration_splits,
            )),
        ])
        calibrated.fit(texts[train_index], train_labels)
        probabilities[test_index] = calibrated.predict_proba(texts[test_index])
    predicted_index = probabilities.argmax(axis=1)
    predicted = classes[predicted_index]
    confidence = probabilities.max(axis=1)
    correct = predicted == labels
    one_hot = np.equal(labels[:, None], classes[None, :]).astype(float)
    brier = float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))
    threshold_table = []
    for threshold in (0.50, 0.60, 0.70, 0.80, 0.90):
        accepted = confidence >= threshold
        threshold_table.append({
            "threshold": threshold,
            "accepted_count": int(accepted.sum()),
            "coverage": float(accepted.mean()),
            "precision": float(correct[accepted].mean()) if accepted.any() else None,
        })
    eligible = [item for item in threshold_table if item["accepted_count"] >= 10 and item["precision"] >= 0.90]
    report = {
        "data_scope": "仅正式训练集，外层与校准内层均按 case_id 分组；固定验证集和冻结最终测试集未读取。",
        "sample_count": len(rows), "case_family_count": len(set(groups)), "method": "LinearSVC + sigmoid calibration",
        "oof_accuracy": accuracy_score(labels, predicted),
        "oof_macro_f1": f1_score(labels, predicted, average="macro"),
        "multiclass_brier": brier,
        "top_label_ece": expected_calibration_error(confidence, correct),
        "threshold_table": threshold_table,
        "recommended_human_review_threshold": eligible[0]["threshold"] if eligible else None,
        "threshold_selection_rule": "仅选择折外样本不少于 10 条且观测精度不低于 0.90 的最低阈值；无满足项时不得设置自动放行阈值。",
        "confidence_bins": [
            {"lower": round(lower, 1), "upper": round(lower + 0.1, 1), "count": int(((confidence >= lower) & ((confidence < lower + 0.1) if lower < 0.9 else (confidence <= 1))).sum())}
            for lower in np.linspace(0, 0.9, 10)
        ],
        "integration_status": "仅为校准评估；尚未设定自动放行阈值，风险、停机、信息缺失与规则冲突仍必须转人工。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"分组校准评估完成：OOF Macro-F1={report['oof_macro_f1']:.3f}，ECE={report['top_label_ece']:.3f}，Brier={brier:.3f}")


if __name__ == "__main__":
    main()
