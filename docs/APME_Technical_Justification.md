# APME – Technical Justification of the Adaptive Heuristic

## Overview

The Adaptive Pattern Matching Engine (APME) does not use a single algorithm.
Instead, it analyses measurable properties of the input at runtime and
dispatches to the algorithm most likely to minimise execution time for that
specific case. This document explains **why** each rule exists, grounded in
the published complexity analysis of the three algorithms.

---

## The Three Algorithms

| Algorithm | Preprocessing | Search (Best) | Search (Worst) | Space |
|-----------|-------------|--------------|----------------|-------|
| KMP | O(m) | O(n + m) | O(n + m) | O(m) |
| Boyer-Moore | O(m + σ) | **O(n/m)** | O(n) with GS | O(m + σ) |
| Rabin-Karp | O(m) | O(n + m) | O(n · m)* | O(1) |

*worst case only when hash collisions occur on every window (extremely rare with a large prime MOD)

**Notation:** n = text length, m = pattern length, σ = alphabet size (distinct characters)

---

## Decision Rules and Their Justification

### Rule 1 — Very Short Pattern (m ≤ 2) → KMP

**Why:** Both Boyer-Moore and Rabin-Karp incur preprocessing overhead:
- BM builds a bad-character table of size σ and a good-suffix array of size m + 1
- RK computes an initial window hash in O(m)

For m ≤ 2, neither preprocessing step can be amortised across the search.
KMP's single O(m) LPS computation is minimal and its O(n + m) search is
optimal. The average BM skip distance for short patterns is `m · (1 − 1/σ)`,
which for m = 2 and σ = 26 is only ≈ 1.92 — negligible over the naive step.

---

### Rule 2 — Multiple Patterns (num_patterns > 1) → Rabin-Karp

**Why:** KMP and BM require one full text pass per pattern.
Rabin-Karp can hash *all* patterns in O(k · m) and then scan the text once
in O(n), comparing the rolling window hash against all k pattern hashes
simultaneously. Total cost: **O(n + k · m)** versus O(k · (n + m)) for KMP/BM.
For k > 1, Rabin-Karp's amortisation advantage grows linearly.

---

### Rule 3 — Small Alphabet (σ ≤ 4) → KMP

**Why:** Boyer-Moore's Bad Character heuristic relies on mismatch characters
appearing rarely in the pattern. With only 4 distinct characters (e.g. DNA:
{A, C, G, T} or binary: {0, 1}), the probability that the mismatched text
character appears in the pattern is high (≈ m/σ ≈ m/4), so the BC skip is
small. In degenerate cases (e.g. pattern `AAAB` in text `AAAA...AAAB`) BM
degrades to **O(n · m)**. KMP's LPS-based skip is independent of alphabet
size and guarantees O(n + m) in all cases.

---

### Rule 4 — Highly Repetitive Text (repetitiveness > 70%) → KMP

**Why:** Repetitive text is Boyer-Moore's Achilles' heel. Consider searching
for `AAAB` in `AAAAAA...AAA`: nearly every position is a partial match, so
the Good Suffix shift is almost always 1 — the algorithm barely skips at all,
and worst-case O(n · m) is approached. KMP's failure function handles repeated
characters gracefully by using the LPS to jump within the pattern rather than
restarting from scratch.

**Detection:** The repetitiveness ratio is `max_frequency(c) / len(sample)`.
A value above 70 % reliably identifies monotonic or near-monotonic inputs.

---

### Rule 5 — Long Pattern + Large Alphabet + Substantial Text → Boyer-Moore

**Conditions:** m > 10, σ > 10, n > 5 000

**Why:** This is Boyer-Moore's sweet spot.
- Large alphabet → mismatches are common → BC shift distance is large
- Long pattern → even a shift of `m/2` skips many characters
- Expected BC shift = `m · (1 − 1/σ)`. For m = 20, σ = 52 (English + digits):
  skip ≈ 19.6 characters per step → **sub-linear O(n/m)**

This is why BM is used internally by UNIX `grep`, `agrep`, and most text editors.

---

### Rule 6 — Short Pattern in Large Text → Rabin-Karp

**Conditions:** m ≤ 10, n > 100 000

**Why:** For short patterns, BM's average skip is `m · (1 − 1/σ)`. With m = 5
and σ = 26, skip ≈ 4.8 — barely more than 1 step ahead. Rabin-Karp's
rolling hash update is O(1) per position:

```
hash_new = (BASE * (hash_old − text[i] * h) + text[i+m]) % MOD
```

This keeps throughput high with no per-step branching overhead, outperforming
BM's table lookups at small m.

---

### Default — Boyer-Moore

When no specific rule fires, Boyer-Moore is chosen as the general-purpose
default. Its sub-linear average-case performance makes it the best choice
for the most common input type: natural language or source-code text with
moderate-length patterns and a large alphabet.

---

## Why Not Machine Learning?

The APME could theoretically use a classifier to predict the best algorithm.
This was **deliberately avoided** for three reasons:

1. **Explainability:** A rule-based system can justify its choice in plain
   language (visible in the UI). A neural network cannot.
2. **No training data required:** The rules are derived from mathematical
   complexity analysis, not empirical measurements — they work on the first run.
3. **Zero latency overhead:** ML inference adds tens to hundreds of milliseconds.
   The entire heuristic runs in microseconds (pure Python string sampling).

The formal bounds described above provide stronger guarantees than any
trained model could offer.

---

## References

1. Knuth, Morris & Pratt, *Fast Pattern Matching in Strings*, SIAM J. Comput., 1977
2. Boyer & Moore, *A Fast String Searching Algorithm*, CACM, 1977
3. Karp & Rabin, *Efficient Randomized Pattern-Matching Algorithms*, IBM J., 1987
4. Crochemore & Rytter, *Text Algorithms*, Oxford University Press, 1994
5. Cormen et al., *Introduction to Algorithms (CLRS)*, MIT Press, Chapter 32
