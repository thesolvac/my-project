from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .heuristics import Algorithm, HeuristicResult, select_algorithm, COMPLEXITY
from . import c_bindings

_CONTEXT_CHARS = 60

@dataclass
class Match:
    position:       int
    line_number:    int
    snippet:        str
    context_before: str
    context_after:  str

@dataclass
class SearchResult:

    matches:         list[Match]
    match_count:     int

    algorithm:       str
    algorithm_display: str
    justification:   str
    complexity:      dict

    duration_ms:     float
    text_size_bytes: int
    throughput_mbs:  float

    pattern:         str
    pattern_length:  int
    text_snippet:    str
    mode:            str

    warnings:        list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
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
            "match_positions": [m.position for m in self.matches[:1000]],
        }

class APMEEngine:

    def __init__(self, context_chars: int = _CONTEXT_CHARS):
        self._ctx = context_chars

    def search(
        self,
        text:         str,
        pattern:      str,
        mode:         str = "auto",
        algorithm:    str | None = None,
        num_patterns: int = 1,
        max_errors:   int = 1,
    ) -> SearchResult:
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
        chunk_size: int = 65_536,
        encoding:   str = "utf-8",
        max_errors: int = 1,
    ) -> SearchResult:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        warnings: list[str] = []

        with path.open("r", encoding=encoding, errors="replace") as fh:
            sample = fh.read(10_000)

        manual = algorithm if mode == "manual" else None
        heuristic = select_algorithm(sample, pattern, manual=manual)

        pat_bytes = pattern.encode(encoding)
        overlap   = max(0, len(pat_bytes) - 1)

        all_positions: list[int] = []
        leftover      = ""
        global_offset = 0

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
                    if global_p >= global_offset - leftover_bytes + len(leftover.encode(encoding)) - overlap \
                            or not all_positions or global_p > all_positions[-1]:
                        all_positions.append(global_p)

                leftover       = segment[-overlap:] if overlap else ""
                global_offset += len(raw_chunk.encode(encoding))

        duration_s = time.perf_counter() - t0

        all_positions = sorted(set(all_positions))

        with path.open("r", encoding=encoding, errors="replace") as fh:
            text_snippet = fh.read(200)

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
        results: dict[str, SearchResult] = {}
        for algo in Algorithm:
            h = select_algorithm("", "", manual=algo.value)
            pos, dur = self._execute(algo, text, pattern, [], max_errors=max_errors)
            results[algo.value] = self._build_result(
                text, pattern, pos, h, dur, mode="compare", warnings=[]
            )
        return results

    def _execute(
        self,
        algo:       Algorithm,
        text:       str,
        pattern:    str,
        warnings:   list[str],
        max_errors: int = 1,
    ) -> tuple[list[int], float]:
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
        if not c_bindings.C_BACKEND_AVAILABLE:
            if not any("C backend" in w for w in warnings):
                warnings.append(
                    "C backend not compiled – using pure-Python KMP fallback.  "
                    "Run 'python build.py' or 'make' in src/c_backend to enable "
                    "optimised C algorithms."
                )
            return _python_exact_search(text, pattern)

        if algo == Algorithm.FUZZY_SEARCH:
            return c_bindings.fuzzysearch_search(text, pattern, max_errors)

        _fn_map = {
            Algorithm.DNA_SCAN:  c_bindings.dnascan_search,
            Algorithm.GAP_JUMP:  c_bindings.gapjump_search,
            Algorithm.DUAL_RABIN: c_bindings.dualrabin_search,
            Algorithm.BIT_MATCH: c_bindings.bitmatch_search,
            Algorithm.SWEEP_RUN: c_bindings.sweeprun_search,
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

def _python_exact_search(text: str, pattern: str) -> list[int]:
    m, n = len(pattern), len(text)
    if m == 0 or n < m:
        return []

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
