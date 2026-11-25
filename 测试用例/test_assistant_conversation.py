"""对话式信息采集助手：字段边界、采用留痕和工单状态限制。"""

import tempfile
import unittest
from pathlib import Path

from app import create_app, db
from app.models import ConversationMessage, ConversationSession, Ticket


def fake_turn(_messages):
    return {
        "reply": "请确认设备目前是否已经停机，并补充报警代码。",
        "field_suggestions": {
            "equipment_model": "VF-2", "shutdown": "YES", "alarm_code_status": "PRESENT",
            "alarm_code": "253", "priority": "URGENT",
        },
        "needs_confirmation": ["safety_risk", "shutdown", "priority"],
        "urgent_risk_hint": False,
    }


class AssistantConversationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "assistant.db"
        self.app = create_app({
            "TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
            "CSRF_ENABLED": False, "AUTH_ENABLED": False, "ASSISTANT_TURN_GENERATOR": fake_turn,
        })
        with self.app.app_context():
            db.create_all()
            db.session.add(Ticket(
                ticket_id="T-ASSIST-001", equipment_type="CNC", description="控制柜温度过高，屏幕提示报警。",
                operating_state="UNKNOWN", shutdown="UNKNOWN", safety_risk="UNKNOWN", alarm_code_status="UNKNOWN",
                action_status="NEED_INFO", submitted_by="SYSTEM",
            ))
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.tempdir.cleanup()

    def test_draft_conversation_only_returns_allowed_fields_and_records_adoption(self):
        client = self.app.test_client()
        session = client.post("/assistant/sessions").get_json()["session_id"]
        reply = client.post(f"/assistant/sessions/{session}/messages", json={
            "message": "设备已经停机，报警代码是253，型号VF-2。",
            "form_context": {"equipment_type": "CNC", "description": "控制柜发热"},
        })
        self.assertEqual(reply.status_code, 200)
        body = reply.get_json()
        self.assertNotIn("priority", body["field_suggestions"])
        self.assertNotIn("priority", body["needs_confirmation"])
        self.assertEqual(body["field_suggestions"]["shutdown"], "YES")

        applied = client.post(f"/assistant/sessions/{session}/apply", json={
            "message_id": body["message_id"], "fields": ["equipment_model", "shutdown", "priority"],
        })
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.get_json()["applied_fields"], {"equipment_model": "VF-2", "shutdown": "YES"})
        with self.app.app_context():
            assistant_message = db.session.get(ConversationMessage, body["message_id"])
            self.assertEqual(assistant_message.applied_fields["shutdown"], "YES")

    def test_ticket_conversation_only_allowed_when_ticket_needs_information(self):
        client = self.app.test_client()
        created = client.post("/assistant/tickets/T-ASSIST-001/session")
        self.assertEqual(created.status_code, 200)
        session_id = created.get_json()["session_id"]
        reply = client.post(f"/assistant/sessions/{session_id}/messages", json={"message": "设备已经停机。"})
        self.assertEqual(reply.status_code, 200)
        with self.app.app_context():
            ticket = db.session.get(Ticket, "T-ASSIST-001")
            ticket.action_status = "CONFIRMED"
            db.session.commit()
        denied = client.post(f"/assistant/sessions/{session_id}/messages", json={"message": "补充信息。"})
        self.assertEqual(denied.status_code, 409)

    def test_draft_session_attaches_to_ticket_only_after_submission(self):
        with self.app.app_context():
            session = ConversationSession(owner_username="SYSTEM")
            db.session.add(session)
            db.session.commit()
            session_id = session.id
        response = self.app.test_client().post("/tickets/new", data={
            "equipment_type": "CNC", "equipment_model": "VF-2", "equipment_code": "", "description": "控制柜温度持续升高，风扇声音异常。",
            "occurred_at": "", "operating_state": "RUNNING", "shutdown": "NO", "safety_risk": "NO",
            "alarm_code_status": "PRESENT", "alarm_code": "253", "submitter_note": "", "assistant_session_id": session_id,
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(ConversationSession, session_id).ticket_id)


if __name__ == "__main__":
    unittest.main()
