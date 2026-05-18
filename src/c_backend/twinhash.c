#include "algorithms.h"
#include <stdlib.h>

#define TH_BASE1  256LL
#define TH_MOD1   1000000007LL    

#define TH_BASE2  31LL
#define TH_MOD2   998244353LL     

int twinhash_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    
    long long h1 = 1, h2 = 1;
    for (int i = 0; i < pat_len - 1; i++) {
        h1 = (h1 * TH_BASE1) % TH_MOD1;
        h2 = (h2 * TH_BASE2) % TH_MOD2;
    }

    
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
        
        if (win_h1 == pat_h1 && win_h2 == pat_h2) {
            int match = 1;
            for (int k = 0; k < pat_len; k++) {
                if (text[i + k] != pattern[k]) { match = 0; break; }
            }
            if (match && count < max_res)
                positions[count++] = i;
        }

        
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
