"""
Flask Application Factory
==========================
Creates and configures the Flask app, registers blueprints,
and sets up Flask-Login.

Usage:
    from src.web.app import create_app
    app = create_app()
    app.run()
"""

from pathlib import Path

from flask import Flask
from flask_login import LoginManager

from .config import Config
from .database import close_db, init_db_indexes
from .models.user import UserProxy

login_manager = LoginManager()


def create_app(config_class=Config) -> Flask:
    """
    Application factory.  Returns a fully configured Flask instance.

    Args:
        config_class: Configuration object (defaults to Config).

    Returns:
        Configured Flask application.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(config_class)

    # Ensure upload directory exists
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    # ── Database teardown ────────────────────────────────────────────────
    app.teardown_appcontext(close_db)

    # ── Flask-Login ──────────────────────────────────────────────────────
    login_manager.init_app(app)
    login_manager.login_view         = "auth.login"          # type: ignore[assignment]
    login_manager.login_message      = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str):
        from .database import get_db
        from bson import ObjectId
        try:
            # Our in-memory IDs are 24-hex strings — valid for bson.ObjectId too
            doc = get_db().users.find_one({"_id": ObjectId(user_id)})
            return UserProxy(doc) if doc else None
        except Exception:
            return None

    # ── Blueprints ───────────────────────────────────────────────────────
    from .routes.auth   import auth_bp
    from .routes.search import search_bp
    from .routes.admin  import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(admin_bp)

    # ── MongoDB indexes (idempotent) ──────────────────────────────────────
    try:
        init_db_indexes(app)
    except Exception:
        pass   # MongoDB may not be running; app still starts

    return app
