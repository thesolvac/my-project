"""
Application Configuration
==========================
All settings are read from environment variables with sensible defaults.
Copy .env.example to .env and fill in values before running in production.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()   # reads .env if present

_BASE = Path(__file__).resolve().parent


class Config:
    # ── Security ──────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-insecure-key-change-in-prod")

    # ── MongoDB ───────────────────────────────────────────────────────────
    MONGO_URI:     str = os.getenv("MONGO_URI",     "mongodb://localhost:27017/")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "apme_db")

    # ── Uploads ───────────────────────────────────────────────────────────
    UPLOAD_FOLDER:      Path = _BASE / "uploads"
    MAX_CONTENT_LENGTH: int  = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
    ALLOWED_EXTENSIONS: set  = {"txt", "log", "csv", "md", "json", "xml", "py", "js", "html"}

    # ── Flask ─────────────────────────────────────────────────────────────
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    SEND_FILE_MAX_AGE_DEFAULT: int = 0  # disable static-file caching in dev
