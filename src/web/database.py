"""
Database Layer
==============
Returns either a real PyMongo database or an in-memory fallback,
depending on whether MongoDB is reachable.

The in-memory store mirrors the PyMongo collection API so all route
code works unchanged.  Data resets on server restart; install MongoDB
and set MONGO_URI in .env for persistent storage.
"""

from flask import current_app, g

# ── Attempt to connect to MongoDB; fall back to in-memory store ──────────────
_MONGO_AVAILABLE: bool | None = None   # None = not yet tested


def _test_mongo(uri: str) -> bool:
    """Return True if MongoDB is reachable at *uri*."""
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=1500)
        client.server_info()
        client.close()
        return True
    except Exception:
        return False


def get_db():
    """
    Return the active database handle bound to the current request context.
    Falls back to MemoryDatabase when MongoDB is unreachable.
    """
    if "db" not in g:
        global _MONGO_AVAILABLE

        # First call: probe MongoDB once and cache the result
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
    """Tear-down hook: close the MongoClient (no-op for in-memory store)."""
    client = g.pop("_mongo_cl", None)
    if client is not None:
        client.close()


def init_db_indexes(app) -> None:
    """Create indexes if using real MongoDB (no-op otherwise)."""
    global _MONGO_AVAILABLE
    if _MONGO_AVAILABLE is False:
        return
    try:
        with app.app_context():
            db = get_db()
            if hasattr(db, "users"):   # real pymongo db
                db.users.create_index("username",  unique=True)
                db.users.create_index("email",     unique=True)
                db.search_history.create_index([("user_id", 1), ("timestamp", -1)])
                db.performance_log.create_index([("algorithm", 1), ("timestamp", -1)])
    except Exception:
        pass
