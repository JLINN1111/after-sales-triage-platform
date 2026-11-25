"""账户创建成功提示仅在跳转页显示，并带自动消失标记。"""

import re
import tempfile
import unittest
from pathlib import Path

from app import create_app, db
from app.models import User


class FlashFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "flash.db"
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}", "CSRF_ENABLED": True})
        with self.app.app_context():
            db.create_all()
            user = User(username="admin01", role="ADMIN", is_active=True)
            user.set_password("admin-test-password")
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.tempdir.cleanup()

    def test_created_account_message_has_auto_dismiss_marker_once(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
        page = client.get("/admin/users")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = client.post("/admin/users", data={
            "csrf_token": token, "username": "reviewer_demo", "password": "DemoReviewer2026!", "role": "REVIEWER",
        }, follow_redirects=True)
        self.assertIn("已创建账号：reviewer_demo。".encode("utf-8"), response.data)
        self.assertIn(b'data-auto-dismiss="4000"', response.data)
        refreshed = client.get("/admin/users")
        self.assertNotIn("已创建账号：reviewer_demo。".encode("utf-8"), refreshed.data)

    def test_general_login_feedback_also_has_auto_dismiss_marker(self):
        client = self.app.test_client()
        page = client.get("/login")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = client.post("/login", data={
            "csrf_token": token, "username": "admin01", "password": "wrong-password",
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn("账号或密码不正确".encode("utf-8"), response.data)
        self.assertIn(b'data-auto-dismiss="4000"', response.data)


if __name__ == "__main__":
    unittest.main()
