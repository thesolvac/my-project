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

int tiermatch_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int         max_errors,
                     int        *positions, int max_res);

#endif 
