"""
APME – Adaptive Pattern Matching Engine  (Orchestration Layer)
===============================================================
Orchestrates the complete search pipeline:

  1. Input validation & edge-case handling
  2. Heuristic algorithm selection           (heuristics.py)
  3. C-backend algorithm execution           (c_bindings.py)
  4. Streaming support for large files       (chunked reads with overlap)
  5. Result normalisation & context snippets
  6. Performance metrics collection

Public API
----------
    engine = APMEEngine()

    # In-memory search
    result = engine.search(text, pattern)
    result = engine.search(text, pattern, mode="manual", algorithm="flow_scan")

    # File search with streaming
    result = engine.search_file("/path/to/large.log", pattern)

    # Comparative mode (runs all six, returns dict of SearchResult)
    results = engine.compare(text, pattern)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .heuristics import Algorithm, HeuristicResult, select_algorithm, COMPLEXITY
from . import c_bindings


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

_CONTEXT_CHARS = 60   # characters of surrounding text shown per match


@dataclass
class Match:
    """A single occurrence of the pattern in the text."""
    position:       int    # byte index in the (potentially global) text
    line_number:    int    # 1-based line number estimate
    snippet:        str    # the matched text itself
    context_before: str    # up to _CONTEXT_CHARS chars before the match
    context_after:  str    # up to _CONTEXT_CHARS chars after the match


@dataclass
class SearchResult:
    """Complete output of one APME search operation."""

    # ── Match data ──────────────────────────────────────────────────
    matches:         list[Match]
    match_count:     int

    # ── Algorithm metadata ──────────────────────────────────────────
    algorithm:       str          # "flow_scan" | "skip_stride" | "twin_hash" | "bit_anchor" | "web_scan" | "tier_match"
    algorithm_display: str        # human-readable name
    justification:   str          # why this algorithm was selected
    complexity:      dict         # Big-O table

    # ── Performance metrics ─────────────────────────────────────────
    duration_ms:     float        # wall-clock time in milliseconds
    text_size_bytes: int
    throughput_mbs:  float        # MB/s throughput

    # ── Input metadata ──────────────────────────────────────────────
    pattern:         str
    pattern_length:  int
    text_snippet:    str          # first 200 chars of input (for display)
    mode:            str          # "auto" | "manual"

    # ── Warnings ────────────────────────────────────────────────────
    warnings:        list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a JSON-friendly dict (for MongoDB storage)."""
        return {
            "match_count":       self.match_count,
            "algorithm":         self.algorithm,
            "algorithm_display": self.algorithm_display,
            "justification":     self.justification,
            "complexity":        self.complexity,
            "duration_ms":       self.duration_ms,
            "text_size_bytes":   self.text_size_bytes,
            "throughput_mbs":    self.throughput_mbs,
            "pattern":           self.pattern,
            "pattern_length":    self.pattern_length,
            "mode":              self.mode,
            "warnings":          self.warnings,
            # Matches are stored separately to keep documents small
            "match_positions": [m.position for m in self.matches[:1000]],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

class APMEEngine:
    """
    The central orchestrator of the Adaptive Pattern Matching Engine.

    The engine is stateless between calls; a single instance can serve
    multiple concurrent requests (it holds no mutable per-search state).
    """

    def __init__(self, context_chars: int = _CONTEXT_CHARS):
        self._ctx = context_chars

    # ── Public interface ─────────────────────────────────────────────────

    def search(
        self,
        text:         str,
        pattern:      str,
        mode:         str = "auto",
        algorithm:    str | None = None,
        num_patterns: int = 1,
        max_errors:   int = 1,
    ) -> SearchResult:
        """
        Search for *pattern* in *text* (in-memory).

        Args:
            text:         Text to search within.
            pattern:      Pattern to find.
            mode:         "auto"   – heuristic selects the algorithm.
                          "manual" – use the *algorithm* argument.
            algorithm:    Explicit algorithm name (only when mode=="manual").
                          One of: "flow_scan", "skip_stride", "twin_hash",
                                  "bit_anchor", "web_scan", "tier_match".
            num_patterns: Hint that multiple patterns will be searched.
                          A value > 1 biases selection toward WebScan.
            max_errors:   Maximum edit distance for fuzzy matching (0–5).

        Returns:
            SearchResult populated with matches and performance data.
        """
        warnings: list[str] = []

        if not pattern:
            return self._empty("Pattern is empty.", pattern, text, mode, warnings)
        if not text:
            return self._empty("Text is empty.", pattern, text, mode, warnings)

        manual = algorithm if mode == "manual" else None
        heuristic: HeuristicResult = select_algorithm(
            text, pattern, num_patterns=num_patterns, manual=manual
        )

        positions, duration_s = self._execute(
            heuristic.algorithm, text, pattern, warnings, max_errors=max_errors
        )

        return self._build_result(text, pattern, positions, heuristic, duration_s, mode, warnings)

    def search_file(
        self,
        file_path:  str | Path,
        pattern:    str,
        mode:       str = "auto",
        algorithm:  str | None = None,
        chunk_size: int = 65_536,   # 64 KB per read
        encoding:   str = "utf-8",
        max_errors: int = 1,
    ) -> SearchResult:
        """
        Memory-efficient streaming search over a large file.

        Reads the file in overlapping chunks to avoid missing cross-boundary
        matches.  Overlap width = len(pattern.encode()) − 1, ensuring that
        any match spanning two consecutive chunks is captured exactly once.

        Args:
            file_path:  Path to the target file.
            pattern:    Pattern to search for.
            mode:       "auto" or "manual".
            algorithm:  Explicit algorithm (only when mode=="manual").
            chunk_size: Bytes to read per iteration (default 64 KB).
            encoding:   File encoding (default UTF-8; falls back to 'replace').

        Returns:
            SearchResult with globally-adjusted match positions.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        warnings: list[str] = []

        # Read a small sample for heuristic analysis
        with path.open("r", encoding=encoding, errors="replace") as fh:
            sample = fh.read(10_000)

        manual = algorithm if mode == "manual" else None
        heuristic = select_algorithm(sample, pattern, manual=manual)

        pat_bytes = pattern.encode(encoding)
        overlap   = max(0, len(pat_bytes) - 1)

        all_positions: list[int] = []
        leftover      = ""
        global_offset = 0            # byte offset into the file

        t0 = time.perf_counter()

        with path.open("r", encoding=encoding, errors="replace") as fh:
            while True:
                raw_chunk = fh.read(chunk_size)
                if not raw_chunk:
                    break

                segment  = leftover + raw_chunk
                raw_pos  = self._dispatch(heuristic.algorithm, segment, pattern, warnings, max_errors=max_errors)

                leftover_bytes = len(leftover.encode(encoding))

                for p in raw_pos:
                    global_p = global_offset - leftover_bytes + p
                    # De-duplicate positions that fall inside the leftover region
                    # (they were already captured in the previous iteration)
                    if global_p >= global_offset - leftover_bytes + len(leftover.encode(encoding)) - overlap \
                            or not all_positions or global_p > all_positions[-1]:
                        all_positions.append(global_p)

                leftover       = segment[-overlap:] if overlap else ""
                global_offset += len(raw_chunk.encode(encoding))

        duration_s = time.perf_counter() - t0

        # De-duplicate and sort (small redundancy can occur at chunk boundaries)
        all_positions = sorted(set(all_positions))

        with path.open("r", encoding=encoding, errors="replace") as fh:
            text_snippet = fh.read(200)

        # Build rich Match objects using the in-memory sample as context source
        matches = self._build_matches(sample, pattern, all_positions[:500])

        file_bytes = path.stat().st_size
        return SearchResult(
            matches=matches,
            match_count=len(all_positions),
            algorithm=heuristic.algorithm.value,
            algorithm_display=heuristic.algorithm.display_name(),
            justification=heuristic.justification,
            complexity=heuristic.complexity,
            duration_ms=round(duration_s * 1000, 4),
            text_size_bytes=file_bytes,
            throughput_mbs=round((file_bytes / 1_048_576) / duration_s, 2) if duration_s else 0.0,
            pattern=pattern,
            pattern_length=len(pattern),
            text_snippet=text_snippet,
            mode=mode,
            warnings=warnings,
        )

    def compare(
        self,
        text:       str,
        pattern:    str,
        max_errors: int = 1,
    ) -> dict[str, SearchResult]:
        """
        Run all six algorithms and return their individual SearchResults.
        Used by the "Compare Mode" UI to display a side-by-side benchmark.

        Returns:
            Dict mapping algorithm name → SearchResult.
        """
        results: dict[str, SearchResult] = {}
        for algo in Algorithm:
            h = select_algorithm("", "", manual=algo.value)
            pos, dur = self._execute(algo, text, pattern, [], max_errors=max_errors)
            results[algo.value] = self._build_result(
                text, pattern, pos, h, dur, mode="compare", warnings=[]
            )
        return results

    # ── Private helpers ──────────────────────────────────────────────────

    def _execute(
        self,
        algo:       Algorithm,
        text:       str,
        pattern:    str,
        warnings:   list[str],
        max_errors: int = 1,
    ) -> tuple[list[int], float]:
        """Run the algorithm and return (positions, duration_seconds)."""
        t0 = time.perf_counter()
        positions = self._dispatch(algo, text, pattern, warnings, max_errors=max_errors)
        return positions, time.perf_counter() - t0

    def _dispatch(
        self,
        algo:       Algorithm,
        text:       str,
        pattern:    str,
        warnings:   list[str],
        max_errors: int = 1,
    ) -> list[int]:
        """Call the appropriate C binding, falling back to Python FlowScan if needed."""
        if not c_bindings.C_BACKEND_AVAILABLE:
            if not any("C backend" in w for w in warnings):
                warnings.append(
                    "C backend not compiled – using pure-Python FlowScan fallback.  "
                    "Run 'python build.py' or 'make' in src/c_backend to enable "
                    "optimised C algorithms."
                )
            return _python_flowscan(text, pattern)

        if algo == Algorithm.TIER_MATCH:
            return c_bindings.tiermatch_search(text, pattern, max_errors)

        _fn_map = {
            Algorithm.FLOW_SCAN:   c_bindings.flowscan_search,
            Algorithm.SKIP_STRIDE: c_bindings.skipstride_search,
            Algorithm.TWIN_HASH:   c_bindings.twinhash_search,
            Algorithm.BIT_ANCHOR:  c_bindings.bitanchor_search,
            Algorithm.WEB_SCAN:    c_bindings.webscan_search,
        }
        return _fn_map[algo](text, pattern)

    def _build_result(
        self,
        text:      str,
        pattern:   str,
        positions: list[int],
        heuristic: HeuristicResult,
        duration_s: float,
        mode:      str,
        warnings:  list[str],
    ) -> SearchResult:
        matches    = self._build_matches(text, pattern, positions)
        text_bytes = len(text.encode("utf-8"))
        dur_ms     = round(duration_s * 1000, 4)
        tput       = round((text_bytes / 1_048_576) / duration_s, 2) if duration_s > 0 else 0.0
        return SearchResult(
            matches=matches,
            match_count=len(matches),
            algorithm=heuristic.algorithm.value,
            algorithm_display=heuristic.algorithm.display_name(),
            justification=heuristic.justification,
            complexity=heuristic.complexity,
            duration_ms=dur_ms,
            text_size_bytes=text_bytes,
            throughput_mbs=tput,
            pattern=pattern,
            pattern_length=len(pattern),
            text_snippet=text[:200],
            mode=mode,
            warnings=warnings,
        )

    def _build_matches(
        self,
        text:      str,
        pattern:   str,
        positions: list[int],
    ) -> list[Match]:
        """Convert raw index list into rich Match objects with context."""
        cc  = self._ctx
        pm  = len(pattern)
        out = []
        for pos in positions:
            if pos < 0 or pos + pm > len(text):
                continue
            start = max(0, pos - cc)
            end   = min(len(text), pos + pm + cc)
            out.append(Match(
                position=pos,
                line_number=text[:pos].count("\n") + 1,
                snippet=text[pos: pos + pm],
                context_before=text[start: pos],
                context_after=text[pos + pm: end],
            ))
        return out

    def _empty(
        self,
        reason:   str,
        pattern:  str,
        text:     str,
        mode:     str,
        warnings: list[str],
    ) -> SearchResult:
        warnings.append(reason)
        return SearchResult(
            matches=[], match_count=0,
            algorithm="none", algorithm_display="N/A",
            justification=reason, complexity={},
            duration_ms=0.0,
            text_size_bytes=len(text.encode("utf-8", errors="replace")),
            throughput_mbs=0.0,
            pattern=pattern, pattern_length=len(pattern),
            text_snippet=text[:200], mode=mode, warnings=warnings,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python FlowScan fallback (used when C library is unavailable)
# ─────────────────────────────────────────────────────────────────────────────

def _python_flowscan(text: str, pattern: str) -> list[int]:
    """
    Pure-Python FlowScan implementation (LPS-based exact search).
    Activated automatically when the C shared library cannot be loaded.
    O(n + m) time, O(m) space.
    """
    m, n = len(pattern), len(text)
    if m == 0 or n < m:
        return []

    # Build LPS table
    lps = [0] * m
    length, i = 0, 1
    while i < m:
        if pattern[i] == pattern[length]:
            length += 1
            lps[i]  = length
            i      += 1
        elif length:
            length = lps[length - 1]
        else:
            i += 1

    results, i, j = [], 0, 0
    while i < n:
        if pattern[j] == text[i]:
            i += 1
            j += 1
        if j == m:
            results.append(i - j)
            j = lps[j - 1]
        elif i < n and pattern[j] != text[i]:
            j = lps[j - 1] if j else 0
            if not j:
                i += 1
    return results
