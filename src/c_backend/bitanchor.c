/**
 * BitAnchor – APME Proprietary String Matching Algorithm
 * =======================================================
 *
 * Base algorithm : Shift-Or / Bitap (64-bit NFA bit-parallelism)
 * APME optimisation : memchr dead-state skip
 *
 * How it differs from classic Shift-Or
 * ──────────────────────────────────────
 * Classic Shift-Or processes every text byte unconditionally.  When the
 * NFA state vector drops to zero — meaning no partial match threads are
 * alive — the algorithm still advances one byte at a time waiting for a
 * character that can restart a thread.  BitAnchor detects this dead state
 * after each NFA update and immediately calls memchr to jump to the next
 * occurrence of pattern[0], the only byte that can reactivate the NFA.
 *
 * This is particularly effective when pattern[0] is rare in the text
 * (e.g., a special delimiter in log files) or when the pattern itself is
 * long relative to the alphabet, because the NFA resets frequently and
 * memchr can skip large stretches with SIMD acceleration.
 *
 * Patterns > 64 bytes fall back to flowscan_search (same O(n+m) guarantee).
 *
 * Complexity
 *   Time  O(n) for m ≤ 64 — worst unchanged; average improves with sparsity
 *   Space O(sigma) — 256 64-bit masks
 *
 * When APME prefers BitAnchor
 *   - Short ASCII patterns (m ≤ 64) with a rare leading byte
 *   - High-throughput log scanning where pattern[0] is a sentinel char
 *   - UTF-8 safe: multi-byte sequences are treated as byte runs
 */

#include "algorithms.h"
#include <stdint.h>
#include <string.h>

#define BA_MAX_PATTERN 64

/* FlowScan fallback for long patterns */
extern int flowscan_search(const char *text,    int text_len,
                           const char *pattern, int pat_len,
                           int *positions,      int max_res);

int bitanchor_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    /* Patterns > 64 bytes: fall back to FlowScan */
    if (pat_len > BA_MAX_PATTERN)
        return flowscan_search(text, text_len, pattern, pat_len,
                               positions, max_res);

    /* Build D[c]: bitmask with bit j set iff pattern[j] == c */
    uint64_t D[256];
    memset(D, 0, sizeof D);
    for (int j = 0; j < pat_len; j++)
        D[(unsigned char)pattern[j]] |= (uint64_t)1 << j;

    const uint64_t match_bit = (uint64_t)1 << (pat_len - 1);
    uint64_t state = 0;
    int      count = 0;
    int      i     = 0;

    while (i < text_len) {
        /*
         * APME BitAnchor optimisation — dead-state fast-forward:
         * When the NFA state is zero, no match thread is alive.
         * Jump directly to the next occurrence of pattern[0] instead of
         * advancing one byte at a time, exploiting memchr's SIMD acceleration.
         */
        if (state == 0) {
            const char *hit = (const char *)memchr(text + i,
                                                   (unsigned char)pattern[0],
                                                   (size_t)(text_len - i));
            if (!hit) break;
            i = (int)(hit - text);
        }

        state = ((state << 1) | 1) & D[(unsigned char)text[i]];

        if (state & match_bit) {
            if (count < max_res)
                positions[count] = i - pat_len + 1;
            count++;
        }

        i++;
    }

    return count;
}
