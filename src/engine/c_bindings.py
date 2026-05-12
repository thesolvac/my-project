"""
C Backend Bindings
==================
Loads the compiled shared library (algorithms.dll / .so / .dylib) and
exposes typed Python wrappers for each search function via ctypes.

The library is expected at:
    <project_root>/src/c_backend/algorithms.<ext>

If the library cannot be found, C_BACKEND_AVAILABLE is set to False and
the engine falls back to its pure-Python FlowScan implementation.

Public API
----------
    from src.engine.c_bindings import (
        flowscan_search, skipstride_search, twinhash_search,
        bitanchor_search, webscan_search, tiermatch_search,
    )
    positions = flowscan_search("hello world", "world")           # → [6]
    positions = tiermatch_search("hello world", "wrold", k=1)    # → [6]
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Library discovery & loading
# ─────────────────────────────────────────────────────────────────────────────

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "c_backend"
_MAX_RESULTS = 1_000_000   # must match MAX_RESULTS in algorithms.h


def _find_library() -> Path:
    """Return the path to the compiled shared library, or raise FileNotFoundError."""
    if sys.platform.startswith("win"):
        candidates = [_BACKEND_DIR / "algorithms.dll"]
    elif sys.platform.startswith("darwin"):
        candidates = [
            _BACKEND_DIR / "algorithms.dylib",
            _BACKEND_DIR / "algorithms.so",
        ]
    else:
        candidates = [_BACKEND_DIR / "algorithms.so"]

    for p in candidates:
        if p.exists():
            return p

    searched = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(
        f"C shared library not found.  Run 'make' in {_BACKEND_DIR}.\n"
        f"Searched: {searched}"
    )


def _configure(lib: ctypes.CDLL) -> ctypes.CDLL:
    """Attach argument and return types to all six search functions."""
    # Common signature: (char*, int, char*, int, int*, int) → int
    _argtypes = [
        ctypes.c_char_p,               # text
        ctypes.c_int,                  # text_len
        ctypes.c_char_p,               # pattern
        ctypes.c_int,                  # pat_len
        ctypes.POINTER(ctypes.c_int),  # positions[]
        ctypes.c_int,                  # max_res
    ]
    for name in ("flowscan_search", "skipstride_search", "twinhash_search",
                 "bitanchor_search", "webscan_search"):
        fn = getattr(lib, name)
        fn.restype  = ctypes.c_int
        fn.argtypes = _argtypes

    # tiermatch_search has an extra max_errors parameter
    lib.tiermatch_search.restype  = ctypes.c_int
    lib.tiermatch_search.argtypes = [
        ctypes.c_char_p,               # text
        ctypes.c_int,                  # text_len
        ctypes.c_char_p,               # pattern
        ctypes.c_int,                  # pat_len
        ctypes.c_int,                  # max_errors
        ctypes.POINTER(ctypes.c_int),  # positions[]
        ctypes.c_int,                  # max_res
    ]
    return lib


# Attempt to load once at import time; set flags accordingly.
_lib: ctypes.CDLL | None = None
_load_error: str = ""

try:
    _lib = _configure(ctypes.CDLL(str(_find_library())))
    C_BACKEND_AVAILABLE = True
except FileNotFoundError as _exc:
    C_BACKEND_AVAILABLE = False
    _load_error = str(_exc)
except OSError as _exc:
    C_BACKEND_AVAILABLE = False
    _load_error = f"OS error loading library: {_exc}"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helper
# ─────────────────────────────────────────────────────────────────────────────

def _call(fn: ctypes.CFUNCTYPE, text: str, pattern: str) -> list[int]:
    """
    Invoke a C search function and return a list of match positions.

    Args:
        fn:      ctypes function reference (standard 6-arg signature)
        text:    Text to search within
        pattern: Pattern to locate

    Returns:
        Sorted list of integer start indices.

    Raises:
        RuntimeError: C library not loaded
        ValueError:   C function returned error code (e.g. malloc failure)
    """
    if not C_BACKEND_AVAILABLE:
        raise RuntimeError(
            f"C backend unavailable – using Python fallback.\nDetails: {_load_error}"
        )
    if not text or not pattern:
        return []

    b_text    = text.encode("utf-8")
    b_pattern = pattern.encode("utf-8")
    buf       = (ctypes.c_int * _MAX_RESULTS)()

    count = fn(b_text, len(b_text), b_pattern, len(b_pattern), buf, _MAX_RESULTS)

    if count < 0:
        raise ValueError(
            "C search function returned a negative code – likely a malloc failure."
        )
    return list(buf[:count])


def _call_tiermatch(text: str, pattern: str, max_errors: int) -> list[int]:
    """Invoke tiermatch_search (7-arg signature with max_errors)."""
    if not C_BACKEND_AVAILABLE:
        raise RuntimeError(
            f"C backend unavailable – using Python fallback.\nDetails: {_load_error}"
        )
    if not text or not pattern:
        return []

    b_text    = text.encode("utf-8")
    b_pattern = pattern.encode("utf-8")
    buf       = (ctypes.c_int * _MAX_RESULTS)()
    max_errors = max(0, min(5, max_errors))

    count = _lib.tiermatch_search(
        b_text, len(b_text), b_pattern, len(b_pattern),
        max_errors, buf, _MAX_RESULTS,
    )
    if count < 0:
        raise ValueError(
            "tiermatch_search returned a negative code – likely a malloc failure."
        )
    return list(buf[:count])


# ─────────────────────────────────────────────────────────────────────────────
# Public wrappers
# ─────────────────────────────────────────────────────────────────────────────

def flowscan_search(text: str, pattern: str) -> list[int]:
    """FlowScan via C backend. O(n/σ₀) best case, O(n+m) worst case."""
    return _call(_lib.flowscan_search, text, pattern)


def skipstride_search(text: str, pattern: str) -> list[int]:
    """SkipStride via C backend. O(n/(m+1)) best case."""
    return _call(_lib.skipstride_search, text, pattern)


def twinhash_search(text: str, pattern: str) -> list[int]:
    """TwinHash (dual rolling hash) via C backend. O(n+m) average. Collision prob ≈ 10⁻¹⁸."""
    return _call(_lib.twinhash_search, text, pattern)


def bitanchor_search(text: str, pattern: str) -> list[int]:
    """BitAnchor via C backend. O(n) for m ≤ 64."""
    return _call(_lib.bitanchor_search, text, pattern)


def webscan_search(text: str, pattern: str) -> list[int]:
    """WebScan via C backend. O(n) search."""
    return _call(_lib.webscan_search, text, pattern)


def tiermatch_search(text: str, pattern: str, max_errors: int = 1) -> list[int]:
    """
    TierMatch (Wu-Manber + best-tier deduplication) via C backend.
    O(n·k) for m ≤ 64; O(n·m) Levenshtein DP fallback for m > 64.

    Args:
        max_errors: Maximum allowed edit distance (0–5).
    """
    return _call_tiermatch(text, pattern, max_errors)
