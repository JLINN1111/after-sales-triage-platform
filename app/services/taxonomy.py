"""故障词表读取服务（模块1产物，只读）。

用途：
- 从 data/fault_taxonomy.json 读取模块1的故障词表，供页面或接口展示。
- 本词表是《开发分工手册》模块1的原始产物（6 类，来源待确认），
  与当前系统冻结的 V1 故障标签（报修字段与标签定义.md 第5节，5 类）是两套不同体系。
  因此本模块只负责"读取与展示"，不参与分诊判断；分诊仍以 rules.py 的 V1 标签为准。

函数：
- load_taxonomy() -> dict：返回完整词表字典。
- category_briefs() -> list：返回供页面展示的简要字段。
- find_category(category_id) -> dict | None：按编号查单个类别。
"""

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = ROOT / "data" / "fault_taxonomy.json"


@lru_cache(maxsize=1)
def load_taxonomy():
    """读取并返回词表；文件不存在时返回空结构，不抛异常影响页面。"""
    if not TAXONOMY_PATH.exists():
        return {"version": None, "categories": []}
    with TAXONOMY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def category_briefs():
    """供页面/接口展示的简要信息，避免把大段反例直接铺在页面上。"""
    return [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "priority": c.get("priority"),
            "transfer_to": c.get("transfer_to"),
            "symptoms": c.get("symptoms", []),
        }
        for c in load_taxonomy().get("categories", [])
    ]


def find_category(category_id):
    """按编号查找单个故障类别，找不到返回 None。"""
    for c in load_taxonomy().get("categories", []):
        if c.get("id") == category_id:
            return c
    return None
