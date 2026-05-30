/* ===========================================================================
 * twinhash.c  —  DualRabin exact string matching
 * ---------------------------------------------------------------------------
 * Project-book design (proof 6.7, SWOT 8.3, §6.4): a four-layer hierarchical
 * filter so that the expensive full comparison runs only for very strong
 * candidates:
 *
 *   Layer 1  byte-sum   : rolling Sigma(bytes) mod 256 — one add/sub per step,
 *                         rejects the vast majority of windows for free.
 *   Layer 2  hash #1    : rolling polynomial hash, base 257  mod 1e9+7.
 *   Layer 3  hash #2    : rolling polynomial hash, base 31   mod 998244353.
 *   Layer 4  SSE2 verify: 16-byte-parallel _mm_cmpeq_epi8 confirmation, with a
 *                         byte-by-byte fallback when SSE2 is unavailable.
 *
 * A window is verified (layer 4) only after surviving the byte-sum and BOTH
 * hashes, dropping the residual false-positive probability to ~10^-22.
 * Signature is unchanged.
 *
 * Book alignment note: base #1 is 257 (was 256 in the legacy code) to match
 * the value documented in the project book; the documentation is canonical.
 * =========================================================================== */
#include "algorithms.h"
#include <stdint.h>

#define TH_BASE1  257LL
#define TH_MOD1   1000000007LL

#define TH_BASE2  31LL
#define TH_MOD2   998244353LL

/* ── Layer 4: final verification ──────────────────────────────────────────── */
#if defined(__SSE2__)
#include <emmintrin.h>
/* 16 bytes per compare; only full aligned-length chunks use SSE so we never
 * read past the candidate window, the tail falls back to a byte loop. */
static inline int twinhash_verify(const unsigned char *t,
                                  const unsigned char *p, int m) {
    int k = 0;
    for (; k + 16 <= m; k += 16) {
        __m128i vt = _mm_loadu_si128((const __m128i *)(t + k));
        __m128i vp = _mm_loadu_si128((const __m128i *)(p + k));
        if (_mm_movemask_epi8(_mm_cmpeq_epi8(vt, vp)) != 0xFFFF) return 0;
    }
    for (; k < m; k++)
        if (t[k] != p[k]) return 0;
    return 1;
}
#else
static inline int twinhash_verify(const unsigned char *t,
                                  const unsigned char *p, int m) {
    for (int k = 0; k < m; k++)
        if (t[k] != p[k]) return 0;
    return 1;
}
#endif

int twinhash_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    const unsigned char *T = (const unsigned char *)text;
    const unsigned char *P = (const unsigned char *)pattern;

    /* high-order multiplier for removing the leading byte during the roll */
    long long h1 = 1, h2 = 1;
    for (int i = 0; i < pat_len - 1; i++) {
        h1 = (h1 * TH_BASE1) % TH_MOD1;
        h2 = (h2 * TH_BASE2) % TH_MOD2;
    }

    long long pat_h1 = 0, pat_h2 = 0;
    long long win_h1 = 0, win_h2 = 0;
    unsigned int pat_sum = 0, win_sum = 0;          /* layer 1 (mod 256) */

    for (int i = 0; i < pat_len; i++) {
        pat_h1 = (TH_BASE1 * pat_h1 + P[i]) % TH_MOD1;
        win_h1 = (TH_BASE1 * win_h1 + T[i]) % TH_MOD1;
        pat_h2 = (TH_BASE2 * pat_h2 + P[i]) % TH_MOD2;
        win_h2 = (TH_BASE2 * win_h2 + T[i]) % TH_MOD2;
        pat_sum += P[i];
        win_sum += T[i];
    }
    pat_sum &= 0xFF;
    win_sum &= 0xFF;

    int count = 0;

    for (int i = 0; i <= text_len - pat_len; i++) {
        /* Layer 1 → Layer 2/3 → Layer 4, short-circuited. */
        if (win_sum == pat_sum &&
            win_h1 == pat_h1 && win_h2 == pat_h2 &&
            twinhash_verify(T + i, P, pat_len)) {
            if (count < max_res)
                positions[count++] = i;
        }

        if (i < text_len - pat_len) {
            win_h1 = (TH_BASE1 *
                      ((win_h1 - T[i] * h1 % TH_MOD1 + TH_MOD1) % TH_MOD1)
                      + T[i + pat_len]) % TH_MOD1;

            win_h2 = (TH_BASE2 *
                      ((win_h2 - T[i] * h2 % TH_MOD2 + TH_MOD2) % TH_MOD2)
                      + T[i + pat_len]) % TH_MOD2;

            win_sum = (win_sum - T[i] + T[i + pat_len]) & 0xFF;
        }
    }

    return count;
}
