from functools import wraps

from bson import ObjectId
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..database import get_db

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

_ALGO_DISPLAY = {
    "flow_scan":   "FlowScan",
    "skip_stride": "SkipStride",
    "twin_hash":   "TwinHash",
    "bit_anchor":  "BitAnchor",
    "web_scan":    "WebScan",
    "tier_match":  "TierMatch",
}

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Administrator access required.", "danger")
            return redirect(url_for("search.dashboard"))
        return f(*args, **kwargs)
    return decorated

@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    db = get_db()

    total_searches = db.search_history.count_documents({})
    total_users    = db.users.count_documents({})

    algo_stats = list(db.search_history.aggregate([
        {"$group": {"_id": "$algorithm", "count": {"$sum": 1}}},
        {"$sort":  {"count": -1}},
    ]))
    for a in algo_stats:
        a["display"] = _ALGO_DISPLAY.get(a["_id"], a["_id"])

    perf_stats = list(db.performance_log.aggregate([
        {"$group": {
            "_id":       "$algorithm",
            "avg_ms":    {"$avg": "$duration_ms"},
            "avg_mbs":   {"$avg": "$throughput_mbs"},
            "avg_match": {"$avg": "$match_count"},
            "total":     {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]))
    for p in perf_stats:
        p["avg_ms"]    = round(p["avg_ms"]    or 0, 3)
        p["avg_mbs"]   = round(p["avg_mbs"]   or 0, 2)
        p["avg_match"] = round(p["avg_match"] or 0, 1)
        p["display"]   = _ALGO_DISPLAY.get(p["_id"], p["_id"])

    recent = list(db.search_history.find().sort("timestamp", -1).limit(20))
    for s in recent:
        s["_id"]     = str(s["_id"])
        s["user_id"] = str(s.get("user_id", ""))
        s["display"] = s.get("algorithm_display") or _ALGO_DISPLAY.get(s.get("algorithm", ""), s.get("algorithm", "—"))

    top_users = list(
        db.users
        .find({}, {"username": 1, "search_count": 1, "role": 1, "email": 1})
        .sort("search_count", -1)
        .limit(10)
    )
    for u in top_users:
        u["_id"] = str(u["_id"])

    return render_template(
        "admin/dashboard.html",
        total_searches=total_searches,
        total_users=total_users,
        algo_stats=algo_stats,
        perf_stats=perf_stats,
        recent=recent,
        top_users=top_users,
    )

@admin_bp.route("/promote/<user_id>")
@login_required
@admin_required
def promote(user_id: str):
    db = get_db()
    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": "admin"}})
    flash("User promoted to admin.", "success")
    return redirect(url_for("admin.dashboard"))
