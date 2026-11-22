"""公开资料知识库的管理员维护权限与启停验证。"""

import tempfile
import unittest
from pathlib import Path

from app import create_app, db
from app.models import KnowledgeEntry, User
from app.services.knowledge_matcher import load_knowledge


class KnowledgeManagementTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "knowledge.db"
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}", "CSRF_ENABLED": False})
        with self.app.app_context():
            db.create_all()
            admin = User(username="admin", role="ADMIN", is_active=True)
            admin.set_password("pass")
            agent = User(username="agent", role="AGENT", is_active=True)
            agent.set_password("pass")
            db.session.add_all([admin, agent])
            db.session.commit()
            self.admin_id, self.agent_id = admin.id, agent.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.tempdir.cleanup()

    def _client_for(self, user_id):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
        return client

    @staticmethod
    def _payload():
        return {
            "brand": "演示设备", "equipment_model": "DEMO-01", "controller_system": "演示控制器", "software_version": "ANY",
            "equipment_category": "CNC_MACHINING", "subsystem": "THERMAL_COOLING", "title": "演示控制柜过热检查",
            "symptoms": "控制柜温度升高，风扇运行异常。", "alarm_code": "D-01", "fault_category": "THERMAL_COOLING",
            "summary": "停止继续加工并由售后核对散热通道与风扇状态。", "source_name": "公开演示资料",
            "source_page": "第 1 节", "source_url": "https://example.com/demo-guide",
        }

    def test_only_admin_can_maintain_knowledge(self):
        self.assertEqual(self._client_for(self.agent_id).get("/knowledge").status_code, 302)
        self.assertEqual(self._client_for(self.admin_id).post("/knowledge", data=self._payload()).status_code, 302)
        with self.app.app_context():
            entry = KnowledgeEntry.query.one()
            self.assertTrue(entry.is_active)
            self.assertIn(entry.knowledge_id, {row["knowledge_id"] for row in load_knowledge()})

    def test_disabled_entry_is_not_used_as_reference(self):
        client = self._client_for(self.admin_id)
        client.post("/knowledge", data=self._payload())
        with self.app.app_context():
            knowledge_id = KnowledgeEntry.query.one().knowledge_id
        self.assertEqual(client.post(f"/knowledge/{knowledge_id}/status").status_code, 302)
        with self.app.app_context():
            self.assertFalse(db.session.get(KnowledgeEntry, knowledge_id).is_active)
            self.assertNotIn(knowledge_id, {row["knowledge_id"] for row in load_knowledge()})


if __name__ == "__main__":
    unittest.main()
