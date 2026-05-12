/**
 * TwinHash – APME Proprietary String Matching Algorithm
 * ======================================================
 *
 * Base algorithm : Rabin-Karp (single rolling polynomial hash)
 * APME optimisation : dual independent rolling hashes
 *
 * How it differs from classic Rabin-Karp
 * ───────────────────────────────────────
 * Classic Rabin-Karp uses one hash; when it collides, a full O(m)
 * character comparison is required to confirm or reject the match.
 * TwinHash maintains TWO independent rolling hashes (different base and
 * modulus pairs) in parallel.  Character-by-character verification is
 * only triggered when BOTH hashes agree simultaneously.  The probability
 * of a simultaneous false collision is 1/(MOD1 × MOD2) ≈ 10⁻¹⁸, making
 * spurious verifications practically impossible for any realistic text.
 *
 * The rolling update cost doubles (two hash computations per window slide)
 * but the savings from eliminating verification calls overwhelmingly
 * dominate on texts with many near-collisions.
 *
 * Complexity
 *   Preprocessing : O(m)
 *   Search avg    : O(n + m)   — near-zero false-positive verifications
 *   Search worst  : O(n · m)  — theoretical, requires deliberate collision
 *   Space         : O(1)
 *
 * When APME prefers TwinHash
 *   - Multiple patterns (hash all simultaneously, single text pass)
 *   - Short patterns (m ≤ 10) in very large texts
 *   - Fingerprinting / plagiarism detection
 */

#include "algorithms.h"
#include <stdlib.h>

/* Primary hash parameters */
#define TH_BASE1  256LL
#define TH_MOD1   1000000007LL    /* large prime, collision prob ≈ 10⁻⁹  */

/* Secondary hash parameters (independent base and modulus) */
#define TH_BASE2  31LL
#define TH_MOD2   998244353LL     /* NTT-friendly prime, also ≈ 10⁹       */

int twinhash_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    /*
     * Precompute h1 = BASE1^(pat_len-1) % MOD1
     *            h2 = BASE2^(pat_len-1) % MOD2
     * These are the coefficients used to remove the leftmost character
     * from each rolling window.
     */
    long long h1 = 1, h2 = 1;
    for (int i = 0; i < pat_len - 1; i++) {
        h1 = (h1 * TH_BASE1) % TH_MOD1;
        h2 = (h2 * TH_BASE2) % TH_MOD2;
    }

    /* Compute initial hashes for pattern and first text window */
    long long pat_h1 = 0, pat_h2 = 0;
    long long win_h1 = 0, win_h2 = 0;

    for (int i = 0; i < pat_len; i++) {
        pat_h1 = (TH_BASE1 * pat_h1 + (unsigned char)pattern[i]) % TH_MOD1;
        win_h1 = (TH_BASE1 * win_h1 + (unsigned char)text[i])    % TH_MOD1;
        pat_h2 = (TH_BASE2 * pat_h2 + (unsigned char)pattern[i]) % TH_MOD2;
        win_h2 = (TH_BASE2 * win_h2 + (unsigned char)text[i])    % TH_MOD2;
    }

    int count = 0;

    for (int i = 0; i <= text_len - pat_len; i++) {
        /*
         * APME TwinHash optimisation:
         * Only verify character-by-character when BOTH hashes agree.
         * A single-hash collision probability is ≈1/10⁹; dual-hash is ≈10⁻¹⁸.
         */
        if (win_h1 == pat_h1 && win_h2 == pat_h2) {
            int match = 1;
            for (int k = 0; k < pat_len; k++) {
                if (text[i + k] != pattern[k]) { match = 0; break; }
            }
            if (match && count < max_res)
                positions[count++] = i;
        }

        /* Roll both hashes forward */
        if (i < text_len - pat_len) {
            win_h1 = (TH_BASE1 *
                      ((win_h1 - (unsigned char)text[i] * h1 % TH_MOD1 + TH_MOD1) % TH_MOD1)
                      + (unsigned char)text[i + pat_len]) % TH_MOD1;

            win_h2 = (TH_BASE2 *
                      ((win_h2 - (unsigned char)text[i] * h2 % TH_MOD2 + TH_MOD2) % TH_MOD2)
                      + (unsigned char)text[i + pat_len]) % TH_MOD2;
        }
    }

    return count;
}
