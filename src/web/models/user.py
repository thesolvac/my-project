from flask_login import UserMixin

class UserProxy(UserMixin):

    def __init__(self, doc: dict):
        self._doc = doc

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
