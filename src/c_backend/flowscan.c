/* ===========================================================================
 * flowscan.c  —  DNAScan exact string matching
 * ---------------------------------------------------------------------------
 * Project-book design (§21.3.1, proof 6.5): adaptive bigram-anchor scan with
 * bidirectional verification, replacing the classic KMP/LPS scan.
 *
 *   1. Sample the first min(text_len, 8192) bytes of the text and tally byte
 *      frequencies.
 *   2. Choose the pattern bigram (p[a], p[a+1]) with the *minimum* joint
 *      frequency  freq[p[a]] * freq[p[a+1]]  — i.e. the rarest two-byte anchor
 *      in this particular text. A rare anchor maximises memchr skip distance.
 *   3. Scan with memchr on the anchor's first byte, apply a cheap one-byte
 *      filter on the second byte, then verify the rest of the pattern
 *      byte-by-byte in both directions (prefix backwards from the anchor,
 *      suffix forwards) with early exit on the first mismatch.
 *
 * Edge cases: m==1 degenerates to a plain memchr loop on p[0]; m==2 fixes the
 * anchor at a==0. The flowscan_build_lps() helper is retained unchanged so the
 * public header API is preserved (the book keeps the LPS table available).
 * Signature is unchanged: callers (c_bindings.py, bitanchor fallback) are safe.
 * =========================================================================== */
#include "algorithms.h"
#include <stdlib.h>
#include <string.h>

/* Retained for API compatibility (declared in algorithms.h). The bigram-anchor
 * scan below does not use it, but the symbol must remain for the public header. */
void flowscan_build_lps(const char *pattern, int pat_len, int *lps) {
    int len = 0;
    lps[0]  = 0;
    int i   = 1;

    while (i < pat_len) {
        if (pattern[i] == pattern[len]) {
            lps[i] = ++len;
            i++;
        } else if (len != 0) {
            len = lps[len - 1];
        } else {
            lps[i] = 0;
            i++;
        }
    }
}

/* Return the index a in [0, m-2] of the pattern bigram (p[a], p[a+1]) with the
 * minimal joint frequency in the sampled text. Bytes absent from the sample
 * have frequency 0, so a bigram unseen in the text wins immediately (rarest). */
static int dnascan_select_anchor(const unsigned char *pattern, int m,
                                 const unsigned char *sample, int sample_len) {
    long freq[256];
    for (int i = 0; i < 256; i++) freq[i] = 0;
    for (int i = 0; i < sample_len; i++) freq[sample[i]]++;

    int  best_idx  = 0;
    long best_cost = -1;                 /* sentinel: "not set yet" */
    for (int a = 0; a <= m - 2; a++) {
        long cost = freq[pattern[a]] * freq[pattern[a + 1]];
        if (best_cost < 0 || cost < best_cost) {
            best_cost = cost;
            best_idx  = a;
            if (best_cost == 0) break;   /* cannot do better than a rare bigram */
        }
    }
    return best_idx;
}

int flowscan_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    const unsigned char *T = (const unsigned char *)text;
    const unsigned char *P = (const unsigned char *)pattern;
    int count = 0;

    /* m == 1: a bigram anchor is impossible; scan the single byte directly. */
    if (pat_len == 1) {
        int i = 0;
        while (i < text_len) {
            const unsigned char *hit =
                (const unsigned char *)memchr(T + i, P[0], (size_t)(text_len - i));
            if (!hit) break;
            i = (int)(hit - T);
            if (count < max_res) positions[count++] = i;
            i++;
        }
        return count;
    }

    /* Sample the text and pick the rarest pattern bigram as the anchor.
     * m == 2 forces a == 0 (only one possible bigram). */
    int sample_len = text_len < 8192 ? text_len : 8192;
    int a = (pat_len == 2) ? 0
          : dnascan_select_anchor(P, pat_len, T, sample_len);

    unsigned char a0 = P[a];
    unsigned char a1 = P[a + 1];

    /* Valid anchor start t satisfies match-start s = t - a in [0, text_len-m],
     * i.e. t in [a, text_len - pat_len + a]. */
    int t_max = text_len - pat_len + a;
    int t = a;

    while (t <= t_max) {
        const unsigned char *hit =
            (const unsigned char *)memchr(T + t, a0, (size_t)(t_max - t + 1));
        if (!hit) break;
        t = (int)(hit - T);

        if (T[t + 1] == a1) {                 /* cheap second-byte filter */
            int s  = t - a;
            int ok = 1;

            /* prefix: verify backwards from just before the anchor */
            for (int k = a - 1; k >= 0; k--) {
                if (P[k] != T[s + k]) { ok = 0; break; }
            }
            /* suffix: verify forwards from just after the anchor */
            if (ok) {
                for (int k = a + 2; k < pat_len; k++) {
                    if (P[k] != T[s + k]) { ok = 0; break; }
                }
            }
            if (ok && count < max_res) positions[count++] = s;
        }
        t++;                                  /* allow overlapping matches */
    }

    return count;
}
