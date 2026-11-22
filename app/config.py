import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

# 仅加载本机未纳入版本控制的配置文件；已存在的系统环境变量优先。
load_dotenv(ROOT / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "local-development-only")
    CSRF_ENABLED = os.getenv("CSRF_ENABLED", "true").lower() == "true"
    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "")
    BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{ROOT / '本地运行数据' / 'triage.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

