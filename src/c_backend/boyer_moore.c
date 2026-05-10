/**
 * Boyer-Moore String Matching Algorithm
 * =======================================
 * Combines two independent shift heuristics; on each mismatch the
 * algorithm takes the LARGER shift, guaranteeing forward progress.
 *
 *  Bad Character (BC) rule
 *  ────────────────────────
 *  Mismatch at text[s+j].  Shift the window so that the rightmost
 *  occurrence of text[s+j] inside the pattern lines up with text[s+j].
 *  bc[c] stores the last index of character c in the pattern (-1 if absent).
 *  BC shift = j − bc[ text[s+j] ]   (minimum 1)
 *
 *  Good Suffix (GS) rule
 *  ──────────────────────
 *  The suffix pattern[j+1..m-1] matched.  Shift so either:
 *    (a) Another occurrence of that suffix inside the pattern aligns, or
 *    (b) A prefix of the pattern matching a suffix of the matched region aligns.
 *  gs[j+1] stores the shift for a mismatch at position j.
 *
 *  Combined shift = max( BC_shift, GS_shift )
 *
 * Complexity
 *   Preprocessing : O(m + sigma)
 *   Search best   : O(n / m)   sub-linear — skips up to m chars per step
 *   Search worst  : O(n)       with GS table (without GS: O(n·m))
 *   Space         : O(m + sigma)
 *
 * When APME prefers Boyer-Moore
 *   - Natural language / source-code text (large alphabet → big BC skips)
 *   - Long patterns (m > 10) where skips matter most
 *   - General-purpose default for mixed text
 *
 * Reference: Boyer & Moore, "A Fast String Searching Algorithm",
 *            CACM 20(10), 1977.
 */

#include "algorithms.h"
#include <stdlib.h>
#include <string.h>

/* ---------------------------------------------------------------------- */
/*  Bad Character table                                                    */
/* ---------------------------------------------------------------------- */

void bm_build_bad_char(const char *pattern, int pat_len, int bc[ALPHABET_SIZE]) {
    for (int i = 0; i < ALPHABET_SIZE; i++) bc[i] = -1;
    for (int i = 0; i < pat_len;      i++) bc[(unsigned char)pattern[i]] = i;
}

/* ---------------------------------------------------------------------- */
/*  Good Suffix table  (Apostolico-Giancarlo formulation)                 */
/* ---------------------------------------------------------------------- */

void bm_build_good_suffix(const char *pattern, int pat_len, int *gs) {
    /*
     * border[i] = start of the widest border of pattern[i..m-1]
     * A "border" of a string is a proper substring that is simultaneously
     * a prefix and a suffix of that string.
     *
     * Phase 1: compute border[] scanning right-to-left.
     * Phase 2: assign shifts for Case 2 (no matching suffix inside pattern).
     * Phase 3: assign shifts for Case 1 (matching suffix found inside pattern).
     */
    int *border = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    if (!border) return;

    /* Initialise all shifts to 0 */
    for (int i = 0; i <= pat_len; i++) gs[i] = 0;

    /* ── Phase 1: fill border[] right-to-left ── */
    int i = pat_len;
    int j = pat_len + 1;
    border[i] = j;

    while (i > 0) {
        /* Slide j until characters match or j falls off the right end */
        while (j <= pat_len && pattern[i - 1] != pattern[j - 1]) {
            /* Case 2: pattern[j..m-1] is the good suffix; no occurrence
               of it exists in pattern — the shift is j-i               */
            if (gs[j] == 0) gs[j] = j - i;
            j = border[j];
        }
        border[--i] = --j;
    }

    /* ── Phase 2: fill remaining positions with prefix-of-pattern matches ── */
    j = border[0];
    for (i = 0; i <= pat_len; i++) {
        if (gs[i] == 0) gs[i] = j;   /* Case 1: shift aligns longest prefix */
        if (i == j)     j = border[j];
    }

    free(border);
}

/* ---------------------------------------------------------------------- */
/*  Boyer-Moore search                                                     */
/* ---------------------------------------------------------------------- */

int bm_search(const char *text,    int text_len,
              const char *pattern, int pat_len,
              int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    /* Build preprocessing tables */
    int bc[ALPHABET_SIZE];
    bm_build_bad_char(pattern, pat_len, bc);

    int *gs = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    if (!gs) return -1;
    bm_build_good_suffix(pattern, pat_len, gs);

    int count = 0;
    int s = 0;   /* start of current pattern window in text */

    while (s <= text_len - pat_len) {
        int j = pat_len - 1;   /* compare right-to-left */

        while (j >= 0 && pattern[j] == text[s + j])
            j--;

        if (j < 0) {
            /* ── Full match at position s ── */
            if (count < max_res)
                positions[count++] = s;
            s += gs[0];   /* GS shift for a complete match */
        } else {
            /* ── Mismatch at position j ── */
            int bc_shift = j - bc[(unsigned char)text[s + j]];
            int gs_shift = gs[j + 1];
            int shift    = (bc_shift > gs_shift) ? bc_shift : gs_shift;
            if (shift < 1) shift = 1;   /* always advance at least 1 */
            s += shift;
        }
    }

    free(gs);
    return count;
}
