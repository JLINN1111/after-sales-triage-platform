"""客服操作状态流转、原始结果保护与留痕自动检验。"""

import tempfile
import unittest
from pathlib import Path

from app import create_app, db
from app.models import Ticket, TicketAction
from app.services.ticket_actions import apply_ticket_action, initial_action_status


class TicketActionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "actions.db"
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        })
        with self.app.app_context():
            db.create_all()
            self.ticket = Ticket(
                ticket_id="T-ACTION-001",
                equipment_type="CNC",
                description="控制柜温度过高，风扇异常。",
                operating_state="RUNNING",
                shutdown="NO",
                safety_risk="NO",
                alarm_code_status="PRESENT",
                alarm_code="253",
                predicted_category="THERMAL_COOLING",
                priority="NORMAL",
                action_status="NEW",
            )
            db.session.add(self.ticket)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.tempdir.cleanup()

    def get_ticket(self):
        return db.session.get(Ticket, "T-ACTION-001")

    def test_initial_status_respects_manual_and_missing_flags(self):
        self.assertEqual(initial_action_status({"recommend_human": True}), "HUMAN_REVIEW")
        self.assertEqual(initial_action_status({"recommend_human": False, "missing_fields": ["equipment_model"]}), "NEED_INFO")
        self.assertEqual(initial_action_status({"recommend_human": False, "missing_fields": []}), "NEW")

    def test_confirm_preserves_system_result_and_writes_history(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            action = apply_ticket_action(ticket, {
                "action_type": "CONFIRM",
                "action_by": "demo-agent-01",
                "confirmed_category": "THERMAL_COOLING",
                "confirmed_priority": "NORMAL",
            })
            db.session.add(action)
            db.session.commit()
            saved = self.get_ticket()
            self.assertEqual(saved.action_status, "CONFIRMED")
            self.assertEqual(saved.predicted_category, "THERMAL_COOLING")
            self.assertEqual(saved.confirmed_category, "THERMAL_COOLING")
            self.assertEqual(TicketAction.query.count(), 1)

    def test_edit_requires_reason_and_keeps_original_prediction(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            db.session.add(apply_ticket_action(ticket, {
                "action_type": "CONFIRM", "action_by": "demo-agent-01",
                "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "NORMAL",
            }))
            db.session.commit()
            with self.assertRaisesRegex(ValueError, "修订时必须填写原因"):
                apply_ticket_action(self.get_ticket(), {
                    "action_type": "EDIT", "action_by": "demo-agent-01",
                    "confirmed_priority": "HIGH",
                })
            action = apply_ticket_action(self.get_ticket(), {
                "action_type": "EDIT", "action_by": "demo-agent-01",
                "confirmed_priority": "HIGH", "action_note": "客服补充现场影响范围后调整。",
            })
            db.session.add(action)
            db.session.commit()
            saved = self.get_ticket()
            self.assertEqual(saved.predicted_category, "THERMAL_COOLING")
            self.assertEqual(saved.confirmed_priority, "HIGH")
            self.assertEqual(TicketAction.query.count(), 2)

    def test_follow_up_writes_question_and_sets_need_info(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            db.session.add(apply_ticket_action(ticket, {
                "action_type": "FOLLOW_UP", "action_by": "客服001",
                "customer_follow_up": "请补充设备型号和报警代码。",
            }))
            db.session.commit()
            saved = self.get_ticket()
            self.assertEqual(saved.action_status, "NEED_INFO")
            self.assertEqual(saved.customer_follow_up, "请补充设备型号和报警代码。")
            self.assertEqual(TicketAction.query.one().action_type, "FOLLOW_UP")

    def test_human_review_confirmation_requires_note(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            ticket.action_status = "HUMAN_REVIEW"
            ticket.safety_risk = "YES"
            ticket.priority = "URGENT"
            db.session.commit()
            with self.assertRaisesRegex(ValueError, "必须填写核对说明"):
                apply_ticket_action(self.get_ticket(), {
                    "action_type": "CONFIRM", "action_by": "客服001",
                    "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "URGENT",
                })

    def test_risky_ticket_requires_handoff_before_close(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            ticket.safety_risk = "YES"
            ticket.action_status = "HUMAN_REVIEW"
            db.session.commit()
            db.session.add(apply_ticket_action(ticket, {
                "action_type": "CONFIRM", "action_by": "demo-agent-01",
                "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "URGENT",
                "action_note": "存在安全风险，需人工处理。",
            }))
            db.session.commit()
            with self.assertRaisesRegex(ValueError, "必须先记录转人工处理"):
                apply_ticket_action(self.get_ticket(), {
                    "action_type": "CLOSE", "action_by": "demo-agent-01", "action_note": "关闭。",
                })
            db.session.add(apply_ticket_action(self.get_ticket(), {
                "action_type": "HANDOFF", "action_by": "demo-agent-01", "action_note": "已转现场安全人员。",
            }))
            db.session.commit()
            db.session.add(apply_ticket_action(self.get_ticket(), {
                "action_type": "CONFIRM", "action_by": "demo-agent-01",
                "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "URGENT",
                "action_note": "人工处理结论已核对。",
            }))
            db.session.commit()
            db.session.add(apply_ticket_action(self.get_ticket(), {
                "action_type": "CLOSE", "action_by": "demo-agent-01", "action_note": "客服流程已完成。",
            }))
            db.session.commit()
            self.assertEqual(self.get_ticket().action_status, "CLOSED")

    def test_api_rejects_direct_close_from_new(self):
        client = self.app.test_client()
        response = client.post("/tickets/T-ACTION-001/actions", json={
            "action_type": "CLOSE", "action_by": "demo-agent-01", "action_note": "关闭。",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("当前状态不允许", response.get_json()["error"])

    def test_detail_displays_action_history(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            db.session.add(apply_ticket_action(ticket, {
                "action_type": "HANDOFF", "action_by": "客服001", "action_note": "停机状态需要现场核对。",
            }))
            db.session.commit()
        response = self.app.test_client().get("/tickets/T-ACTION-001")
        self.assertEqual(response.status_code, 200)
        self.assertIn("操作历史".encode("utf-8"), response.data)
        self.assertIn("转人工处理".encode("utf-8"), response.data)
        self.assertIn("客服001".encode("utf-8"), response.data)

    def test_history_does_not_repeat_follow_up_content_for_confirmation(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            db.session.add(apply_ticket_action(ticket, {
                "action_type": "FOLLOW_UP", "action_by": "客服001",
                "customer_follow_up": "请补充现场照片。",
            }))
            db.session.commit()
            db.session.add(apply_ticket_action(self.get_ticket(), {
                "action_type": "CONFIRM", "action_by": "客服001",
                "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "NORMAL",
            }))
            db.session.commit()
        response = self.app.test_client().get("/tickets/T-ACTION-001")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count("请补充现场照片。".encode("utf-8")), 1)

    def test_form_follow_up_redirects_and_saves_history(self):
        response = self.app.test_client().post("/tickets/T-ACTION-001/actions", data={
            "action_type": "FOLLOW_UP", "action_by": "客服001",
            "customer_follow_up": "请补充设备型号和报警代码。",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            saved = self.get_ticket()
            self.assertEqual(saved.action_status, "NEED_INFO")
            self.assertEqual(saved.customer_follow_up, "请补充设备型号和报警代码。")

    def test_supplement_retriages_without_overwriting_original_ticket(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            ticket.equipment_model = None
            ticket.operating_state = "UNKNOWN"
            ticket.shutdown = "UNKNOWN"
            ticket.safety_risk = "UNKNOWN"
            ticket.alarm_code_status = "UNKNOWN"
            ticket.alarm_code = None
            ticket.action_status = "NEED_INFO"
            db.session.commit()
        response = self.app.test_client().post("/tickets/T-ACTION-001/actions", data={
            "action_type": "SUPPLEMENT", "action_by": "客服001",
            "equipment_model": "VF-2", "operating_state": "RUNNING",
            "shutdown": "NO", "safety_risk": "NO",
            "alarm_code_status": "PRESENT", "alarm_code": "253",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            saved = self.get_ticket()
            self.assertIsNone(saved.equipment_model)
            self.assertEqual(saved.operating_state, "UNKNOWN")
            action = TicketAction.query.one()
            self.assertEqual(action.action_type, "SUPPLEMENT")
            self.assertEqual(action.new_values["supplemental_fields"]["equipment_model"], "VF-2")
            self.assertEqual(saved.action_status, "HUMAN_REVIEW")

    def test_supplement_history_displays_customer_values(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            ticket.action_status = "NEED_INFO"
            db.session.commit()
        self.app.test_client().post("/tickets/T-ACTION-001/actions", data={
            "action_type": "SUPPLEMENT", "action_by": "客服001", "shutdown": "NO",
        })
        response = self.app.test_client().get("/tickets/T-ACTION-001")
        self.assertEqual(response.status_code, 200)
        self.assertIn("是否停机：否".encode("utf-8"), response.data)

    def test_action_success_message_is_shown_on_detail_page(self):
        response = self.app.test_client().post("/tickets/T-ACTION-001/actions", data={
            "action_type": "HANDOFF", "action_by": "客服001", "action_note": "需要人工核对。",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("客服操作已保存。".encode("utf-8"), response.data)

    def test_form_confirm_redirects_and_saves_confirmation(self):
        response = self.app.test_client().post("/tickets/T-ACTION-001/actions", data={
            "action_type": "CONFIRM", "action_by": "客服001",
            "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "NORMAL",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            saved = self.get_ticket()
            self.assertEqual(saved.action_status, "CONFIRMED")
            self.assertEqual(saved.confirmed_category, "THERMAL_COOLING")
            self.assertEqual(saved.confirmed_priority, "NORMAL")

    def test_form_edit_requires_confirmed_status_and_saves_change(self):
        client = self.app.test_client()
        client.post("/tickets/T-ACTION-001/actions", data={
            "action_type": "CONFIRM", "action_by": "客服001",
            "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "NORMAL",
        })
        response = client.post("/tickets/T-ACTION-001/actions", data={
            "action_type": "EDIT", "action_by": "客服001",
            "confirmed_priority": "HIGH", "action_note": "补充现场影响范围后提高优先级。",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            saved = self.get_ticket()
            self.assertEqual(saved.action_status, "CONFIRMED")
            self.assertEqual(saved.confirmed_priority, "HIGH")
            self.assertEqual(TicketAction.query.count(), 2)

    def test_form_close_redirects_after_confirmation(self):
        client = self.app.test_client()
        client.post("/tickets/T-ACTION-001/actions", data={
            "action_type": "CONFIRM", "action_by": "客服001",
            "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "NORMAL",
        })
        response = client.post("/tickets/T-ACTION-001/actions", data={
            "action_type": "CLOSE", "action_by": "客服001", "action_note": "客户已确认处理完成。",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            saved = self.get_ticket()
            self.assertEqual(saved.action_status, "CLOSED")
            self.assertEqual(TicketAction.query.count(), 2)

    def test_detail_hides_close_form_until_risky_ticket_is_handed_off(self):
        with self.app.app_context():
            ticket = self.get_ticket()
            ticket.safety_risk = "YES"
            ticket.action_status = "CONFIRMED"
            db.session.commit()
        response = self.app.test_client().get("/tickets/T-ACTION-001")
        self.assertEqual(response.status_code, 200)
        self.assertIn("关闭前必须先记录“转人工处理”".encode("utf-8"), response.data)
        self.assertNotIn(b'name="action_type" value="CLOSE"', response.data)


if __name__ == "__main__":
    unittest.main()
