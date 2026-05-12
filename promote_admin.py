"""Promote a user to admin role by email."""

from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME   = "apme_db"
EMAIL     = "admin@apme.com"

client = MongoClient(MONGO_URI)
db     = client[DB_NAME]

result = db.users.update_one(
    {"email": EMAIL},
    {"$set": {"role": "admin"}},
)

if result.matched_count == 0:
    print(f"No user found with email '{EMAIL}'.")
elif result.modified_count == 1:
    doc = db.users.find_one({"email": EMAIL}, {"username": 1, "email": 1, "role": 1})
    print(f"Success: {doc['username']} ({doc['email']}) -> role = {doc['role']}")
else:
    print(f"User '{EMAIL}' was already an admin — no change needed.")

client.close()
