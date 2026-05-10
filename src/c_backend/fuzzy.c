/**
 * Approximate (Fuzzy) String Search
 * ====================================
 *
 * Two execution paths depending on pattern length:
 *
 * PRIMARY — Wu-Manber k-error Bitap  (patterns ≤ 64 bytes)
 * ─────────────────────────────────────────────────────────
 * Extends Shift-Or to the k-error case using k+1 bit-vectors R[0..k].
 * R[d] tracks text positions where the pattern matches with ≤ d edit
 * operations (substitutions, insertions, deletions).
 *
 * Recurrence for each text byte t:
 *   save old_R[0..k]
 *   R[0] = ((R[0] << 1) | 1) & D[t]                     exact match
 *   R[d] = ((R[d] << 1) | 1) & D[t]                     substitution/match
 *         | old_R[d-1]                                    delete from text
 *         | (old_R[d-1] << 1)                             insert in pattern
 *         | (R[d-1] << 1)                                 delete from pattern
 *
 * Match: bit (m-1) of R[k] is set → approximate match ending here.
 *
 * Complexity: O(n · k) time, O(k + σ) space.
 *
 * FALLBACK — Levenshtein DP  (patterns > 64 bytes)
 * ─────────────────────────────────────────────────
 * Classical O(n · m) sliding DP.  The dp[] row is initialised to
 * [0, 1, 2, …, m] so the algorithm is free to start anywhere in the
 * text without penalty.  A match is recorded whenever dp[m] ≤ max_errors.
 *
 * Complexity: O(n · m) time, O(m) space.
 *
 * Return value
 *   Positions are approximate START byte offsets (i - m + 1 for the
 *   Bitap path; i for the DP path where i is the last matched text byte).
 *   Total match count is returned; negative means malloc failure.
 *
 * Reference: Wu & Manber, "Fast Text Searching Allowing Errors",
 *            CACM 35(10), 1992.
 */

#include "algorithms.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define FUZZY_BITAP_MAX  64   /* max pattern length for the 64-bit Bitap */
#define FUZZY_MAX_ERRORS  5   /* maximum supported error budget */


/* ── Wu-Manber k-error Bitap ──────────────────────────────────────────────── */

static int bitap_fuzzy(const char *text,    int text_len,
                       const char *pattern, int pat_len,
                       int         max_err,
                       int        *positions, int max_res) {
    /* D[c]: bit j set iff pattern[j] == c */
    uint64_t D[256];
    memset(D, 0, sizeof D);
    for (int j = 0; j < pat_len; j++)
        D[(unsigned char)pattern[j]] |= (uint64_t)1 << j;

    const uint64_t match_bit = (uint64_t)1 << (pat_len - 1);

    /* k+1 state bitvectors */
    uint64_t  R[FUZZY_MAX_ERRORS + 1];
    uint64_t  old_R[FUZZY_MAX_ERRORS + 1];
    memset(R, 0, sizeof(uint64_t) * (size_t)(max_err + 1));

    int count = 0;

    for (int i = 0; i < text_len; i++) {
        /* Save previous state before update */
        memcpy(old_R, R, sizeof(uint64_t) * (size_t)(max_err + 1));

        unsigned char t = (unsigned char)text[i];

        /* Exact layer */
        R[0] = ((R[0] << 1) | 1) & D[t];

        /* Error layers */
        for (int d = 1; d <= max_err; d++) {
            R[d] = ((R[d] << 1) | 1) & D[t]   /* substitution / match */
                 | old_R[d - 1]                /* delete from text     */
                 | (old_R[d - 1] << 1)         /* insert in pattern    */
                 | (R[d - 1] << 1);            /* delete from pattern  */
        }

        if (R[max_err] & match_bit) {
            int pos = i - pat_len + 1;
            if (pos < 0) pos = 0;
            if (count < max_res)
                positions[count] = pos;
            count++;
        }
    }
    return count;
}


/* ── Levenshtein DP fallback (patterns > 64 bytes) ────────────────────────── */

static int dp_fuzzy(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int         max_err,
                    int        *positions, int max_res) {
    int *dp   = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    int *prev = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    if (!dp || !prev) { free(dp); free(prev); return -1; }

    /* Init: free to start anywhere in text (no row-0 penalty) */
    for (int j = 0; j <= pat_len; j++) dp[j] = j;

    int count = 0;

    for (int i = 0; i < text_len; i++) {
        memcpy(prev, dp, (size_t)(pat_len + 1) * sizeof(int));
        dp[0] = 0;  /* always free to start a new match at this position */

        for (int j = 1; j <= pat_len; j++) {
            int cost = (text[i] == pattern[j - 1]) ? 0 : 1;
            int sub  = prev[j - 1] + cost;
            int del  = prev[j]     + 1;
            int ins  = dp[j - 1]   + 1;
            dp[j] = sub < del ? sub : del;
            if (ins < dp[j]) dp[j] = ins;
        }

        if (dp[pat_len] <= max_err) {
            /* Record the end byte of the approximate match */
            if (count < max_res)
                positions[count] = i;
            count++;
        }
    }

    free(dp);
    free(prev);
    return count;
}


/* ── Public entry point ───────────────────────────────────────────────────── */

int fuzzy_search(const char *text,    int text_len,
                 const char *pattern, int pat_len,
                 int         max_errors,
                 int        *positions, int max_res) {
    if (pat_len == 0 || text_len == 0) return 0;
    if (max_errors < 0) max_errors = 0;
    if (max_errors > FUZZY_MAX_ERRORS) max_errors = FUZZY_MAX_ERRORS;

    if (pat_len <= FUZZY_BITAP_MAX)
        return bitap_fuzzy(text, text_len, pattern, pat_len,
                           max_errors, positions, max_res);
    else
        return dp_fuzzy(text, text_len, pattern, pat_len,
                        max_errors, positions, max_res);
}
