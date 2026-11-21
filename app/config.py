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
    # 外部大模型默认关闭；密钥只从本机环境变量读取，不写入仓库或数据库。
    LLM_ENABLED = os.getenv("LLM_ENABLED", "false").lower() == "true"
    LLM_ALLOW_EXTERNAL_CALLS = os.getenv("LLM_ALLOW_EXTERNAL_CALLS", "false").lower() == "true"
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "disabled").lower()
    LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "12"))
    LLM_ALIYUN_BASE_URL = os.getenv("LLM_ALIYUN_BASE_URL", "").rstrip("/")
    LLM_ALIYUN_MODEL = os.getenv("LLM_ALIYUN_MODEL", "qwen-plus")
    LLM_DEEPSEEK_BASE_URL = os.getenv("LLM_DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    LLM_DEEPSEEK_MODEL = os.getenv("LLM_DEEPSEEK_MODEL", "deepseek-flash")
    LLM_REFERENCE_COOLDOWN_SECONDS = int(os.getenv("LLM_REFERENCE_COOLDOWN_SECONDS", "60"))

