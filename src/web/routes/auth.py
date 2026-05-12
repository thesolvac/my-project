"""
Authentication Blueprint
=========================
Handles user registration, login, and logout.
Passwords are hashed with Werkzeug's PBKDF2-SHA256 implementation.
"""

from datetime import datetime

from bson import ObjectId
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import get_db
from ..models.user import UserProxy

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ─────────────────────────────────────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("search.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # ── Validation ────────────────────────────────────────────────────
        if not all([username, email, password]):
            flash("All fields are required.", "danger")
            return render_template("register.html")

        if len(username) < 3 or len(username) > 30:
            flash("Username must be 3–30 characters.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("register.html")

        db = get_db()
        if db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
            flash("Username or email is already taken.", "danger")
            return render_template("register.html")

        # ── Create user ───────────────────────────────────────────────────
        doc = {
            "username":     username,
            "email":        email,
            "password":     generate_password_hash(password),
            "role":         "user",
            "created_at":   datetime.utcnow(),
            "search_count": 0,
        }
        result    = db.users.insert_one(doc)
        doc["_id"] = result.inserted_id

        login_user(UserProxy(doc))
        flash(f"Welcome, {username}! Your account has been created.", "success")
        return redirect(url_for("search.dashboard"))

    return render_template("register.html")


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("search.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")
        remember   = bool(request.form.get("remember"))

        db       = get_db()
        user_doc = db.users.find_one({
            "$or": [{"username": identifier}, {"email": identifier.lower()}]
        })

        if user_doc and check_password_hash(user_doc["password"], password):
            user = UserProxy(user_doc)
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(next_page or url_for("search.dashboard"))

        flash("Invalid username/email or password.", "danger")

    return render_template("login.html")


# ─────────────────────────────────────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("search.index"))
