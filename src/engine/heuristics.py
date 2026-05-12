"""
APME Heuristic Algorithm Selector
===================================
Determines which C-backend algorithm will perform best for a given input,
using purely rule-based logic derived from the theoretical complexity of
each algorithm.  No machine-learning or AI is used.

Six APME proprietary algorithms are available:
  flow_scan   – FlowScan  (LPS table + memchr anchor)           O(n/σ₀) best, O(n+m) worst
  skip_stride – SkipStride (triple-heuristic skip search)       O(n/(m+1)) best
  twin_hash   – TwinHash  (dual rolling hash)                   O(n+m) avg, ≈10⁻¹⁸ false-pos
  bit_anchor  – BitAnchor (NFA bit-parallel + dead-state skip)  O(n) for m ≤ 64
  web_scan    – WebScan   (DFA automaton + presence bitmap)      O(n) search after O(m·σ) build
  tier_match  – TierMatch (approximate NFA + best-tier dedup)   O(n·k); DP fallback for m > 64

Auto-selection decision table (for exact algorithms):
───────────────────────────────────────────────────────────────────────
Priority  Condition                                    Algorithm
────────  ───────────────────────────────────────────  ─────────────
2         m ≤ 2                                        FlowScan
2.5       m ≤ 64 AND ASCII-only pattern                BitAnchor
3         num_patterns > 1                             WebScan
4         alphabet cardinality σ ≤ 4  (binary/DNA)    FlowScan
5         repetitiveness ratio  > 70 %                FlowScan
6         m > 10  AND  σ > 10  AND  n > 5 000         SkipStride
7         m ≤ 10  AND  n > 100 000                    TwinHash
8         default                                      SkipStride

TierMatch and WebScan are also available as manual selections.

References
----------
Crochemore & Rytter, "Text Algorithms", OUP, 1994.
Navarro & Raffinot, "Flexible Pattern Matching in Strings", CUP, 2002.
Wu & Manber, "Fast Text Searching Allowing Errors", CACM 35(10), 1992.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# Public types
# ─────────────────────────────────────────────────────────────────────────────

class Algorithm(str, Enum):
    FLOW_SCAN   = "flow_scan"
    SKIP_STRIDE = "skip_stride"
    TWIN_HASH   = "twin_hash"
    BIT_ANCHOR  = "bit_anchor"
    WEB_SCAN    = "web_scan"
    TIER_MATCH  = "tier_match"

    def display_name(self) -> str:
        names = {
            "flow_scan":   "FlowScan",
            "skip_stride": "SkipStride",
            "twin_hash":   "TwinHash",
            "bit_anchor":  "BitAnchor",
            "web_scan":    "WebScan",
            "tier_match":  "TierMatch",
        }
        return names[self.value]


@dataclass(frozen=True)
class HeuristicResult:
    """Carries the selected algorithm and a human-readable justification."""
    algorithm:     Algorithm
    justification: str
    complexity:    dict[str, str]   # Big-O table for UI display


# ─────────────────────────────────────────────────────────────────────────────
# Per-algorithm complexity reference (shown in the results UI)
# ─────────────────────────────────────────────────────────────────────────────

COMPLEXITY: dict[Algorithm, dict[str, str]] = {
    Algorithm.FLOW_SCAN: {
        "time_best":    "O(n / σ₀)",
        "time_average": "O(n + m)",
        "time_worst":   "O(n + m)",
        "space":        "O(m)",
        "note":         "memchr anchor skips dead-state loops; LPS table unchanged.",
    },
    Algorithm.SKIP_STRIDE: {
        "time_best":    "O(n / (m + 1))",
        "time_average": "O(n)",
        "time_worst":   "O(n)  with GS table",
        "space":        "O(m + σ)",
        "note":         "Sunday bonus shift adds one extra byte skipped per window.",
    },
    Algorithm.TWIN_HASH: {
        "time_best":    "O(n + m)",
        "time_average": "O(n + m)",
        "time_worst":   "O(n · m)  — deliberate collision only",
        "space":        "O(1)",
        "note":         "Dual hash reduces false-positive probability to ≈ 10⁻¹⁸.",
    },
    Algorithm.BIT_ANCHOR: {
        "time_best":    "O(n)",
        "time_average": "O(n)",
        "time_worst":   "O(n · ⌈m/64⌉)",
        "space":        "O(σ)",
        "note":         "memchr jumps from dead-NFA to next pattern[0] occurrence.",
    },
    Algorithm.WEB_SCAN: {
        "time_best":    "O(n + m·σ)",
        "time_average": "O(n)",
        "time_worst":   "O(n)",
        "space":        "O((m+1)·σ) + 32 bytes",
        "note":         "256-bit presence bitmap bypasses DFA for non-pattern bytes.",
    },
    Algorithm.TIER_MATCH: {
        "time_best":    "O(n · k)",
        "time_average": "O(n · k)",
        "time_worst":   "O(n · m)  DP fallback for m > 64",
        "space":        "O(k + σ)  /  O(m)",
        "note":         "Best-tier dedup: one result per position at lowest edit distance.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Input analysis helpers
# ─────────────────────────────────────────────────────────────────────────────

_SAMPLE_CAP = 10_000   # analyse at most this many characters for speed


def _alphabet_size(text: str) -> int:
    """Count distinct characters in the first _SAMPLE_CAP chars of text."""
    return len(set(text[:_SAMPLE_CAP]))


def _repetitiveness(text: str) -> float:
    """
    Fraction of the sample occupied by the single most-frequent character.
    Returns a value in [0, 1].  > 0.70 indicates highly repetitive text.
    """
    if not text:
        return 0.0
    sample = text[:_SAMPLE_CAP]
    top_freq = max(sample.count(c) for c in set(sample))
    return top_freq / len(sample)


# ─────────────────────────────────────────────────────────────────────────────
# Public selector
# ─────────────────────────────────────────────────────────────────────────────

def select_algorithm(
    text:         str,
    pattern:      str,
    num_patterns: int = 1,
    manual:       str | None = None,
) -> HeuristicResult:
    """
    Choose the best string-matching algorithm for the given input.

    Args:
        text:         Full text (or a representative sample) to search.
        pattern:      Primary search pattern.
        num_patterns: Number of distinct patterns in this session.
                      A value > 1 triggers WebScan preference.
        manual:       If set, bypass heuristics and return this algorithm.
                      Accepted values: "flow_scan", "skip_stride", "twin_hash",
                         "bit_anchor", "web_scan", "tier_match".

    Returns:
        HeuristicResult with the selected Algorithm and justification.
    """

    # ── Manual override ────────────────────────────────────────────────────
    if manual:
        try:
            algo = Algorithm(manual.lower().replace("-", "_").replace(" ", "_"))
        except ValueError:
            algo = Algorithm.SKIP_STRIDE
        return HeuristicResult(
            algorithm=algo,
            justification=f"Manual selection: {algo.display_name()}.",
            complexity=COMPLEXITY[algo],
        )

    m = len(pattern)
    n = len(text)

    # ── Rule 2: trivial / very short pattern ──────────────────────────────
    if m <= 2:
        return HeuristicResult(
            algorithm=Algorithm.FLOW_SCAN,
            justification=(
                f"Pattern length m={m} ≤ 2.  SkipStride and TwinHash "
                "preprocessing tables (O(m + σ) and O(m)) add overhead that "
                "cannot be recovered on such a short pattern.  FlowScan requires "
                "only an O(m) LPS table and is optimal here."
            ),
            complexity=COMPLEXITY[Algorithm.FLOW_SCAN],
        )

    # ── Rule 2.5: short ASCII pattern → BitAnchor ─────────────────────────
    if m <= 64 and pattern.isascii():
        return HeuristicResult(
            algorithm=Algorithm.BIT_ANCHOR,
            justification=(
                f"Pattern length m={m} ≤ 64 and pattern is ASCII-only.  "
                "BitAnchor encodes the NFA into a single 64-bit integer per "
                "character, achieving O(n) search with no branching and "
                "excellent cache behaviour.  When the NFA drops to the dead "
                "state, memchr fast-forwards to the next pattern[0] occurrence."
            ),
            complexity=COMPLEXITY[Algorithm.BIT_ANCHOR],
        )

    # ── Rule 3: multiple patterns → WebScan ───────────────────────────────
    if num_patterns > 1:
        return HeuristicResult(
            algorithm=Algorithm.WEB_SCAN,
            justification=(
                f"{num_patterns} patterns detected.  WebScan builds a "
                "single DFA automaton over all patterns in O(m·σ) time, "
                "then scans the text once in O(n) — reporting every match for "
                "every pattern simultaneously.  The 256-bit presence bitmap "
                "further bypasses DFA lookups for bytes absent from all patterns."
            ),
            complexity=COMPLEXITY[Algorithm.WEB_SCAN],
        )

    sigma = _alphabet_size(text)
    rep   = _repetitiveness(text)

    # ── Rule 4: small alphabet (binary, DNA) ──────────────────────────────
    if sigma <= 4:
        return HeuristicResult(
            algorithm=Algorithm.FLOW_SCAN,
            justification=(
                f"Alphabet cardinality σ={sigma} ≤ 4 (binary or DNA-like text).  "
                "SkipStride's Bad Character skip distance is bounded by σ, so "
                "with only 4 distinct characters the average skip ≈ 1 and "
                "worst-case degrades to O(n·m).  FlowScan's O(n+m) guarantee "
                "is strictly better here, and the memchr anchor exploits rare "
                "occurrences of pattern[0] when available."
            ),
            complexity=COMPLEXITY[Algorithm.FLOW_SCAN],
        )

    # ── Rule 5: highly repetitive text ────────────────────────────────────
    if rep > 0.70:
        return HeuristicResult(
            algorithm=Algorithm.FLOW_SCAN,
            justification=(
                f"Text repetitiveness = {rep:.0%} (>{70}% same character).  "
                "Repetitive text is SkipStride's worst-case trigger: mismatches "
                "are rare, bad-char skips are tiny, and runtime approaches O(n·m).  "
                "FlowScan's LPS-driven backtrack avoidance keeps time strictly O(n+m)."
            ),
            complexity=COMPLEXITY[Algorithm.FLOW_SCAN],
        )

    # ── Rule 6: long pattern + large alphabet + non-trivial text ──────────
    if m > 10 and sigma > 10 and n > 5_000:
        return HeuristicResult(
            algorithm=Algorithm.SKIP_STRIDE,
            justification=(
                f"m={m} > 10, σ={sigma} > 10, n={n:,} > 5 000.  "
                "SkipStride's Bad Character rule yields an average skip of "
                f"≈ m·(1 − 1/σ) ≈ {m * (1 - 1/sigma):.1f} characters per step.  "
                "The Sunday bonus shift inspects the byte past the window, "
                "pushing the best case to O(n/(m+1)) — fastest for natural-language "
                "or source-code text."
            ),
            complexity=COMPLEXITY[Algorithm.SKIP_STRIDE],
        )

    # ── Rule 7: short pattern in large text ───────────────────────────────
    if m <= 10 and n > 100_000:
        return HeuristicResult(
            algorithm=Algorithm.TWIN_HASH,
            justification=(
                f"m={m} ≤ 10 with large text n={n:,} > 100 000.  "
                "Short patterns offer SkipStride little skip distance "
                f"(avg skip ≈ m/σ ≈ {m/sigma:.2f}).  TwinHash's O(1) "
                "dual rolling hash update maintains high throughput; the "
                "second independent hash drops false-positive probability "
                "to ≈ 10⁻¹⁸, eliminating verification overhead entirely."
            ),
            complexity=COMPLEXITY[Algorithm.TWIN_HASH],
        )

    # ── Default: SkipStride for general natural text ───────────────────────
    return HeuristicResult(
        algorithm=Algorithm.SKIP_STRIDE,
        justification=(
            "Default selection.  SkipStride achieves the best average-case "
            "performance for general natural-language or mixed text where "
            "no specific degenerate condition was detected.  The Sunday bonus "
            "shift provides an extra stride beyond the classic base algorithm."
        ),
        complexity=COMPLEXITY[Algorithm.SKIP_STRIDE],
    )
