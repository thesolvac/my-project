from __future__ import annotations

import ctypes
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "c_backend"
_MAX_RESULTS = 1_000_000

def _find_library() -> Path:
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
    _argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_int,
    ]
    for name in ("dnascan_search", "gapjump_search", "dualrabin_search",
                 "bitmatch_search", "sweeprun_search"):
        fn = getattr(lib, name)
        fn.restype  = ctypes.c_int
        fn.argtypes = _argtypes

    lib.fuzzysearch_search.restype  = ctypes.c_int  # extra max_errors arg
    lib.fuzzysearch_search.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_int,
    ]

    lib.sweeprun_search_multi.restype  = ctypes.c_int  # multi-pattern Aho-Corasick
    lib.sweeprun_search_multi.argtypes = [
        ctypes.c_char_p,                       # text
        ctypes.c_int,                          # text_len
        ctypes.POINTER(ctypes.c_char_p),       # patterns[]
        ctypes.POINTER(ctypes.c_int),          # pat_lens[]
        ctypes.c_int,                          # n_patterns
        ctypes.POINTER(ctypes.c_int),          # positions[]
        ctypes.POINTER(ctypes.c_int),          # pattern_ids[]
        ctypes.c_int,                          # max_res
    ]
    return lib

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

def _call(fn: ctypes.CFUNCTYPE, text: str, pattern: str) -> list[int]:
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

def _call_fuzzysearch(text: str, pattern: str, max_errors: int) -> list[int]:
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

    count = _lib.fuzzysearch_search(
        b_text, len(b_text), b_pattern, len(b_pattern),
        max_errors, buf, _MAX_RESULTS,
    )
    if count < 0:
        raise ValueError(
            "fuzzysearch_search returned a negative code – likely a malloc failure."
        )
    return list(buf[:count])

def dnascan_search(text: str, pattern: str) -> list[int]:
    return _call(_lib.dnascan_search, text, pattern)

def gapjump_search(text: str, pattern: str) -> list[int]:
    return _call(_lib.gapjump_search, text, pattern)

def dualrabin_search(text: str, pattern: str) -> list[int]:
    return _call(_lib.dualrabin_search, text, pattern)

def bitmatch_search(text: str, pattern: str) -> list[int]:
    return _call(_lib.bitmatch_search, text, pattern)

def sweeprun_search(text: str, pattern: str) -> list[int]:
    return _call(_lib.sweeprun_search, text, pattern)

def sweeprun_search_multi(text: str, patterns: list[str]) -> list[tuple[int, int]]:
    """Multi-pattern Aho-Corasick search.

    Returns a list of (position, pattern_id) pairs, where pattern_id indexes
    into ``patterns``. Positions are byte offsets in the UTF-8 encoded text.
    """
    if not C_BACKEND_AVAILABLE:
        raise RuntimeError(
            f"C backend unavailable – using Python fallback.\nDetails: {_load_error}"
        )
    if not text or not patterns:
        return []

    b_text = text.encode("utf-8")
    enc    = [p.encode("utf-8") for p in patterns]   # keep alive during the call
    n      = len(enc)

    arr_pat  = (ctypes.c_char_p * n)(*enc)
    arr_len  = (ctypes.c_int * n)(*[len(p) for p in enc])
    pos_buf  = (ctypes.c_int * _MAX_RESULTS)()
    id_buf   = (ctypes.c_int * _MAX_RESULTS)()

    count = _lib.sweeprun_search_multi(
        b_text, len(b_text), arr_pat, arr_len, n, pos_buf, id_buf, _MAX_RESULTS
    )
    if count < 0:
        raise ValueError(
            "sweeprun_search_multi returned a negative code – likely a malloc failure."
        )
    return list(zip(pos_buf[:count], id_buf[:count]))

def fuzzysearch_search(text: str, pattern: str, max_errors: int = 1) -> list[int]:
    return _call_fuzzysearch(text, pattern, max_errors)
