import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from app import db
from app.models import User, TicketOutcome, TicketOutcomeReview, TrainingCandidateReview
from app.services.access_control import ROLE_LABELS, login_required, permission_required, current_user
from app.services.feedback_export import candidate_from_outcome


TRAINING_CATEGORIES = ["ELECTRICAL_CONTROL", "MECHANICAL", "THERMAL_COOLING", "SENSOR_COMMUNICATION", "OTHER_UNKNOWN"]


auth_bp = Blueprint("auth", __name__)
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
MANAGEABLE_ROLES = set(ROLE_LABELS)


def _valid_account_input(username, password):
    if not USERNAME_PATTERN.fullmatch(username):
        return "账号须为 3 至 64 位字母、数字、下划线、短横线或点。"
    if len(password) < 12:
        return "密码至少需要 12 位。"
    return None


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


@auth_bp.get("/admin/users")
@login_required
@permission_required("user:manage")
def user_list():
    return render_template("auth/users.html", users=User.query.order_by(User.created_at.asc()).all())


@auth_bp.post("/admin/users")
@login_required
@permission_required("user:manage")
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "")
    error = _valid_account_input(username, password)
    if error:
        flash(error)
    elif role not in MANAGEABLE_ROLES:
        flash("角色取值无效。")
    elif User.query.filter_by(username=username).first():
        flash("该账号已存在。")
    else:
        user = User(username=username, role=role, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"已创建账号：{username}。")
    return redirect(url_for("auth.user_list"))


@auth_bp.post("/admin/users/<int:user_id>/role")
@login_required
@permission_required("user:manage")
def change_role(user_id):
    user = db.get_or_404(User, user_id)
    role = request.form.get("role", "")
    if role not in MANAGEABLE_ROLES:
        flash("角色取值无效。")
    elif user.id == current_user().id and role != "ADMIN":
        flash("不能取消当前登录管理员自身的管理员角色。")
    else:
        user.role = role
        db.session.commit()
        flash(f"已更新 {user.username} 的角色。")
    return redirect(url_for("auth.user_list"))


@auth_bp.post("/admin/users/<int:user_id>/status")
@login_required
@permission_required("user:manage")
def change_status(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user().id:
        flash("不能停用当前登录账号。")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        flash(f"已{'启用' if user.is_active else '停用'}账号：{user.username}。")
    return redirect(url_for("auth.user_list"))


@auth_bp.post("/admin/users/<int:user_id>/password")
@login_required
@permission_required("user:manage")
def reset_password(user_id):
    user = db.get_or_404(User, user_id)
    password = request.form.get("password", "")
    if len(password) < 12:
        flash("密码至少需要 12 位。")
    else:
        user.set_password(password)
        db.session.commit()
        flash(f"已重置账号：{user.username} 的密码。")
    return redirect(url_for("auth.user_list"))


@auth_bp.get("/admin/outcomes")
@login_required
@permission_required("outcome:approve")
def outcome_review_list():
    return render_template("auth/outcome_reviews.html", outcomes=TicketOutcome.query.order_by(TicketOutcome.recorded_at.desc()).all())


@auth_bp.post("/admin/outcomes/<int:outcome_id>/review")
@login_required
@permission_required("outcome:approve")
def review_outcome(outcome_id):
    outcome = db.get_or_404(TicketOutcome, outcome_id)
    decision = request.form.get("decision", "")
    note = request.form.get("review_note", "").strip()
    if outcome.review:
        flash("该反馈已审核，不能重复处理。")
    elif decision not in {"APPROVED", "REJECTED"} or len(note) < 10:
        flash("请选择批准或拒收，并填写不少于 10 个字的审核说明。")
    else:
        db.session.add(TicketOutcomeReview(outcome=outcome, decision=decision, review_note=note, reviewed_by=current_user().username))
        db.session.commit()
        flash("已完成反馈审核。批准项仅作为后续训练候选，不会自动训练。")
    return redirect(url_for("auth.outcome_review_list"))


@auth_bp.get("/admin/training-candidates")
@login_required
@permission_required("outcome:approve")
def training_candidate_list():
    reviews = TicketOutcomeReview.query.filter_by(decision="APPROVED").order_by(TicketOutcomeReview.reviewed_at.desc()).all()
    candidates = []
    for review in reviews:
        candidate, _reason = candidate_from_outcome(review.outcome)
        if candidate:
            candidates.append({"review": review, "candidate": candidate, "sample_review": TrainingCandidateReview.query.filter_by(outcome_review_id=review.id).first()})
    return render_template("auth/training_candidates.html", candidates=candidates, categories=TRAINING_CATEGORIES)


@auth_bp.post("/admin/training-candidates/<int:review_id>")
@login_required
@permission_required("outcome:approve")
def review_training_candidate(review_id):
    review = db.get_or_404(TicketOutcomeReview, review_id)
    decision = request.form.get("decision", "")
    category = request.form.get("reviewed_category", "")
    data_scope = request.form.get("data_scope", "")
    case_family_id = request.form.get("case_family_id", "").strip()
    note = request.form.get("review_note", "").strip()
    candidate, _reason = candidate_from_outcome(review.outcome)
    if not candidate:
        flash("该反馈不满足训练候选审核条件。")
    elif TrainingCandidateReview.query.filter_by(outcome_review_id=review.id).first():
        flash("该候选已完成样本审核。")
    elif decision not in {"ACCEPTED", "REJECTED"} or len(note) < 10 or (decision == "ACCEPTED" and (category not in TRAINING_CATEGORIES or data_scope != "COURSE_SYNTHETIC" or not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,63}", case_family_id))):
        flash("接受候选时，请确认课程虚构范围，并填写有效类别、案例家族标识和说明。")
    else:
        db.session.add(TrainingCandidateReview(outcome_review_id=review.id, decision=decision, reviewed_category=category or None, data_scope=data_scope or None, case_family_id=case_family_id or None, review_note=note, reviewed_by=current_user().username)); db.session.commit(); flash("已完成样本审核；接受项仍须版本化后才可训练。")
    return redirect(url_for("auth.training_candidate_list"))
