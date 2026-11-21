"""校准 LinearSVC 故障分类器。

模型文件仅用于辅助分诊；安全、停机和信息缺失仍由规则层优先处置。
"""

from pathlib import Path
from typing import Iterable

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.svm import LinearSVC

from app.config import ROOT

MODEL_VERSION = "tfidf-calibrated-linearsvc-v0.2"
DEFAULT_MODEL_PATH = ROOT / "本地运行数据" / "模型文件" / "tfidf_nb.joblib"


def train_classifier(
    texts: Iterable[str], labels: Iterable[str], groups: Iterable[str] | None = None,
) -> dict:
    """训练仅供辅助分诊的校准模型；调用方负责数据集隔离。"""
    texts, labels = list(texts), list(labels)
    groups = list(groups) if groups is not None else None
    if len(texts) < 2 or len(set(labels)) < 2:
        raise ValueError("训练至少需要两个类别的已标注样本。")
    if groups is not None and len(groups) != len(texts):
        raise ValueError("案例家族数量必须与训练样本数量一致。")
    class_counts = {label: labels.count(label) for label in set(labels)}
    if groups is None:
        folds = min(3, min(class_counts.values()))
        if folds < 2:
            raise ValueError("每个类别至少需要两条训练样本以进行校准。")
        calibration_cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=20261121)
    else:
        group_counts = {
            label: len({group for group, row_label in zip(groups, labels) if row_label == label})
            for label in set(labels)
        }
        folds = min(3, min(group_counts.values()))
        if folds < 2:
            raise ValueError("每个类别至少需要两个案例家族以进行分组校准。")
        calibration_cv = list(StratifiedGroupKFold(
            n_splits=folds, shuffle=True, random_state=20261121,
        ).split(texts, labels, groups))
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), sublinear_tf=True)
    matrix = vectorizer.fit_transform(texts)
    classifier = CalibratedClassifierCV(
        estimator=LinearSVC(C=1.0, class_weight="balanced", random_state=20261121),
        method="sigmoid", cv=calibration_cv,
    ).fit(matrix, labels)
    return {"version": MODEL_VERSION, "vectorizer": vectorizer, "classifier": classifier}


def save_classifier(model: dict, path: Path = DEFAULT_MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_classifier(path: Path = DEFAULT_MODEL_PATH) -> dict | None:
    return joblib.load(path) if path.exists() else None


def predict_category(text: str, model: dict | None = None) -> dict | None:
    """返回类别与估计分数；模型缺失或文本为空时诚实返回 None。"""
    model = model or load_classifier()
    if not model or not (text or "").strip():
        return None
    matrix = model["vectorizer"].transform([text])
    probabilities = model["classifier"].predict_proba(matrix)[0]
    index = probabilities.argmax()
    return {
        "category": str(model["classifier"].classes_[index]),
        "confidence": float(probabilities[index]),
        "model_version": model.get("version", MODEL_VERSION),
    }
