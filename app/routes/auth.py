from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from app import db
from app.models import User
from app.services.access_control import ROLE_LABELS


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if not current_app.config.get("AUTH_ENABLED", True):
        return redirect(url_for("tickets.list_tickets"))
    if request.method == "GET":
        return render_template("auth/login.html", no_account=(User.query.count() == 0))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = User.query.filter_by(username=username).first()
    if not user or not user.is_active or not user.verify_password(password):
        flash("账号或密码不正确，或账号已停用。")
        return render_template("auth/login.html", no_account=False), 401
    session.clear()
    session["user_id"] = user.id
    flash(f"已登录：{user.username}（{ROLE_LABELS.get(user.role, user.role)}）。")
    return redirect(url_for("tickets.list_tickets"))


@auth_bp.post("/logout")
def logout():
    session.clear()
    flash("已退出登录。")
    return redirect(url_for("auth.login"))
