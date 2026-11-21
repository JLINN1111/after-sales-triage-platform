"""已批准反馈的本地训练候选导出；不训练、不上传，也不替代人工审核。"""

from app.algorithms.deidentification import redact_sensitive_patterns


ALLOWED_RESOLUTION = {"RESOLVED"}


def candidate_from_outcome(outcome):
    """返回安全候选或拒收原因；只允许已批准、已解决、字段完整的反馈。"""
    review = getattr(outcome, "review", None)
    if not review or review.decision != "APPROVED":
        return None, "未获管理员批准"
    if outcome.resolution_status not in ALLOWED_RESOLUTION:
        return None, "处理结果非已解决"
    ticket = outcome.ticket
    if not outcome.final_category or not ticket or not (ticket.description or "").strip():
        return None, "类别或故障描述不完整"
    description, patterns = redact_sensitive_patterns(ticket.description)
    if "CHINA_ID" in patterns:
        return None, "描述含身份证号码，需人工脱敏后再处理"
    return {
        "source_outcome_id": outcome.id,
        "description": description,
        "category": outcome.final_category,
        "reviewed_at": review.reviewed_at.isoformat(),
        "sensitive_patterns_redacted": ";".join(patterns),
        "candidate_status": "待人工样本审核",
    }, None
