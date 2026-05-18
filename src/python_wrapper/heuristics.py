from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

class Algorithm(str, Enum):
    DNA_SCAN     = "dna_scan"
    GAP_JUMP     = "gap_jump"
    DUAL_RABIN   = "dual_rabin"
    BIT_MATCH    = "bit_match"
    SWEEP_RUN    = "sweep_run"
    FUZZY_SEARCH = "fuzzy_search"

    def display_name(self) -> str:
        names = {
            "dna_scan":     "DNAScan",
            "gap_jump":     "GapJump",
            "dual_rabin":   "DualRabin",
            "bit_match":    "BitMatch",
            "sweep_run":    "SweepRun",
            "fuzzy_search": "FuzzySearch",
        }
        return names[self.value]

@dataclass(frozen=True)
class HeuristicResult:
    algorithm:     Algorithm
    justification: str
    complexity:    dict[str, str]

COMPLEXITY: dict[Algorithm, dict[str, str]] = {
    Algorithm.DNA_SCAN: {
        "time_best":    "O(n / σ₀)",
        "time_average": "O(n + m)",
        "time_worst":   "O(n + m)",
        "space":        "O(m)",
        "note":         "Bigram anchor skips dead-state loops; LPS table unchanged.",
    },
    Algorithm.GAP_JUMP: {
        "time_best":    "O(n / (m + 1))",
        "time_average": "O(n)",
        "time_worst":   "O(n)  with GS table",
        "space":        "O(m + σ)",
        "note":         "2-gram bad-character table of 65,536 byte-pairs; Sunday bonus shift adds one extra byte skipped per window.",
    },
    Algorithm.DUAL_RABIN: {
        "time_best":    "O(n + m)",
        "time_average": "O(n + m)",
        "time_worst":   "O(n · m)  — deliberate collision only",
        "space":        "O(1)",
        "note":         "4-layer hierarchical filter + SSE2; dual hash reduces false-positive probability to ≈ 10⁻²².",
    },
    Algorithm.BIT_MATCH: {
        "time_best":    "O(n)",
        "time_average": "O(n)",
        "time_worst":   "O(n · ⌈m/64⌉)",
        "space":        "O(σ)",
        "note":         "Bidirectional NFA around internal anchor; memchr jumps from dead-NFA to next anchor occurrence.",
    },
    Algorithm.SWEEP_RUN: {
        "time_best":    "O(n + m·σ)",
        "time_average": "O(n)",
        "time_worst":   "O(n)",
        "space":        "O((m+1)·σ) + 32 bytes",
        "note":         "True Aho-Corasick DFA with densification; 256-bit presence bitmap bypasses DFA for non-pattern bytes.",
    },
    Algorithm.FUZZY_SEARCH: {
        "time_best":    "O(n · k)",
        "time_average": "O(n · k)",
        "time_worst":   "O(n · m)  DP fallback for m > 64",
        "space":        "O(k + σ)  /  O(m)",
        "note":         "Myers bit-parallel (JACM 1999); one result per position at lowest edit distance.",
    },
}

_SAMPLE_CAP = 10_000

def _alphabet_size(text: str) -> int:
    return len(set(text[:_SAMPLE_CAP]))

def _repetitiveness(text: str) -> float:
    if not text:
        return 0.0
    sample = text[:_SAMPLE_CAP]
    top_freq = max(sample.count(c) for c in set(sample))
    return top_freq / len(sample)

def select_algorithm(
    text:         str,
    pattern:      str,
    num_patterns: int = 1,
    manual:       str | None = None,
) -> HeuristicResult:

    if manual:
        try:
            algo = Algorithm(manual.lower().replace("-", "_").replace(" ", "_"))
        except ValueError:
            algo = Algorithm.GAP_JUMP
        return HeuristicResult(
            algorithm=algo,
            justification=f"Manual selection: {algo.display_name()}.",
            complexity=COMPLEXITY[algo],
        )

    m = len(pattern)
    n = len(text)

    if m <= 2:
        return HeuristicResult(
            algorithm=Algorithm.DNA_SCAN,
            justification=(
                f"Pattern length m={m} ≤ 2.  GapJump and DualRabin "
                "preprocessing tables (O(m + σ) and O(m)) add overhead that "
                "cannot be recovered on such a short pattern.  DNAScan requires "
                "only an O(m) LPS table and is optimal here."
            ),
            complexity=COMPLEXITY[Algorithm.DNA_SCAN],
        )

    if m <= 64 and pattern.isascii():
        return HeuristicResult(
            algorithm=Algorithm.BIT_MATCH,
            justification=(
                f"Pattern length m={m} ≤ 64 and pattern is ASCII-only.  "
                "BitMatch encodes two NFA bitvectors around an internal anchor "
                "into 64-bit integers, achieving O(n) search with no branching "
                "and excellent cache behaviour.  When the NFA drops to the dead "
                "state, memchr fast-forwards to the next anchor occurrence."
            ),
            complexity=COMPLEXITY[Algorithm.BIT_MATCH],
        )

    if num_patterns > 1:
        return HeuristicResult(
            algorithm=Algorithm.SWEEP_RUN,
            justification=(
                f"{num_patterns} patterns detected.  SweepRun builds a "
                "true Aho-Corasick DFA over all patterns in O(m·σ) time, "
                "then scans the text once in O(n) — reporting every match for "
                "every pattern simultaneously.  Densification and the 256-bit "
                "presence bitmap further bypass DFA lookups for bytes absent "
                "from all patterns."
            ),
            complexity=COMPLEXITY[Algorithm.SWEEP_RUN],
        )

    sigma = _alphabet_size(text)
    rep   = _repetitiveness(text)

    if sigma <= 4:
        return HeuristicResult(
            algorithm=Algorithm.DNA_SCAN,
            justification=(
                f"Alphabet cardinality σ={sigma} ≤ 4 (binary or DNA-like text).  "
                "GapJump's 2-gram Bad Character skip distance is bounded by σ², so "
                "with only 4 distinct characters the average skip ≈ 1 and "
                "worst-case degrades to O(n·m).  DNAScan's O(n+m) guarantee "
                "is strictly better here, and the bigram anchor exploits rare "
                "byte-pair occurrences when available."
            ),
            complexity=COMPLEXITY[Algorithm.DNA_SCAN],
        )

    if rep > 0.70:
        return HeuristicResult(
            algorithm=Algorithm.DNA_SCAN,
            justification=(
                f"Text repetitiveness = {rep:.0%} (>{70}% same character).  "
                "Repetitive text is GapJump's worst-case trigger: mismatches "
                "are rare, bad-char skips are tiny, and runtime approaches O(n·m).  "
                "DNAScan's LPS-driven backtrack avoidance keeps time strictly O(n+m)."
            ),
            complexity=COMPLEXITY[Algorithm.DNA_SCAN],
        )

    if m > 10 and sigma > 10 and n > 5_000:
        return HeuristicResult(
            algorithm=Algorithm.GAP_JUMP,
            justification=(
                f"m={m} > 10, σ={sigma} > 10, n={n:,} > 5 000.  "
                "GapJump's 2-gram Bad Character rule yields an average skip of "
                f"≈ m·(1 − 1/σ) ≈ {m * (1 - 1/sigma):.1f} characters per step.  "
                "The Sunday bonus shift inspects the byte past the window, "
                "pushing the best case to O(n/(m+1)) — fastest for natural-language "
                "or source-code text."
            ),
            complexity=COMPLEXITY[Algorithm.GAP_JUMP],
        )

    if m <= 10 and n > 100_000:
        return HeuristicResult(
            algorithm=Algorithm.DUAL_RABIN,
            justification=(
                f"m={m} ≤ 10 with large text n={n:,} > 100 000.  "
                "Short patterns offer GapJump little skip distance "
                f"(avg skip ≈ m/σ ≈ {m/sigma:.2f}).  DualRabin's O(1) "
                "4-layer rolling hash update maintains high throughput; the "
                "hierarchical filter with SSE2 acceleration drops false-positive "
                "probability to ≈ 10⁻²², eliminating verification overhead entirely."
            ),
            complexity=COMPLEXITY[Algorithm.DUAL_RABIN],
        )

    return HeuristicResult(
        algorithm=Algorithm.GAP_JUMP,
        justification=(
            "Default selection.  GapJump achieves the best average-case "
            "performance for general natural-language or mixed text where "
            "no specific degenerate condition was detected.  The 2-gram "
            "bad-character table and Sunday bonus shift provide an extra "
            "stride beyond the classic Boyer-Moore base algorithm."
        ),
        complexity=COMPLEXITY[Algorithm.GAP_JUMP],
    )
