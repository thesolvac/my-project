"""
Search Blueprint
================
Core search functionality: file upload, text input, algorithm selection,
result display, history, and the comparison benchmark mode.
"""

import uuid
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from flask import (Blueprint, current_app, flash, jsonify,
                   redirect, render_template, request, url_for)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ..database import get_db
from src.engine import APMEEngine

search_bp = Blueprint("search", __name__)
_engine   = APMEEngine()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _allowed(filename: str) -> bool:
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", set())
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def _save_to_history(result, source: str, user_id: str) -> str:
    """Persist search metadata to MongoDB and return the search _id string."""
    db  = get_db()
    doc = {
        "user_id":         ObjectId(user_id),
        "username":        current_user.username,
        "pattern":         result.pattern,
        "algorithm":       result.algorithm,
        "algorithm_display": result.algorithm_display,
        "source":          source,
        "match_count":     result.match_count,
        "duration_ms":     result.duration_ms,
        "text_size_bytes": result.text_size_bytes,
        "throughput_mbs":  result.throughput_mbs,
        "mode":            result.mode,
        "timestamp":       datetime.utcnow(),
        "warnings":        result.warnings,
    }
    inserted = db.search_history.insert_one(doc)

    # Increment per-user counter
    db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$inc": {"search_count": 1}},
    )

    # Detailed performance log (for admin analytics)
    db.performance_log.insert_one({
        "search_id":       str(inserted.inserted_id),
        "algorithm":       result.algorithm,
        "pattern_length":  result.pattern_length,
        "text_size_bytes": result.text_size_bytes,
        "duration_ms":     result.duration_ms,
        "match_count":     result.match_count,
        "throughput_mbs":  result.throughput_mbs,
        "timestamp":       datetime.utcnow(),
    })

    return str(inserted.inserted_id)


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@search_bp.route("/")
@login_required
def index():
    return render_template("index.html")


@search_bp.route("/search", methods=["POST"])
@login_required
def run_search():
    pattern    = request.form.get("pattern", "").strip()
    mode       = request.form.get("mode", "auto")
    algorithm  = request.form.get("algorithm") or None
    text_input = request.form.get("text_input", "").strip()
    try:
        max_errors = max(0, min(5, int(request.form.get("max_errors", 1))))
    except (ValueError, TypeError):
        max_errors = 1

    if not pattern:
        flash("Please enter a search pattern.", "warning")
        return redirect(url_for("search.index"))

    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    file_obj   = request.files.get("file")

    # ── Path A: file upload ───────────────────────────────────────────────
    if file_obj and file_obj.filename:
        if not _allowed(file_obj.filename):
            flash("File type not supported.  Use .txt .log .csv .md .json .xml .py .js", "danger")
            return redirect(url_for("search.index"))

        unique_name = f"{uuid.uuid4().hex}_{secure_filename(file_obj.filename)}"
        save_path   = upload_dir / unique_name
        file_obj.save(save_path)

        try:
            result = _engine.search_file(
                str(save_path), pattern,
                mode=mode,
                algorithm=algorithm if mode == "manual" else None,
                max_errors=max_errors,
            )
        except Exception as exc:
            save_path.unlink(missing_ok=True)
            flash(f"Error processing file: {exc}", "danger")
            return redirect(url_for("search.index"))

        source = file_obj.filename

    # ── Path B: direct text input ─────────────────────────────────────────
    elif text_input:
        try:
            result = _engine.search(
                text_input, pattern,
                mode=mode,
                algorithm=algorithm if mode == "manual" else None,
                max_errors=max_errors,
            )
        except Exception as exc:
            flash(f"Search error: {exc}", "danger")
            return redirect(url_for("search.index"))

        source = "Direct text input"

    else:
        flash("Please provide text input or upload a file.", "warning")
        return redirect(url_for("search.index"))

    search_id = _save_to_history(result, source, current_user.get_id())

    return render_template(
        "results.html",
        result=result,
        search_id=search_id,
        source=source,
    )


@search_bp.route("/compare", methods=["POST"])
@login_required
def compare():
    """
    Run all three algorithms on the submitted text and return JSON metrics.
    Called by the Compare button on the results page via fetch().
    """
    text    = request.json.get("text", "")
    pattern = request.json.get("pattern", "")

    if not text or not pattern:
        return jsonify({"error": "text and pattern are required"}), 400

    comparison = _engine.compare(text, pattern)

    payload = {
        algo: {
            "duration_ms":    r.duration_ms,
            "match_count":    r.match_count,
            "throughput_mbs": r.throughput_mbs,
            "complexity":     r.complexity,
            "display_name":   r.algorithm_display,
        }
        for algo, r in comparison.items()
    }
    return jsonify(payload)


@search_bp.route("/history")
@login_required
def history():
    db = get_db()
    raw = list(
        db.search_history
        .find({"user_id": ObjectId(current_user.get_id())})
        .sort("timestamp", -1)
        .limit(50)
    )
    # Stringify ObjectIds for Jinja2
    for doc in raw:
        doc["_id"]     = str(doc["_id"])
        doc["user_id"] = str(doc["user_id"])

    return render_template("history.html", searches=raw)
