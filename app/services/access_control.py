"""本地账户、会话与最小角色权限。服务端权限校验不能由页面隐藏替代。"""

from functools import wraps

from flask import current_app, flash, g, jsonify, redirect, request, session, url_for

from app import db
from app.models import User


ROLE_LABELS = {
    "ADMIN": "平台管理员",
    "AGENT": "报修业务人员",
    "REVIEWER": "售后处理人员",
}

ROLE_PERMISSIONS = {
    "ADMIN": {"ticket:view", "ticket:submit", "ticket:follow_up", "ticket:review", "ticket:delete", "outcome:record", "user:manage"},
    "AGENT": {"ticket:view", "ticket:submit", "ticket:supplement"},
    "REVIEWER": {"ticket:view", "ticket:follow_up", "ticket:review", "outcome:record"},
}

ACTION_PERMISSIONS = {
    "FOLLOW_UP": "ticket:follow_up",
    "SUPPLEMENT": "ticket:supplement",
    "HANDOFF": "ticket:follow_up",
    "CONFIRM": "ticket:review",
    "EDIT": "ticket:review",
    "CLOSE": "ticket:review",
}


def auth_enabled() -> bool:
    return bool(current_app.config.get("AUTH_ENABLED", True))


def current_user():
    return getattr(g, "current_user", None)


def can(permission: str) -> bool:
    if not auth_enabled():
        return True
    user = current_user()
    return bool(user and user.is_active and permission in ROLE_PERMISSIONS.get(user.role, set()))


def can_action(action_type: str) -> bool:
    return can(ACTION_PERMISSIONS.get(action_type, ""))


def can_access_ticket(ticket) -> bool:
    """报修业务人员只可查看或补充自己提交的工单。"""

    if not auth_enabled():
        return True
    user = current_user()
    if not user or not user.is_active:
        return False
    if user.role != "AGENT":
        return can("ticket:view")
    return ticket.submitted_by == user.username


def _deny_login():
    if request.is_json:
        return jsonify({"error": "请先登录。"}), 401
    flash("请先登录后再继续。")
    return redirect(url_for("auth.login"))


def _deny_permission():
    if request.is_json:
        return jsonify({"error": "当前角色无权执行此操作。"}), 403
    flash("当前角色无权执行此操作。")
    return redirect(url_for("tickets.list_tickets"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not auth_enabled():
            return view(*args, **kwargs)
        if current_user() is None:
            return _deny_login()
        return view(*args, **kwargs)
    return wrapped


def permission_required(permission: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if auth_enabled() and not can(permission):
                return _deny_permission()
            return view(*args, **kwargs)
        return wrapped
    return decorator


def action_permission_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if auth_enabled():
            payload = request.get_json(silent=True) if request.is_json else request.form
            action_type = (payload or {}).get("action_type", "")
            if not can_action(action_type):
                return _deny_permission()
        return view(*args, **kwargs)
    return wrapped


def init_access_control(app):
    @app.before_request
    def load_current_user():
        g.current_user = None
        if not auth_enabled():
            return None
        user_id = session.get("user_id")
        if user_id:
            user = db.session.get(User, user_id)
            if user and user.is_active:
                g.current_user = user
            else:
                session.pop("user_id", None)
        return None

    @app.context_processor
    def inject_access_control():
        return {
            "current_user": current_user(),
            "role_labels": ROLE_LABELS,
            "can": can,
            "can_action": can_action,
            "auth_enabled": auth_enabled(),
        }
