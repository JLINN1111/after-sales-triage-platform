import hmac
import secrets

from flask import Flask, abort, redirect, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from app.config import Config

db = SQLAlchemy()


def create_app(config_overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    db.init_app(app)

    from app.models import User  # noqa: F401  确保初始化数据库时包含账户表。
    from app.services.access_control import init_access_control

    def csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": csrf_token}

    @app.before_request
    def protect_unsafe_requests():
        if not app.config.get("CSRF_ENABLED", True):
            return None
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        expected = session.get("csrf_token")
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="请求校验失败，请刷新页面后重试。")
        return None

    init_access_control(app)

    @app.get("/")
    def index():
        return redirect(url_for("tickets.list_tickets"))

    from app.routes.auth import auth_bp
    from app.routes.assistant import assistant_bp
    from app.routes.knowledge import knowledge_bp
    from app.routes.tickets import tickets_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(tickets_bp)

    return app
