#include "algorithms.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int child[ALPHABET_SIZE];
    int fail;
    int output;
} AcNode;

static AcNode *build_dfa(const char *pattern, int m) {
    AcNode *nodes = (AcNode *)malloc((size_t)(m + 1) * sizeof(AcNode));
    if (!nodes) return NULL;

    for (int i = 0; i <= m; i++) {
        for (int c = 0; c < ALPHABET_SIZE; c++) nodes[i].child[c] = -1;
        nodes[i].fail   = 0;
        nodes[i].output = 0;
    }

    for (int j = 0; j < m; j++)
        nodes[j].child[(unsigned char)pattern[j]] = j + 1;
    nodes[m].output = 1;

    int *queue = (int *)malloc((size_t)(m + 1) * sizeof(int));
    if (!queue) { free(nodes); return NULL; }
    int head = 0, tail = 0;

    for (int c = 0; c < ALPHABET_SIZE; c++) {
        int ch = nodes[0].child[c];
        if (ch != -1) {
            nodes[ch].fail = 0;
            queue[tail++]  = ch;
        } else {
            nodes[0].child[c] = 0;
        }
    }

    while (head < tail) {
        int u = queue[head++];
        for (int c = 0; c < ALPHABET_SIZE; c++) {
            int v = nodes[u].child[c];
            if (v != -1) {
                nodes[v].fail    = nodes[nodes[u].fail].child[c];
                nodes[v].output |= nodes[nodes[v].fail].output;
                queue[tail++]    = v;
            } else {
                nodes[u].child[c] = nodes[nodes[u].fail].child[c];
            }
        }
    }

    free(queue);
    return nodes;
}

int webscan_search(const char *text,    int text_len,
                   const char *pattern, int pat_len,
                   int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    AcNode *dfa = build_dfa(pattern, pat_len);
    if (!dfa) return -1;

    
    uint64_t presence[4];
    memset(presence, 0, sizeof presence);
    for (int j = 0; j < pat_len; j++) {
        unsigned char c = (unsigned char)pattern[j];
        presence[c >> 6] |= (uint64_t)1 << (c & 63);
    }

    int state = 0;
    int count = 0;

    for (int i = 0; i < text_len; i++) {
        unsigned char c = (unsigned char)text[i];

        
        if (!(presence[c >> 6] & ((uint64_t)1 << (c & 63)))) {
            state = 0;
            continue;
        }

        state = dfa[state].child[c];
        if (dfa[state].output) {
            if (count < max_res)
                positions[count] = i - pat_len + 1;
            count++;
        }
    }

    free(dfa);
    return count;
}
