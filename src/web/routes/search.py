"""
Search Blueprint
================
Core search functionality: file upload, text input, algorithm selection,
result display, history, and the comparison benchmark mode.
"""

import os
import shutil
import uuid
import zipfile as _zipfile
from datetime import datetime, timedelta
from pathlib import Path

from bson import ObjectId
from flask import (Blueprint, abort, current_app, flash, jsonify,
                   redirect, render_template, request, url_for, Response)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ..database import get_db
from src.engine import APMEEngine

search_bp = Blueprint("search", __name__)
_engine   = APMEEngine()

_MAX_ZIP_SIZE    = 50_000_000  # 50 MB per member
_MAX_ZIP_MEMBERS = 50

_ALGO_DATA = {
    "flow-scan": {
        "name": "FlowScan", "slug": "flow-scan",
        "colour": "#3D5A80", "tag": "Linear · Exact · APME",
        "summary": (
            "FlowScan is APME's linear exact-match algorithm. It scans left-to-right and never "
            "backtracks in the text. An LPS failure table is built at preprocessing time, but when "
            "no active match thread exists, FlowScan calls memchr to jump directly to the next "
            "occurrence of pattern[0] — skipping dead stretches in a single SIMD-accelerated call."
        ),
        "best_for": "Repetitive text, small alphabets (binary/DNA), and any pattern where the first character is rare in the corpus.",
        "steps": [
            "Compute the LPS (longest proper prefix-suffix) table for the pattern in O(m).",
            "Use memchr to locate the first occurrence of pattern[0] in the text — skipping directly past non-starting bytes.",
            "Compare left-to-right from that anchor. On match, advance both pointers.",
            "On mismatch at pattern position j > 0, use LPS[j-1] to shift — the text pointer never retreats.",
            "When the full pattern is consumed, record the match and continue via the LPS table.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n / σ₀)", "note": "σ₀ = frequency of pattern[0]"},
            {"case": "Average", "time": "O(n + m)",  "note": "Normal text"},
            {"case": "Worst",   "time": "O(n + m)",  "note": "Periodic patterns"},
            {"case": "Space",   "time": "O(m)",      "note": "LPS table only"},
        ],
        "notes": [
            "The memchr anchor is the APME optimisation — it exploits SIMD inside libc.",
            "Best-case improves from O(n) to O(n/σ₀) via the memchr anchor optimisation.",
            "Fully O(n+m) worst-case; never degrades on adversarial inputs.",
        ],
    },
    "skip-stride": {
        "name": "SkipStride", "slug": "skip-stride",
        "colour": "#EE6C4D", "tag": "Sub-linear · Exact · APME",
        "summary": (
            "SkipStride applies three complementary mismatch skip heuristics — Bad Character, "
            "Good Suffix, and a Sunday bonus — to skip large portions of the text on every mismatch. "
            "After a mismatch, SkipStride inspects the byte immediately beyond the current window "
            "— text[s + pat_len]. If that byte is absent from the pattern, the entire window plus "
            "one extra position is skipped in a single stride: shift = max(BC, GS, Sunday)."
        ),
        "best_for": "Natural language and source code with long patterns and a diverse character set.",
        "steps": [
            "Precompute the Bad Character table: for each byte c, record its rightmost position in the pattern.",
            "Precompute the Good Suffix table: for each mismatch suffix, record the safe shift distance.",
            "Align the pattern and compare right-to-left.",
            "On mismatch, compute BC shift and GS shift, then inspect text[s + pat_len] for the Sunday bonus shift.",
            "Advance by max(BC, GS, Sunday) — guaranteed ≥ 1.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n / (m+1))", "note": "Sunday shift adds 1 extra byte"},
            {"case": "Average", "time": "O(n)",         "note": "Natural language"},
            {"case": "Worst",   "time": "O(n)",         "note": "GS table prevents quadratic"},
            {"case": "Space",   "time": "O(m + σ)",     "note": "σ = alphabet size"},
        ],
        "notes": [
            "The Sunday bonus shift is the APME optimisation — one extra byte skipped per window on average.",
            "Best case improves from O(n/m) to O(n/(m+1)) with the Sunday bonus shift.",
            "GS table prevents the quadratic worst case of Bad-Character-only implementations.",
        ],
    },
    "twin-hash": {
        "name": "TwinHash", "slug": "twin-hash",
        "colour": "#98C1D9", "tag": "Dual Hash · Exact · APME",
        "summary": (
            "TwinHash maintains TWO independent rolling polynomial hashes in parallel. "
            "Single-hash rolling search requires O(m) character verification on every collision. "
            "TwinHash only triggers verification when BOTH hashes agree simultaneously, "
            "reducing the false-positive rate from ≈ 10⁻⁹ to ≈ 10⁻¹⁸ — making spurious "
            "verifications practically impossible for any realistic workload."
        ),
        "best_for": "Multi-pattern search, plagiarism detection, and short patterns in very large texts.",
        "steps": [
            "Choose two independent (base, modulus) pairs: (256, 10⁹+7) and (31, 998244353).",
            "Compute initial pattern hashes pat_h1, pat_h2 and window hashes win_h1, win_h2.",
            "On each window slide, update both hashes in O(1) using the rolling formula.",
            "Only verify character-by-character when BOTH win_h1 == pat_h1 AND win_h2 == pat_h2.",
            "Record the match and continue sliding.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n + m)",          "note": "No false positives"},
            {"case": "Average", "time": "O(n + m)",          "note": "Near-zero verifications"},
            {"case": "Worst",   "time": "O(n · m)",          "note": "Deliberate collision only"},
            {"case": "Space",   "time": "O(1)",              "note": "Excluding output"},
        ],
        "notes": [
            "The dual hash is the APME optimisation — collision prob drops to ≈ 10⁻¹⁸.",
            "Verification cost doubles hash computation per slide but eliminates O(m) checks.",
            "NTT-friendly second modulus (998244353) is a standard choice in competitive programming.",
        ],
    },
    "bit-anchor": {
        "name": "BitAnchor", "slug": "bit-anchor",
        "colour": "#293241", "tag": "Bit-Parallel · Exact · APME",
        "summary": (
            "BitAnchor uses NFA bit-parallelism to encode pattern positions into 64-bit integers. "
            "When the NFA state drops to zero (no active match threads), the standard approach "
            "still advances one byte at a time. BitAnchor detects this dead state and immediately "
            "calls memchr to jump to the next occurrence of pattern[0], exploiting SIMD acceleration "
            "to skip large stretches with no active match threads."
        ),
        "best_for": "Short ASCII patterns (m ≤ 64) with a rare leading byte; high-throughput log scanning.",
        "steps": [
            "Build the D[c] bitmask table: bit j is set iff pattern[j] == c.",
            "Initialise NFA state vector to 0 (no active threads).",
            "When state == 0, use memchr to jump to the next occurrence of pattern[0] in the remaining text.",
            "Update state = ((state << 1) | 1) & D[text[i]] for each byte at the anchor and beyond.",
            "When the match bit (bit m-1) is set, record the match position.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n)",       "note": "Dead-state skips dominate"},
            {"case": "Average", "time": "O(n)",       "note": "Single-word NFA"},
            {"case": "Worst",   "time": "O(n·⌈m/64⌉)", "note": "m > 64 bytes"},
            {"case": "Space",   "time": "O(σ)",       "note": "256 64-bit masks"},
        ],
        "notes": [
            "The dead-state memchr skip is the APME optimisation.",
            "Patterns > 64 bytes fall back to FlowScan automatically.",
            "UTF-8 safe: multi-byte sequences are treated as independent byte runs.",
        ],
    },
    "web-scan": {
        "name": "WebScan", "slug": "web-scan",
        "colour": "#5b7fa3", "tag": "Multi-Pattern · Automaton · APME",
        "summary": (
            "WebScan adds a 256-bit character presence bitmap to its DFA automaton. "
            "Before each state transition, a single bitwise AND tests whether the current "
            "byte can appear in any pattern. If not, the automaton resets to the root state "
            "with no table access — saving the memory load and potential cache miss for every "
            "byte that is absent from the pattern character set."
        ),
        "best_for": "Multi-pattern keyword spotting in mixed natural-language and code text.",
        "steps": [
            "Insert all patterns into a trie and compute BFS failure links to build a complete DFA.",
            "Build a 256-bit presence bitmap: bit c is set iff byte c appears in any pattern.",
            "For each text byte, test the presence bitmap first with a single AND operation.",
            "If the byte is absent, reset to the root state immediately — no DFA table access.",
            "If present, follow the DFA transition and emit any matches at the new state.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n + m·σ)", "note": "Presence check dominant"},
            {"case": "Average", "time": "O(n)",       "note": "Most bytes bypass the DFA"},
            {"case": "Worst",   "time": "O(n)",       "note": "Always linear"},
            {"case": "Space",   "time": "O((m+1)·σ) + 32 bytes", "note": "DFA + bitmap"},
        ],
        "notes": [
            "The 256-bit presence bitmap (4 × uint64) is the APME optimisation.",
            "Saves a DFA table access for every byte absent from all patterns — typically the majority.",
            "Used in keyword spotting and network packet inspection pipelines.",
        ],
    },
    "tier-match": {
        "name": "TierMatch", "slug": "tier-match",
        "colour": "#f0956a", "tag": "Approximate · Best-Tier · APME",
        "summary": (
            "TierMatch is APME's approximate matching algorithm. It maintains k+1 NFA bitvectors "
            "simultaneously — one per error level — and adds best-tier deduplication: the standard "
            "approach emits a match for every error level d=0..k that fires at the same position, "
            "cluttering results with redundant near-duplicate entries. TierMatch scans d=0 upward "
            "after each NFA step: the first tier that fires is recorded, then the accept bit in all "
            "higher tiers is cleared — at most one result per text position at the lowest error count."
        ),
        "best_for": "Typo-tolerant search, OCR post-processing, and ranked fuzzy pipelines that expect one result per position.",
        "steps": [
            "Build the D[c] bitmask table and k+1 NFA state bitvectors R[0]…R[k].",
            "For each text byte, save old state vectors and update all k+1 layers (exact match, substitution, insert, delete).",
            "Scan d = 0, 1, …, k: find the first tier d where R[d] has the accept bit set.",
            "Record one match at the best tier; clear the accept bit in R[d+1]…R[k] to suppress duplicates.",
            "Patterns > 64 bytes fall back to the Levenshtein DP path, which is naturally position-unique.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n · k)",    "note": "k = max errors"},
            {"case": "Average", "time": "O(n · k)",    "note": "Linear per error level"},
            {"case": "Worst",   "time": "O(n · m)",    "note": "DP fallback for m > 64"},
            {"case": "Space",   "time": "O(k + σ) / O(m)", "note": "Bitap / DP path"},
        ],
        "notes": [
            "Best-tier deduplication is the APME optimisation — one result per position.",
            "k=0 reduces exactly to BitAnchor exact mode.",
            "Setting k too high produces overwhelming false positives; k ≤ 3 is practical.",
        ],
    },
}


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
def index():
    if current_user.is_authenticated:
        return redirect(url_for("search.dashboard"))
    return render_template("landing.html")


@search_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@search_bp.route("/tool")
@login_required
def search_tool():
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
        return redirect(url_for("search.search_tool"))

    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    file_obj   = request.files.get("file")

    # ── Path A: file upload ───────────────────────────────────────────────
    if file_obj and file_obj.filename:
        if not _allowed(file_obj.filename):
            flash("File type not supported.  Use .txt .log .csv .md .json .xml .py .js", "danger")
            return redirect(url_for("search.search_tool"))

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
            return redirect(url_for("search.search_tool"))

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
            return redirect(url_for("search.search_tool"))

        source = "Direct text input"

    else:
        flash("Please provide text input or upload a file.", "warning")
        return redirect(url_for("search.search_tool"))

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


@search_bp.route("/batch", methods=["POST"])
@login_required
def run_batch_search():
    pattern = request.form.get("pattern", "").strip()
    mode    = request.form.get("mode", "auto")
    algorithm = request.form.get("algorithm") or None
    try:
        max_errors = max(0, min(5, int(request.form.get("max_errors", 1))))
    except (ValueError, TypeError):
        max_errors = 1

    if not pattern:
        flash("Please enter a search pattern.", "warning")
        return redirect(url_for("search.search_tool"))

    files = request.files.getlist("batch_files")
    if not any(f.filename for f in files):
        flash("Please select at least one file for batch search.", "warning")
        return redirect(url_for("search.search_tool"))

    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    work_items: list[tuple[str, Path]] = []
    temp_files: list[Path] = []
    temp_dirs:  list[Path] = []

    for f in files:
        if not f.filename:
            continue
        safe = secure_filename(f.filename)
        save_path = upload_dir / f"{uuid.uuid4().hex}_{safe}"
        f.save(save_path)

        if Path(f.filename).suffix.lower() == ".zip":
            td = upload_dir / f"{uuid.uuid4().hex}_batch"
            td.mkdir(parents=True, exist_ok=True)
            temp_dirs.append(td)
            try:
                with _zipfile.ZipFile(save_path) as zf:
                    work_items.extend(_safe_extract_zip(zf, td))
            except _zipfile.BadZipFile:
                flash(f"Could not open ZIP: {f.filename}", "warning")
            finally:
                save_path.unlink(missing_ok=True)
        elif _allowed(f.filename):
            work_items.append((f.filename, save_path))
            temp_files.append(save_path)
        else:
            save_path.unlink(missing_ok=True)

    if not work_items:
        flash("No supported files found to search.", "warning")
        return redirect(url_for("search.search_tool"))

    file_results: list[dict] = []
    total_matches = 0
    try:
        for orig_name, path in work_items:
            entry: dict = {
                "file_name":       orig_name,
                "file_size_bytes": path.stat().st_size,
            }
            try:
                r = _engine.search_file(
                    str(path), pattern,
                    mode=mode,
                    algorithm=algorithm if mode == "manual" else None,
                    max_errors=max_errors,
                )
                entry.update({
                    "match_count": r.match_count,
                    "algorithm":   r.algorithm_display,
                    "duration_ms": round(r.duration_ms, 3),
                })
                total_matches += r.match_count
            except Exception as exc:
                entry["error"] = str(exc)
            file_results.append(entry)
    finally:
        for p in temp_files:
            p.unlink(missing_ok=True)
        for d in temp_dirs:
            shutil.rmtree(d, ignore_errors=True)

    files_with_matches = sum(1 for f in file_results if f.get("match_count", 0) > 0)
    return render_template(
        "batch_results.html",
        file_results=file_results,
        total_matches=total_matches,
        total_files=len(file_results),
        files_with_matches=files_with_matches,
        pattern=pattern,
    )


def _safe_extract_zip(zf: _zipfile.ZipFile, extract_dir: Path) -> list[tuple[str, Path]]:
    """Extract text files from a ZIP, guarding against zip-slip and size bombs."""
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", set())
    items: list[tuple[str, Path]] = []
    count = 0
    for member in zf.infolist():
        if count >= _MAX_ZIP_MEMBERS:
            break
        if member.is_dir() or member.file_size > _MAX_ZIP_SIZE:
            continue
        name = Path(member.filename).name
        ext  = Path(name).suffix.lower().lstrip(".")
        if not ext or ext not in allowed:
            continue
        safe_name = f"{uuid.uuid4().hex}_{secure_filename(name)}"
        target = extract_dir / safe_name
        with zf.open(member) as src, open(target, "wb") as dst:
            dst.write(src.read())
        items.append((name, target))
        count += 1
    return items


@search_bp.route("/algorithm/<slug>")
@login_required
def algorithm_detail(slug: str):
    algo = _ALGO_DATA.get(slug)
    if not algo:
        abort(404)
    return render_template(
        "algorithm_detail.html",
        algo=algo,
        all_algos=list(_ALGO_DATA.values()),
    )


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


def _calc_streak(date_strings):
    """Return the current consecutive-day streak from a desc-sorted list of YYYY-MM-DD strings."""
    if not date_strings:
        return 0
    from datetime import date
    today = date.today()
    unique = sorted({d for d in date_strings}, reverse=True)
    streak = 0
    expected = today
    for ds in unique:
        d = date.fromisoformat(ds)
        if d == expected:
            streak += 1
            expected = expected - timedelta(days=1)
        elif d < expected:
            break
    return streak


@search_bp.route("/statistics")
@login_required
def statistics():
    return render_template("statistics.html")


_ALGO_DISPLAY_MAP = {
    # Internal enum values
    "flow_scan":   "FlowScan",
    "skip_stride": "SkipStride",
    "twin_hash":   "TwinHash",
    "bit_anchor":  "BitAnchor",
    "web_scan":    "WebScan",
    "tier_match":  "TierMatch",
    # Old classic display names (stored before APME renaming)
    "kmp":                       "FlowScan",
    "kmp (knuth-morris-pratt)":  "FlowScan",
    "knuth-morris-pratt":        "FlowScan",
    "flowscan":                  "FlowScan",
    "boyer-moore":               "SkipStride",
    "boyer moore":               "SkipStride",
    "skipstride":                "SkipStride",
    "rabin-karp":                "TwinHash",
    "rabin karp":                "TwinHash",
    "twinhash":                  "TwinHash",
    "shift-or":                  "BitAnchor",
    "shift or":                  "BitAnchor",
    "bitap":                     "BitAnchor",
    "bitanchor":                 "BitAnchor",
    "aho-corasick":              "WebScan",
    "aho corasick":              "WebScan",
    "webscan":                   "WebScan",
    "fuzzy":                     "TierMatch",
    "wu-manber":                 "TierMatch",
    "tiermatch":                 "TierMatch",
}


def _normalize_algo(name: str | None) -> str:
    """Return the canonical APME display name for any stored algorithm value."""
    if not name:
        return "Unknown"
    return _ALGO_DISPLAY_MAP.get(name.lower(), name)


@search_bp.route("/api/statistics")
@login_required
def api_statistics():
    db = get_db()
    uid = ObjectId(current_user.get_id())
    now = datetime.utcnow()
    seven_ago = now - timedelta(days=7)

    # Total searches + avg pattern length
    totals_raw = list(db.search_history.aggregate([
        {"$match": {"user_id": uid}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "avg_pattern_len": {"$avg": {"$strLenCP": "$pattern"}},
        }},
    ]))
    total_searches = totals_raw[0]["total"] if totals_raw else 0
    avg_pattern_len = round(totals_raw[0]["avg_pattern_len"] or 0, 1) if totals_raw else 0

    # Algorithm distribution — prefer algorithm_display, fall back to algorithm
    # for any records that pre-date the algorithm_display field.
    alg_dist = list(db.search_history.aggregate([
        {"$match": {"user_id": uid}},
        {"$addFields": {
            "algo_name": {"$ifNull": ["$algorithm_display", "$algorithm"]}
        }},
        {"$group": {"_id": "$algo_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    most_used_alg = _normalize_algo(alg_dist[0]["_id"]) if alg_dist else "—"

    # 7-day activity (fill missing days with 0)
    activity_raw = list(db.search_history.aggregate([
        {"$match": {"user_id": uid, "timestamp": {"$gte": seven_ago}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "count": {"$sum": 1},
        }},
    ]))
    activity_map = {doc["_id"]: doc["count"] for doc in activity_raw}
    activity_labels = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    activity_counts = [activity_map.get(d, 0) for d in activity_labels]

    # Input method split
    input_split_raw = list(db.search_history.aggregate([
        {"$match": {"user_id": uid}},
        {"$project": {
            "input_type": {
                "$cond": [{"$eq": ["$source", "Direct text input"]}, "Text", "File"]
            }
        }},
        {"$group": {"_id": "$input_type", "count": {"$sum": 1}}},
    ]))
    input_map = {doc["_id"]: doc["count"] for doc in input_split_raw}
    preferred_input = max(input_map, key=input_map.get) if input_map else "—"

    # Activity streak
    all_dates_raw = list(db.search_history.aggregate([
        {"$match": {"user_id": uid}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}}}},
        {"$sort": {"_id": -1}},
    ]))
    all_dates = [d["_id"] for d in all_dates_raw]
    streak = _calc_streak(all_dates)

    return jsonify({
        "total_searches": total_searches,
        "most_used_algorithm": most_used_alg,
        "avg_pattern_length": avg_pattern_len,
        "activity_streak": streak,
        "preferred_input": preferred_input,
        "algorithm_distribution": [
            {"algorithm": _normalize_algo(d["_id"]), "count": d["count"]}
            for d in alg_dist
        ],
        "activity_labels": activity_labels,
        "activity_counts": activity_counts,
        "input_text_count": input_map.get("Text", 0),
        "input_file_count": input_map.get("File", 0),
    })
