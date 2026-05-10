/**
 * Rabin-Karp String Matching Algorithm  (Rolling Polynomial Hash)
 * ================================================================
 *
 * Computes a hash for the pattern and slides a window of the same width
 * across the text.  Hash equality triggers a character-by-character
 * verification to eliminate false positives (spurious hash collisions).
 *
 *  Rolling hash update  (O(1) per step, avoiding O(m) recomputation)
 *  ──────────────────────────────────────────────────────────────────
 *  Let h = BASE^(m-1) mod MOD
 *  hash_new = (BASE * (hash_old - text[i] * h) + text[i+m]) mod MOD
 *
 *  Using a large prime MOD minimises collision probability to ≈ 1/MOD.
 *
 * Complexity
 *   Preprocessing : O(m)
 *   Search avg    : O(n + m)   expected with large prime MOD
 *   Search worst  : O(n · m)  if hash collisions occur on every window
 *   Space         : O(1)
 *
 * When APME prefers Rabin-Karp
 *   - Multiple patterns (hash all at once, single text pass)
 *   - Short patterns in large texts (rolling hash at O(1) per window)
 *   - Fingerprinting / plagiarism detection use-cases
 *
 * Reference: Karp & Rabin, "Efficient Randomized Pattern-Matching Algorithms",
 *            IBM J. Res. Dev. 31(2), 1987.
 */

#include "algorithms.h"
#include <stdlib.h>

/* Hash parameters */
#define RK_BASE  256LL
#define RK_MOD   1000000007LL   /* large prime → collision prob ≈ 10^-9 */

int rk_search(const char *text,    int text_len,
              const char *pattern, int pat_len,
              int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    /*
     * Compute h = BASE^(pat_len - 1) % MOD
     * This is the coefficient of the leftmost character when removing it
     * from the rolling window.
     */
    long long h = 1;
    for (int i = 0; i < pat_len - 1; i++)
        h = (h * RK_BASE) % RK_MOD;

    /* Initial hash values for pattern and first window */
    long long pat_hash = 0;
    long long win_hash = 0;

    for (int i = 0; i < pat_len; i++) {
        pat_hash = (RK_BASE * pat_hash + (unsigned char)pattern[i]) % RK_MOD;
        win_hash = (RK_BASE * win_hash + (unsigned char)text[i])    % RK_MOD;
    }

    int count = 0;

    for (int i = 0; i <= text_len - pat_len; i++) {
        if (pat_hash == win_hash) {
            /* Hash match: verify character-by-character to rule out collision */
            int match = 1;
            for (int k = 0; k < pat_len; k++) {
                if (text[i + k] != pattern[k]) { match = 0; break; }
            }
            if (match && count < max_res)
                positions[count++] = i;
        }

        /* Roll the hash forward (skip last window position) */
        if (i < text_len - pat_len) {
            /*
             * Subtract leftmost character's contribution, multiply by BASE,
             * add next character.  Add RK_MOD before modulo to keep positive.
             */
            win_hash = (RK_BASE *
                        ((win_hash - (unsigned char)text[i] * h % RK_MOD + RK_MOD) % RK_MOD)
                        + (unsigned char)text[i + pat_len]) % RK_MOD;
        }
    }

    return count;
}
