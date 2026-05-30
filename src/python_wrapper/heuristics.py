from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
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
    # full per-algorithm score vector (algorithm value → 0..10); empty for
    # manual selections. Added by the §21.3.3 score-based selector.
    scores:        dict[str, int] = field(default_factory=dict)

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

# ─────────────────────────────────────────────────────────────────────────────
# Score-based selection (project book §§9.5, 21.3.3)
#
# The legacy if-else cascade is replaced by a feature-vector + scoring model.
# Each algorithm carries ten boolean predicates over the extracted features;
# an algorithm's score is the number of predicates it satisfies (0..10). Among
# the *eligible* algorithms the highest score wins, ties broken by the legacy
# §9.5 cascade precedence. This keeps the book's per-algorithm reasoning while
# producing a smooth, inspectable score instead of brittle first-match rules.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Features:
    m:                int     # pattern length
    n:                int     # text length
    k:                int     # max edit errors (0 ⇒ exact search)
    num_patterns:     int
    sigma:            int     # σ  — alphabet cardinality of the text sample
    repetition:       float   # R  — fraction of the most common sample char
    sigma_bigram:     int     # σ_pair — distinct adjacent byte-pairs in sample
    h_pattern:        float   # H  — Shannon entropy (bits) of the pattern
    is_ascii_pattern: bool
    is_ascii_text:    bool

def _extract_features(
    text: str, pattern: str, num_patterns: int, max_errors: int
) -> _Features:
    sample = text[:_SAMPLE_CAP]
    if sample:
        counts   = Counter(sample)
        sigma    = len(counts)
        rep      = max(counts.values()) / len(sample)
        sigma_bg = len({sample[i:i + 2] for i in range(len(sample) - 1)})
        ascii_t  = sample.isascii()
    else:
        sigma, rep, sigma_bg, ascii_t = 0, 0.0, 0, True

    if pattern:
        plen  = len(pattern)
        h_pat = -sum((c / plen) * math.log2(c / plen)
                     for c in Counter(pattern).values())
    else:
        h_pat = 0.0

    return _Features(
        m=len(pattern), n=len(text), k=max(0, max_errors),
        num_patterns=num_patterns, sigma=sigma, repetition=rep,
        sigma_bigram=sigma_bg, h_pattern=h_pat,
        is_ascii_pattern=pattern.isascii(), is_ascii_text=ascii_t,
    )

# Ten predicates per algorithm. Each entry is (label, predicate); the count of
# satisfied predicates is the score, and the labels feed the justification.
_ALGORITHM_RULES: dict[Algorithm, list[tuple[str, object]]] = {
    # DNAScan — O(n+m) guarantee; shines on tiny patterns, tiny/repetitive
    # alphabets, and rare-bigram-anchor opportunities.
    Algorithm.DNA_SCAN: [
        ("m≤2",                 lambda f: f.m <= 2),
        ("m≤4",                 lambda f: f.m <= 4),
        ("σ≤4",                 lambda f: f.sigma <= 4),
        ("σ≤8",                 lambda f: f.sigma <= 8),
        ("R>0.70",              lambda f: f.repetition > 0.70),
        ("R>0.50",              lambda f: f.repetition > 0.50),
        ("σ_pair≤16",           lambda f: f.sigma_bigram <= 16),
        ("H_pattern<1.5",       lambda f: f.h_pattern < 1.5),
        ("large & small-σ",     lambda f: f.n > 50_000 and f.sigma <= 4),
        ("ascii text & σ≤6",    lambda f: f.is_ascii_text and f.sigma <= 6),
    ],
    # GapJump — Boyer-Moore + 2-gram bad-character; best on medium/long
    # patterns over large, diverse alphabets (natural language, source code).
    Algorithm.GAP_JUMP: [
        ("m>10",                lambda f: f.m > 10),
        ("m>4",                 lambda f: f.m > 4),
        ("σ>10",                lambda f: f.sigma > 10),
        ("σ>4",                 lambda f: f.sigma > 4),
        ("n>5000",              lambda f: f.n > 5_000),
        ("n>1000",              lambda f: f.n > 1_000),
        ("σ_pair>64",           lambda f: f.sigma_bigram > 64),
        ("H_pattern>2.0",       lambda f: f.h_pattern > 2.0),
        ("low repetition",      lambda f: f.repetition <= 0.50),
        ("ascii text & σ>10",   lambda f: f.is_ascii_text and f.sigma > 10),
    ],
    # DualRabin — 4-layer rolling hash; wins on short-to-medium patterns over
    # very large text where Boyer-Moore skips shrink.
    Algorithm.DUAL_RABIN: [
        ("m≤10",                lambda f: f.m <= 10),
        ("m≤16",                lambda f: f.m <= 16),
        ("n>100000",            lambda f: f.n > 100_000),
        ("n>20000",             lambda f: f.n > 20_000),
        ("σ>8",                 lambda f: f.sigma > 8),
        ("H_pattern>1.5",       lambda f: f.h_pattern > 1.5),
        ("m≥3",                 lambda f: f.m >= 3),
        ("n>5000 & m≤12",       lambda f: f.n > 5_000 and f.m <= 12),
        ("σ_pair>32",           lambda f: f.sigma_bigram > 32),
        ("ascii text & n>50000", lambda f: f.is_ascii_text and f.n > 50_000),
    ],
    # BitMatch — bidirectional bit-parallel NFA; short ASCII exact patterns,
    # O(n) and branchless. (Template per §21.3.3.)
    Algorithm.BIT_MATCH: [
        ("m≤64",                lambda f: f.m <= 64),
        ("ascii pattern",       lambda f: f.is_ascii_pattern),
        ("m≤32",                lambda f: f.m <= 32),
        ("m≤16",                lambda f: f.m <= 16),
        ("m>2",                 lambda f: f.m > 2),
        ("σ>4",                 lambda f: f.sigma > 4),
        ("n>1000",              lambda f: f.n > 1_000),
        ("R<0.70",              lambda f: f.repetition < 0.70),
        ("σ_pair>16",           lambda f: f.sigma_bigram > 16),
        ("H_pattern>1.0",       lambda f: f.h_pattern > 1.0),
    ],
    # SweepRun — Aho-Corasick; only meaningful for multiple patterns, so every
    # predicate is gated on num_patterns>1 (score 0 for a single pattern).
    Algorithm.SWEEP_RUN: [
        ("multi-pattern",       lambda f: f.num_patterns > 1),
        ("patterns>2",          lambda f: f.num_patterns > 2),
        ("patterns>4",          lambda f: f.num_patterns > 4),
        ("patterns>8",          lambda f: f.num_patterns > 8),
        ("multi & n>1000",      lambda f: f.num_patterns > 1 and f.n > 1_000),
        ("multi & n>10000",     lambda f: f.num_patterns > 1 and f.n > 10_000),
        ("multi & n>5000",      lambda f: f.num_patterns > 1 and f.n > 5_000),
        ("multi & ascii text",  lambda f: f.num_patterns > 1 and f.is_ascii_text),
        ("multi & σ≤64",        lambda f: f.num_patterns > 1 and f.sigma <= 64),
        ("multi & m≤32",        lambda f: f.num_patterns > 1 and f.m <= 32),
    ],
    # FuzzySearch — approximate matching; only eligible when k>0, scored on the
    # difficulty of the approximate search.
    Algorithm.FUZZY_SEARCH: [
        ("k>0",                 lambda f: f.k > 0),
        ("k≥2",                 lambda f: f.k >= 2),
        ("k≥3",                 lambda f: f.k >= 3),
        ("m≤64 (bitap)",        lambda f: f.m <= 64),
        ("m>64 (Myers)",        lambda f: f.m > 64),
        ("m≥4",                 lambda f: f.m >= 4),
        ("n>1000",              lambda f: f.n > 1_000),
        ("σ>4",                 lambda f: f.sigma > 4),
        ("ascii pattern",       lambda f: f.is_ascii_pattern),
        ("k≤5 (capped)",        lambda f: 0 < f.k <= 5),
    ],
}

def _is_eligible(algo: Algorithm, f: _Features) -> bool:
    if algo == Algorithm.BIT_MATCH:
        return f.m <= 64 and f.is_ascii_pattern and f.k == 0
    if algo == Algorithm.FUZZY_SEARCH:
        return f.k > 0
    # the remaining four exact matchers only handle k == 0
    return f.k == 0

# Legacy §9.5 cascade precedence (first-match order) used to break score ties.
_TIE_BREAK_ORDER: list[Algorithm] = [
    Algorithm.DNA_SCAN,
    Algorithm.BIT_MATCH,
    Algorithm.SWEEP_RUN,
    Algorithm.GAP_JUMP,
    Algorithm.DUAL_RABIN,
    Algorithm.FUZZY_SEARCH,
]

def _tie_break(tied: list[Algorithm]) -> Algorithm:
    for algo in _TIE_BREAK_ORDER:
        if algo in tied:
            return algo
    return tied[0]

def _score(algo: Algorithm, f: _Features) -> tuple[int, list[str]]:
    passed = [label for label, pred in _ALGORITHM_RULES[algo] if pred(f)]
    return len(passed), passed

def select_algorithm(
    text:         str,
    pattern:      str,
    num_patterns: int = 1,
    manual:       str | None = None,
    max_errors:   int = 0,
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

    f = _extract_features(text, pattern, num_patterns, max_errors)

    scores:       dict[str, int]            = {}
    passed_rules: dict[Algorithm, list[str]] = {}
    eligible:     list[Algorithm]           = []
    for algo in Algorithm:
        sc, passed         = _score(algo, f)
        scores[algo.value] = sc
        passed_rules[algo] = passed
        if _is_eligible(algo, f):
            eligible.append(algo)

    if not eligible:                       # defensive — should never trigger
        eligible = [Algorithm.GAP_JUMP]

    best   = max(scores[a.value] for a in eligible)
    tied   = [a for a in eligible if scores[a.value] == best]
    winner = tied[0] if len(tied) == 1 else _tie_break(tied)

    tie_note = ""
    if len(tied) > 1:
        names = ", ".join(a.display_name() for a in tied)
        tie_note = (f"  Tie at {best}/10 among [{names}]; resolved to "
                    f"{winner.display_name()} by §9.5 cascade precedence.")

    rules = ", ".join(passed_rules[winner]) or "none"
    justification = (
        f"{winner.display_name()} selected with score {best}/10 "
        f"(σ={f.sigma}, R={f.repetition:.0%}, σ_pair={f.sigma_bigram}, "
        f"H={f.h_pattern:.2f}, m={f.m}, n={f.n:,}, k={f.k}, "
        f"patterns={f.num_patterns}).  Rules passed: [{rules}].{tie_note}"
    )

    return HeuristicResult(
        algorithm=winner,
        justification=justification,
        complexity=COMPLEXITY[winner],
        scores=scores,
    )
