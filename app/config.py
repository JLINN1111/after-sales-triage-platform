import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "local-development-only")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{ROOT / 'instance' / 'triage.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
