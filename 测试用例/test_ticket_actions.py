"""客服操作状态流转、原始结果保护与留痕自动检验。"""

import tempfile
import unittest
import re
from pathlib import Path
from unittest.mock import patch

from app import create_app, db
from app.models import Ticket, TicketAction, TicketOutcome, TicketOutcomeReview, TrainingCandidateReview, User
from app.services.ticket_actions import apply_ticket_action, initial_action_status


class TicketActionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "actions.db"
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
            "LLM_ENABLED": False,
            "LLM_ALLOW_EXTERNAL_CALLS": False,
            "CSRF_ENABLED": False,
            "AUTH_ENABLED": False,
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

    def test_ticket_list_displays_chinese_action_status(self):
        """列表页只展示中文状态，不暴露内部状态码。"""
        with self.app.app_context():
            ticket = self.get_ticket()
            ticket.action_status = "HUMAN_REVIEW"
            db.session.commit()

        response = self.app.test_client().get("/tickets")

        self.assertEqual(response.status_code, 200)
        self.assertIn("人工复核中".encode("utf-8"), response.data)
        self.assertNotIn(b"HUMAN_REVIEW", response.data)

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

    def test_llm_reference_endpoint_is_disabled_without_explicit_enablement(self):
        safe_rules_result = {
            "predicted_category": "THERMAL_COOLING",
            "recommend_human": False,
            "missing_fields": [],
        }
        with patch("app.routes.tickets.triage_ticket", return_value=safe_rules_result):
            response = self.app.test_client().post("/tickets/T-ACTION-001/llm-reference")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "DISABLED")
        self.assertIsNone(response.get_json()["reference"])
        with self.app.app_context():
            audit = TicketAction.query.filter_by(action_type="LLM_REFERENCE").one()
            self.assertEqual(audit.action_by, "SYSTEM")
            self.assertEqual(audit.new_values["llm_status"], "DISABLED")
            self.assertNotIn(self.get_ticket().description, str(audit.new_values))

    def test_llm_reference_success_has_per_ticket_cooldown_and_safe_audit(self):
        self.app.config.update(
            LLM_ENABLED=True,
            LLM_ALLOW_EXTERNAL_CALLS=True,
            LLM_PROVIDER="deepseek",
            LLM_REFERENCE_COOLDOWN_SECONDS=60,
        )
        safe_rules_result = {
            "predicted_category": "THERMAL_COOLING",
            "recommend_human": False,
            "missing_fields": [],
        }
        reference = {
            "status": "REFERENCE",
            "reasons": ["仅供客服参考，仍需人工确认"],
            "reference": {"reference_category": "THERMAL_COOLING"},
        }
        with patch("app.routes.tickets.triage_ticket", return_value=safe_rules_result), patch(
            "app.routes.tickets.guarded_llm_reference", return_value=reference
        ) as guarded:
            client = self.app.test_client()
            first = client.post("/tickets/T-ACTION-001/llm-reference")
            second = client.post("/tickets/T-ACTION-001/llm-reference")
        self.assertEqual(first.get_json()["status"], "REFERENCE")
        self.assertEqual(second.get_json()["status"], "BLOCKED")
        self.assertEqual(guarded.call_count, 1)
        with self.app.app_context():
            audits = TicketAction.query.filter_by(action_type="LLM_REFERENCE").all()
            self.assertEqual([item.new_values["llm_status"] for item in audits], ["REFERENCE", "BLOCKED"])
            self.assertTrue(all(self.get_ticket().description not in str(item.new_values) for item in audits))

    def test_detail_explains_when_deepseek_is_not_enabled(self):
        response = self.app.test_client().get("/tickets/T-ACTION-001")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DeepSeek 客服参考".encode("utf-8"), response.data)
        self.assertIn("尚未在本机启用".encode("utf-8"), response.data)
        self.assertNotIn(b"llm-reference-button", response.data)

    def test_detail_shows_manual_deepseek_button_only_when_eligible(self):
        self.app.config.update(LLM_ENABLED=True, LLM_ALLOW_EXTERNAL_CALLS=True, LLM_PROVIDER="deepseek")
        response = self.app.test_client().get("/tickets/T-ACTION-001")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"llm-reference-button", response.data)
        self.assertIn("仅供人工客服参考".encode("utf-8"), response.data)

    def test_detail_hides_deepseek_button_for_safety_risk(self):
        self.app.config.update(LLM_ENABLED=True, LLM_ALLOW_EXTERNAL_CALLS=True, LLM_PROVIDER="deepseek")
        with self.app.app_context():
            ticket = self.get_ticket()
            ticket.safety_risk = "YES"
            ticket.recommend_human = True
            db.session.commit()
        response = self.app.test_client().get("/tickets/T-ACTION-001")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"llm-reference-button", response.data)
        self.assertIn("安全风险需要人工确认".encode("utf-8"), response.data)

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

class CsrfProtectionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "csrf.db"
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
            "CSRF_ENABLED": True,
            "AUTH_ENABLED": False,
        })
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.tempdir.cleanup()

    def test_rejects_post_without_csrf_token(self):
        response = self.app.test_client().post("/tickets/new", data={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("请求校验失败".encode("utf-8"), response.data)

    def test_accepts_form_post_with_token_from_page(self):
        client = self.app.test_client()
        page = client.get("/tickets/new")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = client.post("/tickets/new", data={
            "csrf_token": token,
            "equipment_type": "CNC",
            "equipment_model": "VF-2",
            "equipment_code": "CSRF-001",
            "description": "控制柜温度过高，冷却风扇异常。",
            "occurred_at": "",
            "operating_state": "RUNNING",
            "shutdown": "NO",
            "safety_risk": "NO",
            "alarm_code_status": "PRESENT",
            "alarm_code": "253",
            "submitter_note": "",
        })
        self.assertEqual(response.status_code, 302)


class AccessControlTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "access.db"
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "access-test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
            "CSRF_ENABLED": True,
            "AUTH_ENABLED": True,
        })
        with self.app.app_context():
            db.create_all()
            agent = User(username="agent01", role="AGENT", is_active=True)
            agent.set_password("safe-test-password")
            db.session.add(agent)
            admin = User(username="admin01", role="ADMIN", is_active=True)
            admin.set_password("admin-test-password")
            db.session.add(admin)
            db.session.add(Ticket(
                ticket_id="T-ACCESS-001", equipment_type="CNC",
                description="控制柜温度过高，冷却风扇异常。", operating_state="RUNNING",
                shutdown="NO", safety_risk="NO", alarm_code_status="PRESENT", alarm_code="253",
                predicted_category="THERMAL_COOLING", priority="NORMAL", action_status="NEW",
            ))
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.tempdir.cleanup()

    def login_agent(self, client):
        self.login(client, "agent01", "safe-test-password")

    def login(self, client, username, password):
        page = client.get("/login")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = client.post("/login", data={
            "csrf_token": token, "username": username, "password": password,
        })
        self.assertEqual(response.status_code, 302)

    def test_login_required_for_ticket_list(self):
        response = self.app.test_client().get("/tickets")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_agent_cannot_confirm_but_action_history_uses_logged_in_account(self):
        client = self.app.test_client()
        self.login_agent(client)
        detail = client.get("/tickets/T-ACCESS-001")
        token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', detail.data).group(1).decode()
        denied = client.post(
            "/tickets/T-ACCESS-001/actions",
            json={"action_type": "CONFIRM", "action_by": "forged", "confirmed_category": "THERMAL_COOLING", "confirmed_priority": "NORMAL"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(denied.status_code, 403)
        allowed = client.post(
            "/tickets/T-ACCESS-001/actions",
            json={"action_type": "FOLLOW_UP", "action_by": "forged", "customer_follow_up": "请补充设备型号。"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(allowed.status_code, 200)
        with self.app.app_context():
            self.assertEqual(TicketAction.query.one().action_by, "agent01")

    def test_only_admin_can_manage_accounts_and_password_is_hashed(self):
        agent_client = self.app.test_client()
        self.login_agent(agent_client)
        self.assertEqual(agent_client.get("/admin/users").status_code, 302)

        admin_client = self.app.test_client()
        self.login(admin_client, "admin01", "admin-test-password")
        page = admin_client.get("/admin/users")
        self.assertEqual(page.status_code, 200)
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        created = admin_client.post("/admin/users", data={
            "csrf_token": token, "username": "reviewer01", "password": "reviewer-password", "role": "REVIEWER",
        })
        self.assertEqual(created.status_code, 302)
        with self.app.app_context():
            user = User.query.filter_by(username="reviewer01").one()
            self.assertEqual(user.role, "REVIEWER")
            self.assertNotEqual(user.password_hash, "reviewer-password")
            self.assertTrue(user.verify_password("reviewer-password"))

    def test_reviewer_can_record_outcome_but_agent_cannot(self):
        with self.app.app_context():
            reviewer = User(username="reviewer02", role="REVIEWER", is_active=True)
            reviewer.set_password("reviewer-test-password")
            ticket = db.session.get(Ticket, "T-ACCESS-001")
            ticket.action_status = "CONFIRMED"
            db.session.add(reviewer)
            db.session.commit()
        agent = self.app.test_client()
        self.login_agent(agent)
        page = agent.get("/tickets/T-ACCESS-001")
        token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
        denied = agent.post("/tickets/T-ACCESS-001/outcomes", data={"csrf_token": token, "final_category": "THERMAL_COOLING", "resolution_status": "RESOLVED", "resolution_note": "现场确认冷却风扇更换后恢复正常。"})
        self.assertEqual(denied.status_code, 302)
        reviewer = self.app.test_client()
        self.login(reviewer, "reviewer02", "reviewer-test-password")
        page = reviewer.get("/tickets/T-ACCESS-001")
        token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
        saved = reviewer.post("/tickets/T-ACCESS-001/outcomes", data={"csrf_token": token, "final_category": "THERMAL_COOLING", "resolution_status": "RESOLVED", "resolution_note": "现场确认冷却风扇更换后恢复正常。"})
        self.assertEqual(saved.status_code, 302)
        with self.app.app_context():
            self.assertEqual(TicketOutcome.query.one().recorded_by, "reviewer02")

    def test_admin_reviews_outcome_once_without_training_model(self):
        with self.app.app_context():
            ticket = db.session.get(Ticket, "T-ACCESS-001")
            outcome = TicketOutcome(ticket=ticket, final_category="THERMAL_COOLING", resolution_status="RESOLVED", resolution_note="现场确认冷却风扇更换后恢复正常。", recorded_by="reviewer02")
            db.session.add(outcome)
            db.session.commit()
            outcome_id = outcome.id
        client = self.app.test_client()
        self.login(client, "admin01", "admin-test-password")
        page = client.get("/admin/outcomes")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = client.post(f"/admin/outcomes/{outcome_id}/review", data={"csrf_token": token, "decision": "APPROVED", "review_note": "已核对处理依据，允许进入后续训练候选审核。"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            review = TicketOutcomeReview.query.one()
            self.assertEqual(review.decision, "APPROVED")
            self.assertEqual(review.reviewed_by, "admin01")
        repeated = client.post(f"/admin/outcomes/{outcome_id}/review", data={"csrf_token": token, "decision": "REJECTED", "review_note": "重复审核不应覆盖已有结论。"})
        self.assertEqual(repeated.status_code, 302)
        with self.app.app_context():
            self.assertEqual(TicketOutcomeReview.query.count(), 1)

    def test_admin_can_accept_training_candidate_once(self):
        with self.app.app_context():
            ticket = db.session.get(Ticket, "T-ACCESS-001")
            outcome = TicketOutcome(ticket=ticket, final_category="THERMAL_COOLING", resolution_status="RESOLVED", resolution_note="现场确认冷却风扇更换后恢复正常。", recorded_by="reviewer02")
            db.session.add(outcome); db.session.commit()
            review = TicketOutcomeReview(outcome=outcome, decision="APPROVED", review_note="允许进入后续训练候选审核。", reviewed_by="admin01")
            db.session.add(review); db.session.commit(); review_id = review.id
        client = self.app.test_client(); self.login(client, "admin01", "admin-test-password")
        page = client.get("/admin/training-candidates")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = client.post(f"/admin/training-candidates/{review_id}", data={"csrf_token": token, "decision": "ACCEPTED", "reviewed_category": "THERMAL_COOLING", "review_note": "文本和类别经人工复核，可作为正式样本候选。"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            candidate = TrainingCandidateReview.query.one()
            self.assertEqual(candidate.decision, "ACCEPTED")
            self.assertEqual(candidate.reviewed_category, "THERMAL_COOLING")
        repeated = client.post(f"/admin/training-candidates/{review_id}", data={"csrf_token": token, "decision": "REJECTED", "review_note": "重复审核不得覆盖已经完成的样本结论。"})
        self.assertEqual(repeated.status_code, 302)
        with self.app.app_context():
            self.assertEqual(TrainingCandidateReview.query.count(), 1)

    def test_training_candidate_page_redacts_description_and_allows_category_revision(self):
        with self.app.app_context():
            ticket = db.session.get(Ticket, "T-ACCESS-001")
            ticket.description = "请联系13800138000，控制柜风扇异常。"
            outcome = TicketOutcome(ticket=ticket, final_category="THERMAL_COOLING", resolution_status="RESOLVED", resolution_note="现场确认风扇更换后恢复正常。", recorded_by="reviewer02")
            review = TicketOutcomeReview(outcome=outcome, decision="APPROVED", review_note="允许进入后续训练候选审核。", reviewed_by="admin01")
            db.session.add_all([outcome, review]); db.session.commit(); review_id = review.id
        client = self.app.test_client(); self.login(client, "admin01", "admin-test-password")
        page = client.get("/admin/training-candidates")
        self.assertNotIn(b"13800138000", page.data)
        self.assertIn(b"[PHONE_REDACTED]", page.data)
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = client.post(f"/admin/training-candidates/{review_id}", data={"csrf_token": token, "decision": "ACCEPTED", "reviewed_category": "MECHANICAL", "review_note": "人工复核后修订类别，可作为正式样本候选。"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(TrainingCandidateReview.query.one().reviewed_category, "MECHANICAL")

    def test_training_candidate_review_requires_admin_and_eligible_feedback(self):
        with self.app.app_context():
            ticket = db.session.get(Ticket, "T-ACCESS-001")
            outcome = TicketOutcome(ticket=ticket, final_category="THERMAL_COOLING", resolution_status="PENDING", resolution_note="尚待现场确认。", recorded_by="reviewer02")
            review = TicketOutcomeReview(outcome=outcome, decision="APPROVED", review_note="允许进入后续训练候选审核。", reviewed_by="admin01")
            db.session.add_all([outcome, review]); db.session.commit(); review_id = review.id
        agent = self.app.test_client(); self.login_agent(agent)
        self.assertEqual(agent.get("/admin/training-candidates").status_code, 302)
        admin = self.app.test_client(); self.login(admin, "admin01", "admin-test-password")
        page = admin.get("/admin/training-candidates")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = admin.post(f"/admin/training-candidates/{review_id}", data={"csrf_token": token, "decision": "ACCEPTED", "reviewed_category": "THERMAL_COOLING", "review_note": "不满足条件的反馈不得形成训练候选审核。"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(TrainingCandidateReview.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
