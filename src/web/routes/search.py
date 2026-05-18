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
from src.python_wrapper import APMEEngine

search_bp = Blueprint("search", __name__)
_engine   = APMEEngine()

_MAX_ZIP_SIZE    = 50_000_000
_MAX_ZIP_MEMBERS = 50

_ALGO_DATA = {
    "flow-scan": {
        "name": "FlowScan", "slug": "flow-scan",
        "colour": "#3D5A80", "tag": "Linear · Exact · APME",
        "summary": (
            "FlowScan is APME's linear exact-match algorithm. It selects an adaptive bigram anchor "
            "— the rarest two-byte pair in the pattern — then scans bidirectionally from every "
            "anchor hit. An LPS failure table handles the left half; the right half advances "
            "normally. When no active match thread exists, FlowScan calls memchr on the bigram "
            "to jump directly past dead stretches in a single SIMD-accelerated call."
        ),
        "best_for": "Repetitive text, small alphabets (binary/DNA), and any pattern where a rare bigram anchor can be identified.",
        "steps": [
            "Select the adaptive bigram anchor: the two-byte pair in the pattern with the lowest corpus frequency.",
            "Compute the LPS (longest proper prefix-suffix) table for the pattern in O(m).",
            "Use memchr on the bigram to locate the next anchor hit — skipping past non-starting byte-pairs.",
            "From each anchor, compare bidirectionally (left via LPS, right forward). On mismatch, shift via LPS.",
            "When the full pattern is consumed, record the match and continue searching.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n / σ₀)", "note": "σ₀ = bigram frequency in corpus"},
            {"case": "Average", "time": "O(n + m)",  "note": "Normal text"},
            {"case": "Worst",   "time": "O(n + m)",  "note": "Periodic patterns"},
            {"case": "Space",   "time": "O(m)",      "note": "LPS table only"},
        ],
        "notes": [
            "The adaptive bigram anchor is the APME optimisation — rarer than any single-byte anchor.",
            "Best-case improves when the bigram is rare; never degrades on adversarial inputs.",
            "Fully O(n+m) worst-case guarantee.",
        ],
    },
    "skip-stride": {
        "name": "SkipStride", "slug": "skip-stride",
        "colour": "#EE6C4D", "tag": "Sub-linear · Exact · APME",
        "summary": (
            "SkipStride extends Boyer-Moore with a 2-gram bad-character table of 65,536 byte-pair "
            "entries. Where classic BM consults a single-byte table (256 entries), SkipStride looks "
            "up the last two bytes of the mismatched window, producing larger skip distances on "
            "every mismatch. A Sunday bonus shift further inspects the byte beyond the window, "
            "yielding shift = max(BC2, GS, Sunday) — guaranteed ≥ 1."
        ),
        "best_for": "Natural language and source code with long patterns and a diverse character set.",
        "steps": [
            "Precompute the 2-gram Bad Character table: for each byte-pair (b1,b2), record the rightmost position in the pattern.",
            "Precompute the Good Suffix table: for each mismatch suffix, record the safe shift distance.",
            "Align the pattern and compare right-to-left.",
            "On mismatch, compute BC2 shift and GS shift, then inspect text[s + pat_len] for the Sunday bonus shift.",
            "Advance by max(BC2, GS, Sunday) — guaranteed ≥ 1.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n / (m+1))", "note": "Sunday shift adds 1 extra byte"},
            {"case": "Average", "time": "O(n)",         "note": "Natural language"},
            {"case": "Worst",   "time": "O(n)",         "note": "GS table prevents quadratic"},
            {"case": "Space",   "time": "O(m + σ)",     "note": "65,536-entry 2-gram table"},
        ],
        "notes": [
            "The 2-gram bad-character table is the APME optimisation — larger skips than single-byte BM.",
            "65,536 entries fit in L1 cache on modern CPUs; lookup cost is identical to classic BM.",
            "GS table prevents the quadratic worst case of Bad-Character-only implementations.",
        ],
    },
    "twin-hash": {
        "name": "TwinHash", "slug": "twin-hash",
        "colour": "#98C1D9", "tag": "Dual Hash · Exact · APME",
        "summary": (
            "TwinHash maintains a four-layer hierarchical filter before any character-level "
            "verification. Layer 1 is a byte-sum pre-filter; layers 2–3 are two independent "
            "rolling polynomial hashes; layer 4 is a final SSE2-accelerated byte comparison. "
            "A window must pass all four layers before a match is reported, reducing the "
            "false-positive probability from ≈ 10⁻⁹ (single hash) to ≈ 10⁻²²."
        ),
        "best_for": "Short patterns in very large texts, plagiarism detection, and workloads requiring near-zero verification overhead.",
        "steps": [
            "Compute pattern byte-sum S and initial window byte-sum — O(m) setup.",
            "Choose two independent (base, modulus) pairs and compute pattern hashes h1, h2.",
            "On each window slide: update byte-sum O(1); reject if sum ≠ S (layer 1).",
            "Update both rolling hashes O(1); reject if either hash mismatches (layers 2–3).",
            "Only on all-pass: run SSE2 byte comparison (layer 4) and record match.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n + m)",          "note": "No false positives"},
            {"case": "Average", "time": "O(n + m)",          "note": "Near-zero verifications"},
            {"case": "Worst",   "time": "O(n · m)",          "note": "Deliberate collision only"},
            {"case": "Space",   "time": "O(1)",              "note": "Excluding output"},
        ],
        "notes": [
            "The 4-layer hierarchical filter + SSE2 is the APME optimisation — collision prob ≈ 10⁻²².",
            "Byte-sum pre-filter (layer 1) eliminates most windows with zero hash computation.",
            "NTT-friendly second modulus (998244353) is a standard choice in competitive programming.",
        ],
    },
    "bit-anchor": {
        "name": "BitAnchor", "slug": "bit-anchor",
        "colour": "#293241", "tag": "Bit-Parallel · Exact · APME",
        "summary": (
            "BitAnchor runs two NFA bitvectors simultaneously around an internal anchor — the "
            "rarest byte inside the pattern. The left NFA scans backward from the anchor; the "
            "right NFA scans forward. Both are encoded into 64-bit integers for branch-free "
            "updates. When both NFAs drop to the dead state, memchr jumps to the next anchor "
            "occurrence, exploiting SIMD acceleration to skip large dead stretches."
        ),
        "best_for": "Short ASCII patterns (m ≤ 64) with a rare internal byte; high-throughput log scanning.",
        "steps": [
            "Identify the internal anchor: the rarest byte inside the pattern.",
            "Build D_left[c] and D_right[c] bitmask tables for the left and right NFA halves.",
            "When both NFA states == 0, use memchr to jump to the next anchor occurrence.",
            "Update left NFA (scanning backward) and right NFA (scanning forward) simultaneously.",
            "When the match bits of both NFAs are set at the anchor, record the match position.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n)",       "note": "Dead-state skips dominate"},
            {"case": "Average", "time": "O(n)",       "note": "Single-word NFA per direction"},
            {"case": "Worst",   "time": "O(n·⌈m/64⌉)", "note": "m > 64 bytes"},
            {"case": "Space",   "time": "O(σ)",       "note": "256 × 2 64-bit masks"},
        ],
        "notes": [
            "The bidirectional NFA around an internal anchor is the APME optimisation.",
            "Internal anchor is rarer than pattern[0], producing longer dead-state skips.",
            "Patterns > 64 bytes fall back to FlowScan automatically.",
        ],
    },
    "web-scan": {
        "name": "WebScan", "slug": "web-scan",
        "colour": "#5b7fa3", "tag": "Multi-Pattern · Automaton · APME",
        "summary": (
            "WebScan builds a true Aho-Corasick DFA and applies three structural optimisations: "
            "(1) densification — hot states are expanded into full 256-entry arrays for O(1) "
            "lookup; (2) a 256-bit presence bitmap that bypasses the DFA entirely for bytes "
            "absent from all patterns; (3) output propagation — failure links carry match sets "
            "so every match at any failure ancestor is reported without extra traversal."
        ),
        "best_for": "Multi-pattern keyword spotting in IDS/IPS, log analysis, and mixed natural-language and code text.",
        "steps": [
            "Insert all patterns into a trie and compute BFS failure links to build a complete DFA.",
            "Densify hot states: expand states with high hit-count into full 256-entry arrays.",
            "Build a 256-bit presence bitmap: bit c is set iff byte c appears in any pattern.",
            "For each text byte, test the presence bitmap first; reset to root if absent.",
            "Follow the DFA transition and emit all matches via propagated output sets.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n + m·σ)", "note": "Presence check dominant"},
            {"case": "Average", "time": "O(n)",       "note": "Most bytes bypass the DFA"},
            {"case": "Worst",   "time": "O(n)",       "note": "Always linear"},
            {"case": "Space",   "time": "O((m+1)·σ) + 32 bytes", "note": "DFA + bitmap"},
        ],
        "notes": [
            "Densification + presence bitmap + output propagation are the three APME optimisations.",
            "Presence bitmap saves a DFA lookup for every byte absent from all patterns — typically the majority.",
            "Used in IDS/IPS keyword spotting and network packet inspection pipelines.",
        ],
    },
    "tier-match": {
        "name": "TierMatch", "slug": "tier-match",
        "colour": "#f0956a", "tag": "Approximate · Myers · APME",
        "summary": (
            "TierMatch implements Myers bit-parallel approximate matching (JACM 1999) with "
            "best-tier deduplication. It maintains k+1 NFA bitvectors simultaneously — one per "
            "error level. After each NFA step, TierMatch scans d=0 upward: the first tier that "
            "fires is recorded and the accept bit in all higher tiers is cleared, ensuring at most "
            "one result per text position at the lowest edit distance. For m > 64, it falls back "
            "to the multi-word Myers variant rather than naive DP."
        ),
        "best_for": "Typo-tolerant search, OCR post-processing, and ranked fuzzy pipelines that expect one result per position.",
        "steps": [
            "Build the D[c] bitmask table and k+1 NFA state bitvectors R[0]…R[k] (Myers encoding).",
            "For each text byte, update all k+1 layers using the Myers recurrence (substitution, insert, delete).",
            "Scan d = 0, 1, …, k: find the first tier d where R[d] has the accept bit set.",
            "Record one match at the best tier; clear the accept bit in R[d+1]…R[k] to suppress duplicates.",
            "For m > 64, use the multi-word Myers variant (64-bit words chained) instead of DP.",
        ],
        "complexity": [
            {"case": "Best",    "time": "O(n · k)",    "note": "k = max errors"},
            {"case": "Average", "time": "O(n · k)",    "note": "Linear per error level"},
            {"case": "Worst",   "time": "O(n · ⌈m/64⌉ · k)", "note": "Multi-word Myers for m > 64"},
            {"case": "Space",   "time": "O(k + σ)  /  O(⌈m/64⌉)", "note": "Bitap / multi-word path"},
        ],
        "notes": [
            "Myers bit-parallel + best-tier dedup is the APME optimisation — one result per position.",
            "k=0 reduces exactly to BitAnchor exact mode.",
            "Setting k too high produces overwhelming false positives; k ≤ 3 is practical.",
        ],
    },
}

def _allowed(filename: str) -> bool:
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", set())
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed

def _save_to_history(result, source: str, user_id: str) -> str:
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

    db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$inc": {"search_count": 1}},
    )

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
    for doc in raw:
        doc["_id"]     = str(doc["_id"])
        doc["user_id"] = str(doc["user_id"])

    return render_template("history.html", searches=raw)

def _calc_streak(date_strings):
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
    "flow_scan":   "FlowScan",
    "skip_stride": "SkipStride",
    "twin_hash":   "TwinHash",
    "bit_anchor":  "BitAnchor",
    "web_scan":    "WebScan",
    "tier_match":  "TierMatch",
    "kmp":                       "FlowScan",
    "kmp (knuth-morris-pratt)":  "FlowScan",
    "knuth-morris-pratt":        "FlowScan",
    "flowscan":                  "FlowScan",
    "dnascan":                   "FlowScan",
    "boyer-moore":               "SkipStride",
    "boyer moore":               "SkipStride",
    "skipstride":                "SkipStride",
    "gapjump":                   "SkipStride",
    "rabin-karp":                "TwinHash",
    "rabin karp":                "TwinHash",
    "twinhash":                  "TwinHash",
    "dualrabin":                 "TwinHash",
    "shift-or":                  "BitAnchor",
    "shift or":                  "BitAnchor",
    "bitap":                     "BitAnchor",
    "bitanchor":                 "BitAnchor",
    "bitmatch":                  "BitAnchor",
    "aho-corasick":              "WebScan",
    "aho corasick":              "WebScan",
    "webscan":                   "WebScan",
    "sweeprun":                  "WebScan",
    "fuzzy":                     "TierMatch",
    "wu-manber":                 "TierMatch",
    "tiermatch":                 "TierMatch",
    "fuzzysearch":               "TierMatch",
}

def _normalize_algo(name: str | None) -> str:
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

    alg_dist = list(db.search_history.aggregate([
        {"$match": {"user_id": uid}},
        {"$addFields": {
            "algo_name": {"$ifNull": ["$algorithm_display", "$algorithm"]}
        }},
        {"$group": {"_id": "$algo_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    most_used_alg = _normalize_algo(alg_dist[0]["_id"]) if alg_dist else "—"

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
