/* ===========================================================================
 * gapjump.c  —  GapJump exact string matching
 * ---------------------------------------------------------------------------
 * Project-book design (§21.3.2, proof 6.6): Boyer-Moore augmented with a
 * 2-gram bad-character table of 65,536 entries. Alongside the classic
 * single-byte BC1 and Good-Suffix tables, a byte-pair (Sunday-style) rule
 * inspects the two bytes immediately past the window. Because a random byte
 * *pair* is far rarer than a single byte, the bigram shift is typically much
 * larger, raising the average stride. Signature and helper APIs unchanged.
 * =========================================================================== */
#include "algorithms.h"
#include <stdlib.h>
#include <string.h>

#define GJ_BC2_SIZE (256 * 256)   /* one slot per ordered byte pair */

void gapjump_build_bad_char(const char *pattern, int pat_len,
                               int bc[ALPHABET_SIZE]) {
    for (int i = 0; i < ALPHABET_SIZE; i++) bc[i] = -1;
    for (int i = 0; i < pat_len;      i++) bc[(unsigned char)pattern[i]] = i;
}

/* 2-gram bad-character table: bc2[p[i]*256 + p[i+1]] = i, rightmost wins.
 * Pairs absent from the pattern keep their -1 sentinel. */
static void gapjump_build_bc2(const unsigned char *pattern, int m, int *bc2) {
    memset(bc2, 0xFF, (size_t)GJ_BC2_SIZE * sizeof(int));   /* all -1 */
    for (int i = 0; i <= m - 2; i++)
        bc2[pattern[i] * 256 + pattern[i + 1]] = i;
}

void gapjump_build_good_suffix(const char *pattern, int pat_len, int *gs) {
    int *border = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    if (!border) return;

    for (int i = 0; i <= pat_len; i++) gs[i] = 0;

    int i = pat_len;
    int j = pat_len + 1;
    border[i] = j;

    while (i > 0) {
        while (j <= pat_len && pattern[i - 1] != pattern[j - 1]) {
            if (gs[j] == 0) gs[j] = j - i;
            j = border[j];
        }
        border[--i] = --j;
    }

    j = border[0];
    for (i = 0; i <= pat_len; i++) {
        if (gs[i] == 0) gs[i] = j;
        if (i == j)     j = border[j];
    }

    free(border);
}

int gapjump_search(const char *text,    int text_len,
                      const char *pattern, int pat_len,
                      int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    int bc[ALPHABET_SIZE];
    gapjump_build_bad_char(pattern, pat_len, bc);

    int *gs = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    if (!gs) return -1;
    gapjump_build_good_suffix(pattern, pat_len, gs);

    int *bc2 = (int *)malloc((size_t)GJ_BC2_SIZE * sizeof(int));   /* 256 KB */
    if (!bc2) { free(gs); return -1; }
    gapjump_build_bc2((const unsigned char *)pattern, pat_len, bc2);

    int count = 0;
    int s = 0;

    while (s <= text_len - pat_len) {
        int j = pat_len - 1;

        while (j >= 0 && pattern[j] == text[s + j])
            j--;

        if (j < 0) {
            if (count < max_res)
                positions[count++] = s;
            s += gs[0];
        } else {
            int bc_shift = j - bc[(unsigned char)text[s + j]];
            int gs_shift = gs[j + 1];
            int shift    = (bc_shift > gs_shift) ? bc_shift : gs_shift;
            if (shift < 1) shift = 1;

            /* 2-gram bonus shift on the byte pair (c1,c2) just past the window.
             * Safe-shift derivation: an alignment at s+Δ places c1=text[s+m] at
             * pattern index m-Δ and c2=text[s+m+1] at m-Δ+1.
             *   Δ==1 : only c1 is inside the window (at the last index) — it may
             *          match iff pattern[m-1]==c1, so the shift must be 1 then.
             *   Δ in [2,m] : both bytes inside — possible only if the *pair*
             *          occurs at pattern index m-Δ; rightmost occurrence gives
             *          the smallest such Δ = m - bc2[idx].
             *   else : neither byte can land on a match → skip past (m+1).
             * Omitting the Δ==1 guard (as a naive Sunday-2 would) skips real
             * matches; with it the bigram shift is provably non-skipping and
             * still dominates the single-byte Sunday rule. */
            if (s + pat_len + 1 < text_len) {
                unsigned char c1 = (unsigned char)text[s + pat_len];
                int bigram_shift;
                if ((unsigned char)pattern[pat_len - 1] == c1) {
                    bigram_shift = 1;
                } else {
                    int idx = c1 * 256 + (unsigned char)text[s + pat_len + 1];
                    bigram_shift = (bc2[idx] < 0) ? (pat_len + 1)
                                                  : (pat_len - bc2[idx]);
                }
                if (bigram_shift > shift) shift = bigram_shift;
            } else if (s + pat_len < text_len) {
                /* tail window: only one byte beyond — single-byte Sunday rule */
                int sunday_shift = pat_len - bc[(unsigned char)text[s + pat_len]];
                if (sunday_shift > shift) shift = sunday_shift;
            }

            s += shift;
        }
    }

    free(bc2);
    free(gs);
    return count;
}
