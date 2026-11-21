"""知识参考的 BFS 候选召回与 TF-IDF 相似度排序。"""

from collections import defaultdict, deque

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _document(row: dict[str, str]) -> str:
    return " ".join(row.get(field, "") for field in ("title", "symptoms", "summary", "fault_category", "subsystem"))


def bfs_recall(
    rows: list[dict[str, str]], category: str | None, subsystems: set[str], max_depth: int = 2,
) -> list[dict[str, str]]:
    """从设备大类和子系统节点出发，召回可解释的参考知识候选。"""
    if not category or not subsystems:
        return []
    graph: dict[str, set[str]] = defaultdict(set)
    by_id = {row["knowledge_id"]: row for row in rows}
    for row in rows:
        category_node = f"category:{row['equipment_category']}"
        subsystem_node = f"subsystem:{row['equipment_category']}:{row['subsystem']}"
        knowledge_node = f"knowledge:{row['knowledge_id']}"
        graph[category_node].add(subsystem_node)
        graph[subsystem_node].add(category_node)
        graph[subsystem_node].add(knowledge_node)
        graph[knowledge_node].add(subsystem_node)
    queue = deque((f"subsystem:{category}:{subsystem}", 0) for subsystem in subsystems)
    visited = set()
    result_ids = []
    while queue:
        node, depth = queue.popleft()
        if node in visited or depth > max_depth:
            continue
        visited.add(node)
        if node.startswith("knowledge:"):
            result_ids.append(node.removeprefix("knowledge:"))
        for neighbor in graph[node]:
            queue.append((neighbor, depth + 1))
    return [by_id[knowledge_id] for knowledge_id in result_ids]


def rank_candidates(query: str, candidates: list[dict[str, str]], limit: int = 5) -> list[dict[str, str]]:
    """按相似度排序候选；分数仅用于知识参考顺序，不构成诊断置信度。"""
    if not query.strip() or not candidates:
        return candidates[:limit]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), sublinear_tf=True)
    matrix = vectorizer.fit_transform([query, *(_document(row) for row in candidates)])
    scores = cosine_similarity(matrix[0], matrix[1:]).ravel()
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda item: item[1], reverse=True)
    return [row for row, _ in ranked[:limit]]
