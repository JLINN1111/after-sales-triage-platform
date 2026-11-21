"""按故障案例家族隔离课程训练与验证样本。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from random import Random


def split_by_case_family(
    rows: Iterable[Mapping[str, str]],
    *,
    validation_fraction: float = 0.25,
    seed: int = 20261121,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """返回训练集和验证集，确保同一 ``case_id`` 不会跨集合。

    切分只适用于已审核的课程虚构样本；各类别独立、固定随机种子抽取
    约四分之一的案例家族进入验证集。冻结最终测试集不应传入本函数。
    """
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction 必须介于 0 与 1 之间。")

    materialized = [dict(row) for row in rows]
    by_category: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in materialized:
        category = (row.get("category") or "").strip()
        case_id = (row.get("case_id") or "").strip()
        if not category or not case_id:
            raise ValueError("每条样本必须包含 category 和 case_id。")
        if row.get("review_status") != "已审核":
            raise ValueError("正式训练/验证切分只能使用已审核样本。")
        by_category[category][case_id].append(row)

    if len(by_category) < 2:
        raise ValueError("切分至少需要两个类别。")

    validation_case_ids: set[str] = set()
    for category, families in sorted(by_category.items()):
        case_ids = sorted(families)
        if len(case_ids) < 2:
            raise ValueError(f"类别 {category} 的案例家族不足，无法隔离验证集。")
        count = max(1, round(len(case_ids) * validation_fraction))
        count = min(count, len(case_ids) - 1)
        category_rng = Random(f"{seed}:{category}")
        category_rng.shuffle(case_ids)
        validation_case_ids.update(case_ids[:count])

    train_rows = [row for row in materialized if row["case_id"] not in validation_case_ids]
    validation_rows = [row for row in materialized if row["case_id"] in validation_case_ids]
    if not train_rows or not validation_rows:
        raise ValueError("切分后训练集和验证集均不能为空。")
    return train_rows, validation_rows
