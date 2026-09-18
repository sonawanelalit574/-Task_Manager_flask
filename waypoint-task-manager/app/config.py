import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
    WTF_CSRF_TIME_LIMIT = None
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'waypoint.sqlite3'}")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = database_url
