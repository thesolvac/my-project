"""
APME Heuristic Algorithm Selector
===================================
Determines which C-backend algorithm will perform best for a given input,
using purely rule-based logic derived from the theoretical complexity of
each algorithm.  No machine-learning or AI is used.

Six algorithms are available:
  kmp          – Knuth-Morris-Pratt       O(n+m) guaranteed
  boyer_moore  – Boyer-Moore (BC+GS)      O(n/m) best case
  rabin_karp   – Rabin-Karp               O(n+m) average
  shift_or     – Shift-Or / Bitap         O(n) for m ≤ 64 bytes
  aho_corasick – Aho-Corasick automaton   O(n) search after O(m·σ) build
  fuzzy        – Wu-Manber k-error Bitap  O(n·k); DP fallback for m > 64

Auto-selection decision table (for exact algorithms):
───────────────────────────────────────────────────────────────────────
Priority  Condition                                    Algorithm
────────  ───────────────────────────────────────────  ─────────────
2         m ≤ 2                                        KMP
2.5       m ≤ 64 AND ASCII-only pattern                Shift-Or
3         num_patterns > 1                             Aho-Corasick
4         alphabet cardinality σ ≤ 4  (binary/DNA)    KMP
5         repetitiveness ratio  > 70 %                KMP
6         m > 10  AND  σ > 10  AND  n > 5 000         Boyer-Moore
7         m ≤ 10  AND  n > 100 000                    Rabin-Karp
8         default                                      Boyer-Moore

Fuzzy and Aho-Corasick are also available as manual selections.

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
    KMP          = "kmp"
    BOYER_MOORE  = "boyer_moore"
    RABIN_KARP   = "rabin_karp"
    SHIFT_OR     = "shift_or"
    AHO_CORASICK = "aho_corasick"
    FUZZY        = "fuzzy"

    def display_name(self) -> str:
        names = {
            "kmp":          "KMP (Knuth-Morris-Pratt)",
            "boyer_moore":  "Boyer-Moore",
            "rabin_karp":   "Rabin-Karp",
            "shift_or":     "Shift-Or (Bitap)",
            "aho_corasick": "Aho-Corasick",
            "fuzzy":        "Fuzzy (Wu-Manber Bitap)",
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
    Algorithm.KMP: {
        "time_best":    "O(n + m)",
        "time_average": "O(n + m)",
        "time_worst":   "O(n + m)",
        "space":        "O(m)",
        "note":         "Guaranteed linear; never backtracks in text.",
    },
    Algorithm.BOYER_MOORE: {
        "time_best":    "O(n / m)",
        "time_average": "O(n / m)",
        "time_worst":   "O(n)  with GS table",
        "space":        "O(m + σ)",
        "note":         "Sub-linear on average; fastest for natural text.",
    },
    Algorithm.RABIN_KARP: {
        "time_best":    "O(n + m)",
        "time_average": "O(n + m)",
        "time_worst":   "O(n · m)  if many hash collisions",
        "space":        "O(1)",
        "note":         "Ideal for multi-pattern search; O(1) rolling update.",
    },
    Algorithm.SHIFT_OR: {
        "time_best":    "O(n)",
        "time_average": "O(n)",
        "time_worst":   "O(n · ⌈m/64⌉)",
        "space":        "O(σ)",
        "note":         "Bit-parallel NFA; O(n) for patterns ≤ 64 bytes.",
    },
    Algorithm.AHO_CORASICK: {
        "time_best":    "O(n + m·σ)",
        "time_average": "O(n)",
        "time_worst":   "O(n)",
        "space":        "O((m+1)·σ)",
        "note":         "Complete DFA; optimal for multi-pattern searches.",
    },
    Algorithm.FUZZY: {
        "time_best":    "O(n · k)",
        "time_average": "O(n · k)",
        "time_worst":   "O(n · m)  DP fallback for m > 64",
        "space":        "O(k + σ)  /  O(m)",
        "note":         "Wu-Manber Bitap; allows up to k edit-distance errors.",
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
                      A value > 1 triggers Rabin-Karp preference.
        manual:       If set, bypass heuristics and return this algorithm.
                      Accepted values: "kmp", "boyer_moore", "rabin_karp", "shift_or",
                         "aho_corasick", "fuzzy".

    Returns:
        HeuristicResult with the selected Algorithm and justification.
    """

    # ── Manual override ────────────────────────────────────────────────────
    if manual:
        try:
            algo = Algorithm(manual.lower().replace("-", "_").replace(" ", "_"))
        except ValueError:
            algo = Algorithm.BOYER_MOORE
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
            algorithm=Algorithm.KMP,
            justification=(
                f"Pattern length m={m} ≤ 2.  Boyer-Moore and Rabin-Karp "
                "preprocessing tables (O(m + σ) and O(m)) add overhead that "
                "cannot be recovered on such a short pattern.  KMP requires "
                "only an O(m) LPS table and is optimal here."
            ),
            complexity=COMPLEXITY[Algorithm.KMP],
        )

    # ── Rule 2.5: short ASCII pattern → Shift-Or ──────────────────────────
    if m <= 64 and pattern.isascii():
        return HeuristicResult(
            algorithm=Algorithm.SHIFT_OR,
            justification=(
                f"Pattern length m={m} ≤ 64 and pattern is ASCII-only.  "
                "Shift-Or encodes the NFA into a single 64-bit integer per "
                "character, achieving O(n) search with no branching and "
                "excellent cache behaviour.  No preprocessing table overhead "
                "beyond the O(σ) character bitmask array."
            ),
            complexity=COMPLEXITY[Algorithm.SHIFT_OR],
        )

    # ── Rule 3: multiple patterns → Aho-Corasick ─────────────────────────
    if num_patterns > 1:
        return HeuristicResult(
            algorithm=Algorithm.AHO_CORASICK,
            justification=(
                f"{num_patterns} patterns detected.  Aho-Corasick builds a "
                "single DFA over all patterns in O(m·σ) time, then scans the "
                "text once in O(n) — reporting every match for every pattern "
                "simultaneously.  KMP and Boyer-Moore each require a separate "
                "full text pass per pattern."
            ),
            complexity=COMPLEXITY[Algorithm.AHO_CORASICK],
        )

    sigma = _alphabet_size(text)
    rep   = _repetitiveness(text)

    # ── Rule 4: small alphabet (binary, DNA) ──────────────────────────────
    if sigma <= 4:
        return HeuristicResult(
            algorithm=Algorithm.KMP,
            justification=(
                f"Alphabet cardinality σ={sigma} ≤ 4 (binary or DNA-like text).  "
                "Boyer-Moore's Bad Character skip distance is bounded by σ, so "
                "with only 4 distinct characters the average skip ≈ 1 and "
                "worst-case degrades to O(n·m).  KMP's O(n+m) guarantee "
                "is strictly better here."
            ),
            complexity=COMPLEXITY[Algorithm.KMP],
        )

    # ── Rule 5: highly repetitive text ────────────────────────────────────
    if rep > 0.70:
        return HeuristicResult(
            algorithm=Algorithm.KMP,
            justification=(
                f"Text repetitiveness = {rep:.0%} (>{70}% same character).  "
                "Repetitive text is Boyer-Moore's worst-case trigger: mismatches "
                "are rare, bad-char skips are tiny, and runtime approaches O(n·m).  "
                "KMP's LPS-driven backtrack avoidance keeps time strictly O(n+m)."
            ),
            complexity=COMPLEXITY[Algorithm.KMP],
        )

    # ── Rule 6: long pattern + large alphabet + non-trivial text ──────────
    if m > 10 and sigma > 10 and n > 5_000:
        return HeuristicResult(
            algorithm=Algorithm.BOYER_MOORE,
            justification=(
                f"m={m} > 10, σ={sigma} > 10, n={n:,} > 5 000.  "
                "Boyer-Moore's Bad Character rule yields an average skip of "
                "≈ m·(1 − 1/σ) ≈ {m * (1 - 1/sigma):.1f} characters per step.  "
                "Expected sub-linear search time O(n/m) makes this the fastest "
                "choice for natural-language or source-code text."
            ),
            complexity=COMPLEXITY[Algorithm.BOYER_MOORE],
        )

    # ── Rule 7: short pattern in large text ───────────────────────────────
    if m <= 10 and n > 100_000:
        return HeuristicResult(
            algorithm=Algorithm.RABIN_KARP,
            justification=(
                f"m={m} ≤ 10 with large text n={n:,} > 100 000.  "
                "Short patterns offer Boyer-Moore little skip distance "
                "(avg skip ≈ m/σ ≈ {m/sigma:.2f}).  Rabin-Karp's O(1) "
                "rolling hash update maintains high throughput without "
                "the BC/GS table overhead."
            ),
            complexity=COMPLEXITY[Algorithm.RABIN_KARP],
        )

    # ── Default: Boyer-Moore for general natural text ─────────────────────
    return HeuristicResult(
        algorithm=Algorithm.BOYER_MOORE,
        justification=(
            "Default selection.  Boyer-Moore achieves the best average-case "
            "performance for general natural-language or mixed text where "
            "no specific degenerate condition was detected."
        ),
        complexity=COMPLEXITY[Algorithm.BOYER_MOORE],
    )
