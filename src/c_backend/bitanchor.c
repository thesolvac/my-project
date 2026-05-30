/* ===========================================================================
 * bitanchor.c  —  BitMatch exact string matching
 * ---------------------------------------------------------------------------
 * Project-book design (SWOT 8.4, data structures §15.3): two bit-parallel
 * NFAs running outward from an internal anchor, replacing the single
 * left-to-right Shift-And automaton.
 *
 *   Anchor choice: the pattern byte that is *rarest* in a sample of the text
 *   (reusing DNAScan's frequency idea, single-byte form). A rare anchor
 *   minimises the number of memchr hits and therefore verifications. The
 *   anchor index a lies in [0, m-1]; it degenerates gracefully to a==0 (pure
 *   forward scan) or a==m-1 (pure backward scan).
 *
 *   Two D (Shift-And) tables are built:
 *     - forward over the suffix  pattern[a .. m-1]            (length Ls = m-a)
 *     - backward over the reversed prefix pattern[a-1 .. 0]   (length Lp = a)
 *   memchr locates the next anchor byte; the forward NFA verifies the suffix
 *   left-to-right and the backward NFA verifies the prefix right-to-left, each
 *   aborting the instant its state goes dead (== 0). On a dead state the scan
 *   memchr-jumps to the next anchor occurrence.
 *
 * The m<=64 ASCII limit and the flowscan_search fallback beyond it are kept
 * (already book-aligned). Signature is unchanged.
 * =========================================================================== */
#include "algorithms.h"
#include <stdint.h>
#include <string.h>

#define BA_MAX_PATTERN 64

extern int flowscan_search(const char *text,    int text_len,
                           const char *pattern, int pat_len,
                           int *positions,      int max_res);

/* Index of the pattern byte rarest in the text sample → fewest memchr hits. */
static int bitanchor_select_anchor(const unsigned char *pattern, int m,
                                   const unsigned char *sample, int sample_len) {
    long freq[256];
    for (int i = 0; i < 256; i++) freq[i] = 0;
    for (int i = 0; i < sample_len; i++) freq[sample[i]]++;

    int  best     = 0;
    long best_cnt = -1;
    for (int k = 0; k < m; k++) {
        long c = freq[pattern[k]];
        if (best_cnt < 0 || c < best_cnt) {
            best_cnt = c;
            best     = k;
            if (best_cnt == 0) break;
        }
    }
    return best;
}

int bitanchor_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    if (pat_len > BA_MAX_PATTERN)
        return flowscan_search(text, text_len, pattern, pat_len,
                               positions, max_res);

    const unsigned char *T = (const unsigned char *)text;
    const unsigned char *P = (const unsigned char *)pattern;

    int sample_len = text_len < 8192 ? text_len : 8192;
    int a  = bitanchor_select_anchor(P, pat_len, T, sample_len);
    int Ls = pat_len - a;          /* suffix length, >= 1 */

    /* forward Shift-And table over the suffix pattern[a .. m-1] */
    uint64_t D_fwd[256];
    memset(D_fwd, 0, sizeof D_fwd);
    for (int j = 0; j < Ls; j++)
        D_fwd[P[a + j]] |= (uint64_t)1 << j;
    const uint64_t fwd_accept = (uint64_t)1 << (Ls - 1);

    /* backward Shift-And table over the reversed prefix pattern[a-1 .. 0] */
    uint64_t D_bwd[256];
    memset(D_bwd, 0, sizeof D_bwd);
    for (int j = 0; j < a; j++)
        D_bwd[P[a - 1 - j]] |= (uint64_t)1 << j;
    const uint64_t bwd_accept = a ? ((uint64_t)1 << (a - 1)) : 0;

    unsigned char anchor = P[a];
    int count = 0;

    /* anchor at text index t ⇒ match start s = t - a; need s >= 0 and the
     * suffix to fit: t in [a, text_len - Ls]. */
    int t_max = text_len - Ls;
    int t = a;

    while (t <= t_max) {
        const unsigned char *hit =
            (const unsigned char *)memchr(T + t, anchor, (size_t)(t_max - t + 1));
        if (!hit) break;
        t = (int)(hit - T);

        /* forward NFA: verify the suffix, abort on a dead state */
        uint64_t Rf = 0;
        int ok = 1;
        for (int j = 0; j < Ls; j++) {
            Rf = ((Rf << 1) | 1) & D_fwd[T[t + j]];
            if (Rf == 0) { ok = 0; break; }
        }
        if (ok && (Rf & fwd_accept)) {
            int matched = 1;
            if (a) {
                /* backward NFA: verify the prefix right-to-left */
                uint64_t Rb = 0;
                for (int j = 0; j < a; j++) {
                    Rb = ((Rb << 1) | 1) & D_bwd[T[t - 1 - j]];
                    if (Rb == 0) { matched = 0; break; }
                }
                if (matched && !(Rb & bwd_accept)) matched = 0;
            }
            if (matched && count < max_res)
                positions[count++] = t - a;
        }
        t++;                       /* allow overlapping matches */
    }

    return count;
}
