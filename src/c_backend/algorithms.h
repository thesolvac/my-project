/**
 * APME – Adaptive Pattern Matching Engine
 * C Backend: Unified Algorithm Interface
 * ========================================
 *
 * Declares six string-matching algorithms compiled into a single shared
 * library (algorithms.dll / algorithms.so / algorithms.dylib).
 * Python loads this library via ctypes (see src/engine/c_bindings.py).
 *
 * Standard calling convention (all exact algorithms):
 *   int <algo>_search(text, text_len, pattern, pat_len, positions[], max_res)
 *   Returns: match count (negative on allocation failure)
 *
 * Fuzzy search has an extra max_errors parameter:
 *   int fuzzy_search(text, text_len, pattern, pat_len, max_errors, positions[], max_res)
 *
 * Algorithms:
 *   kmp_search   – Knuth-Morris-Pratt       O(n+m) guaranteed
 *   bm_search    – Boyer-Moore (BC+GS)      O(n/m) best case
 *   rk_search    – Rabin-Karp               O(n+m) average
 *   so_search    – Shift-Or / Bitap         O(n) for m ≤ 64
 *   ac_search    – Aho-Corasick automaton   O(n) after O(m·σ) build
 *   fuzzy_search – Wu-Manber k-error Bitap  O(n·k); DP fallback for m > 64
 */

#ifndef ALGORITHMS_H
#define ALGORITHMS_H

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

/** Hard limit on stored match positions per call. */
#define MAX_RESULTS   1000000

/** Extended-ASCII alphabet size (used by Boyer-Moore bad-char table). */
#define ALPHABET_SIZE 256

/* ======================================================================
   KMP – Knuth-Morris-Pratt
   ====================================================================== */

/**
 * Builds the LPS (Longest Proper Prefix which is also Suffix) table.
 *
 * @param pattern  Pattern string (not NUL-terminated; use pat_len)
 * @param pat_len  Length of the pattern
 * @param lps      Caller-allocated output array of size pat_len
 */
void kmp_build_lps(const char *pattern, int pat_len, int *lps);

/**
 * Searches for all occurrences of pattern in text using KMP.
 *
 * Time  O(n + m)  Space  O(m)
 *
 * @param text       Text to search
 * @param text_len   Length of text
 * @param pattern    Pattern to find
 * @param pat_len    Length of pattern
 * @param positions  Caller-allocated array receiving match start indices
 * @param max_res    Capacity of positions[] (use MAX_RESULTS)
 * @return           Match count, or -1 on malloc failure
 */
int kmp_search(const char *text,    int text_len,
               const char *pattern, int pat_len,
               int *positions,      int max_res);

/* ======================================================================
   Boyer-Moore  (Bad Character + Good Suffix)
   ====================================================================== */

/**
 * Builds the Bad Character shift table.
 * bc[c] = last index of character c in pattern (-1 if absent).
 *
 * @param pattern  Pattern string
 * @param pat_len  Length of pattern
 * @param bc       Caller-allocated array of size ALPHABET_SIZE
 */
void bm_build_bad_char(const char *pattern, int pat_len, int bc[ALPHABET_SIZE]);

/**
 * Builds the Good Suffix shift table.
 * gs[j] = how far to shift when mismatch occurs at pattern position j-1.
 *
 * @param pattern  Pattern string
 * @param pat_len  Length of pattern
 * @param gs       Caller-allocated array of size pat_len + 1
 */
void bm_build_good_suffix(const char *pattern, int pat_len, int *gs);

/**
 * Searches for all occurrences of pattern using Boyer-Moore (BC + GS).
 *
 * Time  O(n/m) best  O(n) worst with both tables  Space  O(m + sigma)
 *
 * @param text       Text to search
 * @param text_len   Length of text
 * @param pattern    Pattern to find
 * @param pat_len    Length of pattern
 * @param positions  Caller-allocated array receiving match start indices
 * @param max_res    Capacity of positions[]
 * @return           Match count, or -1 on malloc failure
 */
int bm_search(const char *text,    int text_len,
              const char *pattern, int pat_len,
              int *positions,      int max_res);

/* ======================================================================
   Rabin-Karp  (Rolling Polynomial Hash)
   ====================================================================== */

/**
 * Searches for all occurrences of pattern using Rabin-Karp rolling hash.
 *
 * Time  O(n+m) average  O(n*m) worst (hash collisions)  Space  O(1)
 *
 * @param text       Text to search
 * @param text_len   Length of text
 * @param pattern    Pattern to find
 * @param pat_len    Length of pattern
 * @param positions  Caller-allocated array receiving match start indices
 * @param max_res    Capacity of positions[]
 * @return           Match count
 */
int rk_search(const char *text,    int text_len,
              const char *pattern, int pat_len,
              int *positions,      int max_res);

/* ======================================================================
   Shift-Or / Bitap  (64-bit NFA bit-parallelism)
   ====================================================================== */

/**
 * Exact search using Shift-Or bit-parallel NFA.
 * Patterns > 64 bytes automatically fall back to kmp_search.
 *
 * Time  O(n · ⌈m/64⌉)  Space  O(σ)
 *
 * @param text       Text to search
 * @param text_len   Length of text
 * @param pattern    Pattern to find
 * @param pat_len    Length of pattern
 * @param positions  Caller-allocated array receiving match start indices
 * @param max_res    Capacity of positions[]
 * @return           Match count, or -1 on malloc failure (fallback path)
 */
int so_search(const char *text,    int text_len,
              const char *pattern, int pat_len,
              int *positions,      int max_res);

/* ======================================================================
   Aho-Corasick  (trie + BFS failure links → complete DFA)
   ====================================================================== */

/**
 * Exact search using an Aho-Corasick DFA built for a single pattern.
 * Demonstrates the automaton construction; for multi-pattern use the
 * Python-level search_aho_corasick() helper.
 *
 * Time  O(n + m · σ)  Space  O((m+1) · σ)
 *
 * @param text       Text to search
 * @param text_len   Length of text
 * @param pattern    Pattern to find
 * @param pat_len    Length of pattern
 * @param positions  Caller-allocated array receiving match start indices
 * @param max_res    Capacity of positions[]
 * @return           Match count, or -1 on malloc failure
 */
int ac_search(const char *text,    int text_len,
              const char *pattern, int pat_len,
              int *positions,      int max_res);

/* ======================================================================
   Fuzzy / Approximate  (Wu-Manber k-error Bitap + DP fallback)
   ====================================================================== */

/**
 * Approximate search allowing up to max_errors edit operations.
 * Uses Wu-Manber Bitap for m ≤ 64; Levenshtein DP for m > 64.
 *
 * Time  O(n·k) Bitap  O(n·m) DP  Space  O(k+σ) / O(m)
 *
 * NOTE: Unlike exact algorithms, positions[] contains approximate
 * START offsets (Bitap: i-m+1) or END offsets (DP: i).
 *
 * @param text       Text to search
 * @param text_len   Length of text
 * @param pattern    Pattern to find approximately
 * @param pat_len    Length of pattern
 * @param max_errors Maximum Levenshtein edit distance (0–5)
 * @param positions  Caller-allocated array receiving match offsets
 * @param max_res    Capacity of positions[]
 * @return           Match count, or -1 on malloc failure
 */
int fuzzy_search(const char *text,    int text_len,
                 const char *pattern, int pat_len,
                 int         max_errors,
                 int        *positions, int max_res);

#endif /* ALGORITHMS_H */
