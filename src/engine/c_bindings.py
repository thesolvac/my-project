"""
C Backend Bindings
==================
Loads the compiled shared library (algorithms.dll / .so / .dylib) and
exposes typed Python wrappers for each search function via ctypes.

The library is expected at:
    <project_root>/src/c_backend/algorithms.<ext>

If the library cannot be found, C_BACKEND_AVAILABLE is set to False and
the engine falls back to its pure-Python KMP implementation.

Public API
----------
    from src.engine.c_bindings import (
        kmp_search, bm_search, rk_search,
        so_search, ac_search, fuzzy_search,
    )
    positions = kmp_search("hello world", "world")          # → [6]
    positions = fuzzy_search("hello world", "wrold", k=1)   # → [6]
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
    for name in ("kmp_search", "bm_search", "rk_search", "so_search", "ac_search"):
        fn = getattr(lib, name)
        fn.restype  = ctypes.c_int
        fn.argtypes = _argtypes

    # fuzzy_search has an extra max_errors parameter
    lib.fuzzy_search.restype  = ctypes.c_int
    lib.fuzzy_search.argtypes = [
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


def _call_fuzzy(text: str, pattern: str, max_errors: int) -> list[int]:
    """Invoke fuzzy_search (7-arg signature with max_errors)."""
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

    count = _lib.fuzzy_search(
        b_text, len(b_text), b_pattern, len(b_pattern),
        max_errors, buf, _MAX_RESULTS,
    )
    if count < 0:
        raise ValueError(
            "fuzzy_search returned a negative code – likely a malloc failure."
        )
    return list(buf[:count])


# ─────────────────────────────────────────────────────────────────────────────
# Public wrappers
# ─────────────────────────────────────────────────────────────────────────────

def kmp_search(text: str, pattern: str) -> list[int]:
    """KMP search via C backend. O(n + m) guaranteed. Space O(m)."""
    return _call(_lib.kmp_search, text, pattern)


def bm_search(text: str, pattern: str) -> list[int]:
    """Boyer-Moore search via C backend. O(n/m) best case. Space O(m + σ)."""
    return _call(_lib.bm_search, text, pattern)


def rk_search(text: str, pattern: str) -> list[int]:
    """Rabin-Karp search via C backend. O(n + m) average. Space O(1)."""
    return _call(_lib.rk_search, text, pattern)


def so_search(text: str, pattern: str) -> list[int]:
    """Shift-Or (Bitap) search via C backend. O(n) for m ≤ 64. Space O(σ)."""
    return _call(_lib.so_search, text, pattern)


def ac_search(text: str, pattern: str) -> list[int]:
    """Aho-Corasick DFA search via C backend. O(n) after O(m·σ) build."""
    return _call(_lib.ac_search, text, pattern)


def fuzzy_search(text: str, pattern: str, max_errors: int = 1) -> list[int]:
    """
    Wu-Manber k-error Bitap search (fuzzy matching) via C backend.
    O(n·k) for m ≤ 64; O(n·m) Levenshtein DP fallback for m > 64.

    Args:
        max_errors: Maximum allowed edit distance (0–5).
    """
    return _call_fuzzy(text, pattern, max_errors)
