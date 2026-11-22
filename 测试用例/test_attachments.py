"""报修附件上传、访问和格式限制测试。"""

import io
import tempfile
import unittest
from pathlib import Path

from app import create_app, db
from app.models import Ticket, TicketAttachment


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.upload_dir = root / "attachments"
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{root / 'attachments.db'}",
            "CSRF_ENABLED": False,
            "AUTH_ENABLED": False,
            "ATTACHMENT_UPLOAD_DIR": str(self.upload_dir),
        })
        with self.app.app_context():
            db.create_all()
            db.session.add(Ticket(
                ticket_id="T-ATTACH-001", equipment_type="CNC",
                description="控制柜温度过高，需要补充报警截图。", operating_state="RUNNING",
                shutdown="NO", safety_risk="NO", alarm_code_status="NONE", action_status="NEW",
            ))
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.tempdir.cleanup()

    def test_upload_and_download_allowed_image(self):
        response = self.app.test_client().post(
            "/tickets/T-ATTACH-001/attachments",
            data={"attachments": (io.BytesIO(b"demo-image"), "报警截图.png", "image/png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            attachment = TicketAttachment.query.one()
            self.assertEqual(attachment.original_name, "报警截图.png")
            self.assertTrue((self.upload_dir / attachment.stored_name).is_file())
            attachment_id = attachment.id
        download = self.app.test_client().get(f"/tickets/T-ATTACH-001/attachments/{attachment_id}/download")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b"demo-image")
        download.close()

    def test_rejects_disallowed_file_type(self):
        response = self.app.test_client().post(
            "/tickets/T-ATTACH-001/attachments",
            data={"attachments": (io.BytesIO(b"unsafe"), "run.exe", "application/octet-stream")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(TicketAttachment.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
