#ifndef ALGORITHMS_H
#define ALGORITHMS_H

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#define MAX_RESULTS   1000000

#define ALPHABET_SIZE 256

void flowscan_build_lps(const char *pattern, int pat_len, int *lps);

int flowscan_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res);

void skipstride_build_bad_char(const char *pattern, int pat_len, int bc[ALPHABET_SIZE]);
void skipstride_build_good_suffix(const char *pattern, int pat_len, int *gs);

int skipstride_search(const char *text,    int text_len,
                      const char *pattern, int pat_len,
                      int *positions,      int max_res);

int twinhash_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res);

int bitanchor_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int *positions,      int max_res);

int webscan_search(const char *text,    int text_len,
                   const char *pattern, int pat_len,
                   int *positions,      int max_res);

/* True multi-pattern Aho-Corasick. Reports (position, pattern_id) pairs in
 * positions[]/pattern_ids[] (pattern_ids may be NULL to ignore ids). Returns
 * the match count, or a negative value on allocation failure. */
int webscan_search_multi(const char *text, int text_len,
                         const char **patterns, const int *pat_lens,
                         int n_patterns,
                         int *positions, int *pattern_ids, int max_res);

int tiermatch_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int         max_errors,
                     int        *positions, int max_res);

#endif 
