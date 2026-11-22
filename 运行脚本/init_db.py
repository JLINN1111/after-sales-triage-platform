"""初始化 SQLite 数据库：创建工单表。

用法（在仓库根目录、虚拟环境已激活时）：
    python 运行脚本/init_db.py

说明：
- 只负责建表，不写入任何演示数据。
- 数据库文件位置由 app/config.py 的 SQLALCHEMY_DATABASE_URI 决定。
- 重复执行不会报错，已存在的表会被保留，不会清空数据。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app, db
from app.models import Ticket, TicketAction, TicketOutcome, TicketOutcomeReview, TrainingCandidateReview, User  # noqa: F401  导入模型，建表时才能找到它


def ensure_training_candidate_review_columns():
    """为已存在的 SQLite 候选审核表补齐不可自动推断的审核字段。"""
    if db.engine.dialect.name != "sqlite":
        return
    columns = {row[1] for row in db.session.connection().exec_driver_sql("PRAGMA table_info(training_candidate_reviews)")}
    for name in ("data_scope", "case_family_id"):
        if name not in columns:
            db.session.connection().exec_driver_sql(f"ALTER TABLE training_candidate_reviews ADD COLUMN {name} VARCHAR(64)")


def init_database():
    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_training_candidate_review_columns()
        if User.query.count() == 0:
            username = app.config["BOOTSTRAP_ADMIN_USERNAME"].strip()
            password = app.config["BOOTSTRAP_ADMIN_PASSWORD"]
            if username and password:
                admin = User(username=username, role="ADMIN", is_active=True)
                admin.set_password(password)
                db.session.add(admin)
                db.session.commit()
                print(f"已创建初始平台管理员账号：{username}")
            else:
                print("尚未创建管理员账号：请先在本机 .env 设置 BOOTSTRAP_ADMIN_USERNAME 和 BOOTSTRAP_ADMIN_PASSWORD 后再次运行本脚本。")
        print("数据库初始化完成，表已就绪。")


if __name__ == "__main__":
    init_database()
