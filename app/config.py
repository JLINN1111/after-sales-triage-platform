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
    ATTACHMENT_UPLOAD_DIR = os.getenv("ATTACHMENT_UPLOAD_DIR", str(ROOT / "本地运行数据" / "attachments"))
    MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024
    MAX_ATTACHMENTS_PER_TICKET = 5
    MAX_CONTENT_LENGTH = 26 * 1024 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 对话式信息采集助手：默认关闭，只有明确允许后才向外部模型发送脱敏文本。
    LLM_ENABLED = os.getenv("LLM_ENABLED", "false").lower() == "true"
    LLM_ALLOW_EXTERNAL_CALLS = os.getenv("LLM_ALLOW_EXTERNAL_CALLS", "false").lower() == "true"
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    LLM_DEEPSEEK_BASE_URL = os.getenv("LLM_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    LLM_DEEPSEEK_MODEL = os.getenv("LLM_DEEPSEEK_MODEL", "deepseek-v4-flash")
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    LLM_DASHSCOPE_BASE_URL = os.getenv("LLM_DASHSCOPE_BASE_URL", "")
    LLM_DASHSCOPE_MODEL = os.getenv("LLM_DASHSCOPE_MODEL", "qwen-plus")
    LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "15"))
    LLM_MAX_HISTORY_MESSAGES = int(os.getenv("LLM_MAX_HISTORY_MESSAGES", "10"))
    LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "450"))

