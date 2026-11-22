"""初始化 SQLite 数据库：创建工单表。

用法（在仓库根目录、虚拟环境已激活时）：
    python 运行脚本/init_db.py

说明：
- 创建业务表，并在首次运行时导入仓库随附的公开知识资料。
- 数据库文件位置由 app/config.py 的 SQLALCHEMY_DATABASE_URI 决定。
- 重复执行不会报错，已存在的表会被保留，不会清空数据。
"""

import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app, db
from app.models import KnowledgeEntry, Ticket, TicketAction, TicketAttachment, TicketOutcome, User  # noqa: F401  导入模型，建表时才能找到它
from app.services.knowledge_matcher import seed_public_knowledge


def init_database():
    app = create_app()
    with app.app_context():
        db.create_all()
        seeded_count = seed_public_knowledge()
        if seeded_count:
            print(f"已导入 {seeded_count} 条公开知识资料，后续可在知识库管理页维护。")
        columns = {column["name"] for column in inspect(db.engine).get_columns("tickets")}
        if "submitted_by" not in columns:
            db.session.execute(text("ALTER TABLE tickets ADD COLUMN submitted_by VARCHAR(64)"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_tickets_submitted_by ON tickets (submitted_by)"))
            db.session.execute(text("UPDATE tickets SET submitted_by = 'SYSTEM' WHERE submitted_by IS NULL"))
            db.session.commit()
            print("已补建工单提交人字段，并将既有工单标记为系统历史记录。")
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
