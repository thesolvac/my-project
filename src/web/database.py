from flask import current_app, g

_MONGO_AVAILABLE: bool | None = None

def _test_mongo(uri: str) -> bool:
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=1500)
        client.server_info()
        client.close()
        return True
    except Exception:
        return False

def get_db():
    if "db" not in g:
        global _MONGO_AVAILABLE

        if _MONGO_AVAILABLE is None:
            uri = current_app.config["MONGO_URI"]
            _MONGO_AVAILABLE = _test_mongo(uri)
            if not _MONGO_AVAILABLE:
                current_app.logger.warning(
                    "MongoDB not reachable at %s — using in-memory store. "
                    "Data will not persist across restarts.", uri
                )

        if _MONGO_AVAILABLE:
            from pymongo import MongoClient
            client = MongoClient(current_app.config["MONGO_URI"])
            g.db        = client[current_app.config["MONGO_DB_NAME"]]
            g._mongo_cl = client
        else:
            from .memory_store import get_memory_db
            g.db = get_memory_db()

    return g.db

def close_db(exc=None) -> None:
    client = g.pop("_mongo_cl", None)
    if client is not None:
        client.close()

def init_db_indexes(app) -> None:
    global _MONGO_AVAILABLE
    if _MONGO_AVAILABLE is False:
        return
    try:
        with app.app_context():
            db = get_db()
            if hasattr(db, "users"):
                db.users.create_index("username",  unique=True)
                db.users.create_index("email",     unique=True)
                db.search_history.create_index([("user_id", 1), ("timestamp", -1)])
                db.performance_log.create_index([("algorithm", 1), ("timestamp", -1)])
    except Exception:
        pass
