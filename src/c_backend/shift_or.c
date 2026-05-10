/**
 * Shift-Or (Bitap) Algorithm — Exact Single-Pattern Search
 * =========================================================
 *
 * Represents the NFA for "pattern occurred" as a single 64-bit integer,
 * one bit per pattern position.  For each text byte t:
 *
 *   state = ((state << 1) | 1) & D[t]
 *
 * where D[c] is a pre-built bitmask with bit j set iff pattern[j] == c.
 * Bit j of state being set means "pattern[0..j] matches the text ending
 * at the current position."  A full match is detected when bit (m-1) is set.
 *
 * Bit-level parallelism allows a single CPU instruction to advance all m
 * NFA states at once, giving an O(n) inner loop (for m ≤ 64).
 *
 * Pattern length limit
 *   64 bytes (one 64-bit word).  Patterns longer than 64 bytes are
 *   automatically redirected to KMP, which has the same O(n+m) guarantee.
 *
 * Complexity
 *   Time  O(n · ⌈m/64⌉) — O(n) for m ≤ 64
 *   Space O(σ) — 256 64-bit masks
 *
 * When APME prefers Shift-Or
 *   - Short ASCII patterns (m ≤ 64) in varied text
 *   - When branch-misprediction cost of per-character comparison dominates
 *   - UTF-8 safe: multi-byte sequences are treated as byte runs
 *
 * Reference: Wu & Manber, "Fast Text Searching Allowing Errors",
 *            CACM 35(10), 1992.
 */

#include "algorithms.h"
#include <stdint.h>
#include <string.h>

#define SO_MAX_PATTERN 64   /* max pattern bytes for a single 64-bit word */

/* KMP fallback for long patterns */
extern int kmp_search(const char *text,    int text_len,
                      const char *pattern, int pat_len,
                      int *positions,      int max_res);

int so_search(const char *text,    int text_len,
              const char *pattern, int pat_len,
              int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    /* Patterns > 64 bytes: fall back to KMP */
    if (pat_len > SO_MAX_PATTERN)
        return kmp_search(text, text_len, pattern, pat_len, positions, max_res);

    /* Build D[c]: bitmask with bit j set iff pattern[j] == c */
    uint64_t D[256];
    memset(D, 0, sizeof D);
    for (int j = 0; j < pat_len; j++)
        D[(unsigned char)pattern[j]] |= (uint64_t)1 << j;

    const uint64_t match_bit = (uint64_t)1 << (pat_len - 1);
    uint64_t state  = 0;
    int      count  = 0;

    for (int i = 0; i < text_len; i++) {
        state = ((state << 1) | 1) & D[(unsigned char)text[i]];
        if (state & match_bit) {
            if (count < max_res)
                positions[count] = i - pat_len + 1;
            count++;
        }
    }
    return count;
}
