"""只在正式训练集内按案例家族比较文本分类基线。"""

import csv
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "数据资料" / "训练数据" / "正式训练集_案例族隔离.csv"
OUTPUT = ROOT / "测试留存" / "阶段三" / "分类模型训练集分组交叉验证.json"
SEED = 20261121


def candidates() -> dict[str, Pipeline]:
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), sublinear_tf=True)
    return {
        "char_tfidf_multinomial_nb": Pipeline([
            ("tfidf", vectorizer), ("model", MultinomialNB(alpha=0.5)),
        ]),
        "char_tfidf_logistic_regression": Pipeline([
            ("tfidf", vectorizer),
            ("model", LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000, random_state=SEED)),
        ]),
        "char_tfidf_linear_svc": Pipeline([
            ("tfidf", vectorizer),
            ("model", LinearSVC(C=1.0, class_weight="balanced", random_state=SEED)),
        ]),
    }


def main() -> None:
    with DATASET.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if any(row.get("review_status") != "已审核" for row in rows):
        raise SystemExit("训练集存在未审核样本，停止比较。")
    texts = [row["description"] for row in rows]
    labels = [row["category"] for row in rows]
    groups = [row["case_id"] for row in rows]
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    results = []
    for name, pipeline in candidates().items():
        fold_scores = []
        for train_idx, test_idx in splitter.split(texts, labels, groups):
            pipeline.fit([texts[index] for index in train_idx], [labels[index] for index in train_idx])
            predicted = pipeline.predict([texts[index] for index in test_idx])
            expected = [labels[index] for index in test_idx]
            fold_scores.append({
                "macro_f1": f1_score(expected, predicted, average="macro", zero_division=0),
                "accuracy": accuracy_score(expected, predicted),
            })
        results.append({
            "model": name,
            "mean_macro_f1": sum(score["macro_f1"] for score in fold_scores) / len(fold_scores),
            "mean_accuracy": sum(score["accuracy"] for score in fold_scores) / len(fold_scores),
            "fold_scores": fold_scores,
        })
    results.sort(key=lambda item: (item["mean_macro_f1"], item["mean_accuracy"]), reverse=True)
    report = {
        "data_scope": "仅正式训练集，按 case_id 分组的五折交叉验证；未读取固定验证集或冻结最终测试集。",
        "sample_count": len(rows), "case_family_count": len(set(groups)), "seed": SEED,
        "selection_rule": "先比较平均 Macro F1，若相同再比较平均 Accuracy。",
        "results": results, "recommended_candidate": results[0]["model"],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"训练集分组交叉验证完成，推荐候选：{report['recommended_candidate']}")
    for item in results:
        print(f"{item['model']}: Macro-F1={item['mean_macro_f1']:.3f}, Accuracy={item['mean_accuracy']:.3f}")


if __name__ == "__main__":
    main()
