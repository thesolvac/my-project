/**
 * TierMatch – APME Proprietary String Matching Algorithm
 * =======================================================
 *
 * Base algorithm : Wu-Manber k-error Bitap (64-bit NFA bit-parallelism)
 * APME optimisation : best-tier deduplication
 *
 * How it differs from classic Wu-Manber Bitap
 * ─────────────────────────────────────────────
 * Classic Wu-Manber reports a match whenever R[k] has the accept bit set,
 * regardless of whether a lower-error match also ends at that same position.
 * This means the same text position can be emitted multiple times — once for
 * each error tier 0..k that fires simultaneously — cluttering results with
 * redundant near-duplicate entries.
 *
 * TierMatch adds a best-tier deduplication pass after each NFA step:
 *   1. Scan d = 0, 1, …, k in ascending order.
 *   2. If R[d] has the accept bit set, record the match at tier d (exact or
 *      lowest-error) and clear the accept bit in ALL higher tiers (d+1..k) at
 *      that same position.  This suppresses every redundant higher-tier report
 *      before it can be emitted.
 *   3. At most one match is recorded per text position, at the best (lowest)
 *      error count.
 *
 * The deduplication adds one small inner scan (≤ k iterations) per text byte
 * that fires an accept — negligible overhead for typical k ≤ 5.
 *
 * FALLBACK — Levenshtein DP  (patterns > 64 bytes)
 * ──────────────────────────────────────────────────
 * The DP path is already position-unique by construction (one dp[m] cell per
 * text position), so no structural change is needed.  Renamed for consistency.
 *
 * Complexity
 *   Bitap path  O(n · k) time, O(k + σ) space  — unchanged
 *   DP path     O(n · m) time, O(m) space       — unchanged
 *
 * When APME prefers TierMatch
 *   - Any fuzzy search with k ≥ 2 where duplicate-tier results are undesirable
 *   - Ranked / scored output pipelines that expect one result per position
 *   - High-k searches over short patterns where tier collision is frequent
 *
 * Reference: Wu & Manber, "Fast Text Searching Allowing Errors",
 *            CACM 35(10), 1992.
 */

#include "algorithms.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define TM_BITAP_MAX   64   /* max pattern length for the 64-bit Bitap path */
#define TM_MAX_ERRORS   5   /* maximum supported error budget                */


/* ── Wu-Manber k-error Bitap with best-tier deduplication ──────────────────── */

static int bitap_tiermatch(const char *text,    int text_len,
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
    uint64_t R[TM_MAX_ERRORS + 1];
    uint64_t old_R[TM_MAX_ERRORS + 1];
    memset(R, 0, sizeof(uint64_t) * (size_t)(max_err + 1));

    int count = 0;

    for (int i = 0; i < text_len; i++) {
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

        /*
         * APME TierMatch optimisation — best-tier deduplication:
         * Scan d = 0..max_err in ascending order.  The first tier whose
         * accept bit fires is the lowest-error (best) match at this position.
         * Clear the accept bit in all higher tiers so they cannot emit a
         * duplicate match for the same position.
         */
        for (int d = 0; d <= max_err; d++) {
            if (R[d] & match_bit) {
                /* Record once at the best tier */
                int pos = i - pat_len + 1;
                if (pos < 0) pos = 0;
                if (count < max_res)
                    positions[count] = pos;
                count++;

                /* Suppress redundant higher-tier accepts at this position */
                for (int dd = d + 1; dd <= max_err; dd++)
                    R[dd] &= ~match_bit;

                break; /* only one record per position */
            }
        }
    }
    return count;
}


/* ── Levenshtein DP fallback (patterns > 64 bytes) ────────────────────────── */

static int dp_tiermatch(const char *text,    int text_len,
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
        dp[0] = 0;  /* free to start a new match at this position */

        for (int j = 1; j <= pat_len; j++) {
            int cost = (text[i] == pattern[j - 1]) ? 0 : 1;
            int sub  = prev[j - 1] + cost;
            int del  = prev[j]     + 1;
            int ins  = dp[j - 1]   + 1;
            dp[j] = sub < del ? sub : del;
            if (ins < dp[j]) dp[j] = ins;
        }

        if (dp[pat_len] <= max_err) {
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

int tiermatch_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int         max_errors,
                     int        *positions, int max_res) {
    if (pat_len == 0 || text_len == 0) return 0;
    if (max_errors < 0) max_errors = 0;
    if (max_errors > TM_MAX_ERRORS) max_errors = TM_MAX_ERRORS;

    if (pat_len <= TM_BITAP_MAX)
        return bitap_tiermatch(text, text_len, pattern, pat_len,
                               max_errors, positions, max_res);
    else
        return dp_tiermatch(text, text_len, pattern, pat_len,
                            max_errors, positions, max_res);
}
