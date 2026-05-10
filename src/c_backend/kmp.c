/**
 * KMP – Knuth-Morris-Pratt String Matching Algorithm
 * ====================================================
 *
 * Core idea: Pre-process the pattern into an LPS (Longest Proper Prefix
 * which is also a Suffix) table. On a mismatch at pattern[j], instead of
 * resetting j to 0, we "jump" to lps[j-1] — the longest border of
 * pattern[0..j-1]. This guarantees that each character in the text is
 * examined at most twice (once by i, once to resolve a mismatch via LPS),
 * giving a worst-case O(n + m) bound.
 *
 * Complexity
 *   Preprocessing : O(m)
 *   Search        : O(n)
 *   Space         : O(m)  (LPS table)
 *
 * When APME prefers KMP
 *   - Short patterns (m ≤ 2): preprocessing overhead of BM/RK not worth it
 *   - Small alphabets (binary, DNA): BM bad-char skips shrink; worst-case O(n·m)
 *   - Highly repetitive text (>70 % same char): BM degrades; KMP stays linear
 *
 * Reference: Knuth, Morris & Pratt, "Fast Pattern Matching in Strings",
 *            SIAM J. Comput. 6(2), 1977.
 */

#include "algorithms.h"
#include <stdlib.h>

/* ---------------------------------------------------------------------- */
/*  LPS table construction                                                 */
/* ---------------------------------------------------------------------- */

void kmp_build_lps(const char *pattern, int pat_len, int *lps) {
    int len = 0;   /* length of current longest prefix-suffix */
    lps[0]  = 0;   /* first character has no proper prefix    */
    int i   = 1;

    while (i < pat_len) {
        if (pattern[i] == pattern[len]) {
            /* Extend the current border */
            lps[i] = ++len;
            i++;
        } else if (len != 0) {
            /* Fall back: try shorter border, do NOT increment i */
            len = lps[len - 1];
        } else {
            /* No border exists for this position */
            lps[i] = 0;
            i++;
        }
    }
}

/* ---------------------------------------------------------------------- */
/*  KMP search                                                             */
/* ---------------------------------------------------------------------- */

int kmp_search(const char *text,    int text_len,
               const char *pattern, int pat_len,
               int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    int *lps = (int *)malloc((size_t)pat_len * sizeof(int));
    if (!lps) return -1;  /* allocation failure */

    kmp_build_lps(pattern, pat_len, lps);

    int count = 0;
    int i = 0;  /* cursor in text    */
    int j = 0;  /* cursor in pattern */

    while (i < text_len) {
        if (pattern[j] == text[i]) {
            i++;
            j++;
        }

        if (j == pat_len) {
            /* ── Complete match at text[i - pat_len] ── */
            if (count < max_res)
                positions[count++] = i - pat_len;
            j = lps[j - 1];          /* shift: look for overlapping matches */

        } else if (i < text_len && pattern[j] != text[i]) {
            /* ── Mismatch ── */
            if (j != 0)
                j = lps[j - 1];     /* jump using LPS table */
            else
                i++;                /* no border: advance text cursor */
        }
    }

    free(lps);
    return count;
}
