import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_BASE = Path(__file__).resolve().parent

class Config:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-insecure-key-change-in-prod")

    MONGO_URI:     str = os.getenv("MONGO_URI",     "mongodb://localhost:27017/")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "apme_db")

    UPLOAD_FOLDER:      Path = _BASE / "uploads"
    MAX_CONTENT_LENGTH: int  = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
    ALLOWED_EXTENSIONS: set  = {"txt", "log", "csv", "md", "json", "xml", "py", "js", "html"}

    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    SEND_FILE_MAX_AGE_DEFAULT: int = 0
