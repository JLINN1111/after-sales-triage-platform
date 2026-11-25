"""三种角色的页面入口与服务端访问范围。"""

import tempfile
import unittest
from pathlib import Path

from app import create_app, db
from app.models import User


class RoleNavigationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "roles.db"
        self.app = create_app({
            "TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}", "CSRF_ENABLED": False,
        })
        with self.app.app_context():
            db.create_all()
            self.ids = {}
            for username, role in (("agent01", "AGENT"), ("reviewer01", "REVIEWER"), ("admin01", "ADMIN")):
                user = User(username=username, role=role, is_active=True)
                user.set_password("safe-test-password")
                db.session.add(user)
                db.session.flush()
                self.ids[role] = user.id
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.tempdir.cleanup()

    def client_for(self, role):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.ids[role]
        return client

    def test_each_role_only_gets_its_work_navigation(self):
        agent_page = self.client_for("AGENT").get("/home", follow_redirects=True).data
        self.assertIn("提交报修".encode("utf-8"), agent_page)
        self.assertIn("我的报修".encode("utf-8"), agent_page)
        self.assertNotIn("知识库管理".encode("utf-8"), agent_page)

        reviewer_page = self.client_for("REVIEWER").get("/home", follow_redirects=True).data
        self.assertIn("工单处理".encode("utf-8"), reviewer_page)
        self.assertNotIn("提交报修".encode("utf-8"), reviewer_page)

        admin_page = self.client_for("ADMIN").get("/home", follow_redirects=True).data
        self.assertIn("账户管理".encode("utf-8"), admin_page)
        self.assertIn("知识库管理".encode("utf-8"), admin_page)
        self.assertNotIn("工单处理".encode("utf-8"), admin_page)

    def test_server_also_blocks_cross_role_pages(self):
        self.assertEqual(self.client_for("ADMIN").get("/tickets").status_code, 302)
        self.assertEqual(self.client_for("AGENT").get("/knowledge").status_code, 302)
        self.assertEqual(self.client_for("REVIEWER").get("/tickets/new").status_code, 302)


if __name__ == "__main__":
    unittest.main()
