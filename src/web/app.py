from pathlib import Path

from flask import Flask
from flask_login import LoginManager

from .config import Config
from .database import close_db, init_db_indexes
from .models.user import UserProxy

login_manager = LoginManager()

def create_app(config_class=Config) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(config_class)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(close_db)

    login_manager.init_app(app)
    login_manager.login_view         = "auth.login"
    login_manager.login_message      = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str):
        from .database import get_db
        from bson import ObjectId
        try:
            doc = get_db().users.find_one({"_id": ObjectId(user_id)})
            return UserProxy(doc) if doc else None
        except Exception:
            return None

    from .routes.auth   import auth_bp
    from .routes.search import search_bp
    from .routes.admin  import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(admin_bp)

    try:
        init_db_indexes(app)
    except Exception:
        pass

    return app
