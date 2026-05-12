"""
User Model
==========
A thin proxy object that wraps a raw MongoDB document and satisfies
the Flask-Login UserMixin interface.  No ORM layer is used; we keep
the model intentionally simple to stay close to the MongoDB document.
"""

from flask_login import UserMixin


class UserProxy(UserMixin):
    """
    Wraps a MongoDB user document for Flask-Login compatibility.

    MongoDB document schema (collection: users):
    {
        "_id":          ObjectId,
        "username":     str,
        "email":        str,
        "password":     str,          # werkzeug password hash
        "role":         "user"|"admin",
        "created_at":   datetime,
        "search_count": int
    }
    """

    def __init__(self, doc: dict):
        self._doc = doc

    # Flask-Login requires a string ID
    def get_id(self) -> str:
        return str(self._doc["_id"])

    @property
    def username(self) -> str:
        return self._doc.get("username", "")

    @property
    def email(self) -> str:
        return self._doc.get("email", "")

    @property
    def role(self) -> str:
        return self._doc.get("role", "user")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def search_count(self) -> int:
        return self._doc.get("search_count", 0)
