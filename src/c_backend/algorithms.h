/**
 * APME – Adaptive Pattern Matching Engine
 * C Backend: Proprietary Algorithm Interface
 * ===========================================
 *
 * Six APME-proprietary string-matching algorithms compiled into a single
 * shared library (algorithms.dll / .so / .dylib).
 * Python loads this library via ctypes (see src/engine/c_bindings.py).
 *
 * Standard calling convention (all exact algorithms):
 *   int <algo>_search(text, text_len, pattern, pat_len, positions[], max_res)
 *   Returns: match count (negative on allocation failure)
 *
 * TierMatch has an extra max_errors parameter:
 *   int tiermatch_search(text, text_len, pattern, pat_len, max_errors, positions[], max_res)
 *
 * Algorithms (proprietary APME variants):
 *   flowscan_search    – FlowScan    (KMP + memchr first-char anchor)   O(n+m)
 *   skipstride_search  – SkipStride  (BM + Sunday bonus shift)          O(n/(m+1)) best
 *   twinhash_search    – TwinHash    (Rabin-Karp dual rolling hash)      O(n+m) avg
 *   bitanchor_search   – BitAnchor   (Shift-Or + state-zero memchr skip) O(n) / m≤64
 *   webscan_search     – WebScan     (Aho-Corasick + presence-bitmap bypass) O(n)
 *   tiermatch_search   – TierMatch   (Wu-Manber Bitap + best-tier dedup) O(n·k)
 */

#ifndef ALGORITHMS_H
#define ALGORITHMS_H

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

/** Hard limit on stored match positions per call. */
#define MAX_RESULTS   1000000

/** Extended-ASCII alphabet size. */
#define ALPHABET_SIZE 256

/* ======================================================================
   FlowScan  (APME proprietary — KMP with memchr first-character anchor)
   ====================================================================== */

/**
 * Builds the LPS (Longest Proper Prefix which is also Suffix) table.
 * Used internally by flowscan_search.
 */
void flowscan_build_lps(const char *pattern, int pat_len, int *lps);

/**
 * FlowScan: KMP augmented with a memchr-based first-character anchor.
 *
 * When the pattern pointer resets to 0 (no partial match), FlowScan
 * uses memchr to jump directly to the next occurrence of pattern[0]
 * instead of advancing one byte at a time.  This eliminates redundant
 * comparisons on character classes absent from the pattern.
 *
 * Time  O(n + m)  Space  O(m)
 * Practical improvement: up to 3-4× faster than classic KMP on sparse text.
 */
int flowscan_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res);

/* ======================================================================
   SkipStride  (APME proprietary — Boyer-Moore + Sunday bonus shift)
   ====================================================================== */

void skipstride_build_bad_char(const char *pattern, int pat_len, int bc[ALPHABET_SIZE]);
void skipstride_build_good_suffix(const char *pattern, int pat_len, int *gs);

/**
 * SkipStride: Boyer-Moore with an additional Sunday-shift heuristic.
 *
 * After computing the standard BC and GS shifts, SkipStride also inspects
 * the character immediately beyond the current window (text[s + pat_len]).
 * If that character is absent from the pattern, the full window can be
 * skipped in one stride.  The final shift is max(BC, GS, Sunday).
 *
 * Time  O(n/(m+1)) best  O(n) worst  Space  O(m + sigma)
 */
int skipstride_search(const char *text,    int text_len,
                      const char *pattern, int pat_len,
                      int *positions,      int max_res);

/* ======================================================================
   TwinHash  (APME proprietary — Rabin-Karp with dual rolling hashes)
   ====================================================================== */

/**
 * TwinHash: Rabin-Karp with two independent rolling hashes.
 *
 * Maintains two parallel polynomial hashes (different base/mod pairs).
 * Character-by-character verification is only triggered when BOTH hashes
 * agree, reducing the false-positive rate from ~1/MOD to ~1/(MOD1·MOD2)
 * — effectively zero for practical text lengths.
 *
 * Time  O(n + m) avg  O(n·m) worst  Space  O(1)
 */
int twinhash_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res);

/* ======================================================================
   BitAnchor  (APME proprietary — Shift-Or with state-zero memchr skip)
   ====================================================================== */

/**
 * BitAnchor: Shift-Or bit-parallel NFA with dead-state fast-forward.
 *
 * When the NFA state vector drops to zero (no active match threads),
 * BitAnchor uses memchr to jump directly to the next occurrence of
 * pattern[0] rather than spinning through non-matching bytes one at a time.
 * Patterns > 64 bytes fall back to flowscan_search.
 *
 * Time  O(n) for m ≤ 64  Space  O(sigma)
 * Practical speedup: significant for patterns with a rare leading byte.
 */
int bitanchor_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int *positions,      int max_res);

/* ======================================================================
   WebScan  (APME proprietary — Aho-Corasick + presence-bitmap bypass)
   ====================================================================== */

/**
 * WebScan: Aho-Corasick DFA with a 256-bit character presence bypass.
 *
 * Before each DFA transition, WebScan checks a precomputed 256-bit bitmap
 * of all characters in the pattern.  Bytes not in the pattern immediately
 * reset the automaton to the root state without a DFA table lookup.
 * This is particularly effective for keyword searches in natural-language
 * text where most bytes are not part of any pattern.
 *
 * Time  O(n + m·sigma)  Space  O((m+1)·sigma)
 */
int webscan_search(const char *text,    int text_len,
                   const char *pattern, int pat_len,
                   int *positions,      int max_res);

/* ======================================================================
   TierMatch  (APME proprietary — Wu-Manber Bitap with best-tier dedup)
   ====================================================================== */

/**
 * TierMatch: k-error Bitap with best-tier match deduplication.
 *
 * Extends Wu-Manber fuzzy search with a post-update sweep that reports
 * each match position at the LOWEST error tier (d) where a match is found.
 * Higher-tier accept bits at that position are cleared immediately,
 * preventing the same alignment from being reported multiple times at
 * different error levels.  Uses Levenshtein DP for patterns > 64 bytes.
 *
 * Time  O(n·k) Bitap  O(n·m) DP  Space  O(k + sigma) / O(m)
 */
int tiermatch_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int         max_errors,
                     int        *positions, int max_res);

#endif /* ALGORITHMS_H */
