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
from app.models import Ticket, TicketAction  # noqa: F401  导入模型，建表时才能找到它


def init_database():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("数据库初始化完成，表已就绪。")


if __name__ == "__main__":
    init_database()
