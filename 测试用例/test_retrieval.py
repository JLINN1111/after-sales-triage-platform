import unittest

from app.algorithms.knowledge_retrieval import bfs_recall, rank_candidates


class KnowledgeRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"knowledge_id": "K-THERMAL", "equipment_category": "CNC_MACHINING", "subsystem": "THERMAL_COOLING", "title": "控制柜过热", "symptoms": "温度过高 风扇异常", "summary": "转人工", "fault_category": "THERMAL_COOLING"},
            {"knowledge_id": "K-COOLANT", "equipment_category": "CNC_MACHINING", "subsystem": "COOLANT_SYSTEM", "title": "冷却液压力低", "symptoms": "冷却液 流量", "summary": "转人工", "fault_category": "THERMAL_COOLING"},
        ]

    def test_bfs_recalls_only_connected_subsystem_candidates(self):
        recalled = bfs_recall(self.rows, "CNC_MACHINING", {"THERMAL_COOLING"})
        self.assertEqual([row["knowledge_id"] for row in recalled], ["K-THERMAL"])

    def test_rank_places_matching_reference_first(self):
        ranked = rank_candidates("控制柜温度过高且风扇异常", self.rows)
        self.assertEqual(ranked[0]["knowledge_id"], "K-THERMAL")
