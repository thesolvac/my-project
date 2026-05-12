# =============================================================================
# APME C Backend – Makefile
# =============================================================================
# Compiles all six algorithm translation units into a single shared library.
# Supports Windows (MinGW), Linux, and macOS.
#
# Usage:
#   make          → build shared library
#   make clean    → remove compiled artifacts
# =============================================================================

CC     = gcc
CFLAGS = -O2 -Wall -Wextra -fPIC
SRC    = flowscan.c skipstride.c twinhash.c bitanchor.c webscan.c tiermatch.c

# ── Platform detection ────────────────────────────────────────────────────
ifeq ($(OS), Windows_NT)
    TARGET  = algorithms.dll
    LDFLAGS = -shared
else
    UNAME := $(shell uname -s)
    ifeq ($(UNAME), Darwin)
        TARGET  = algorithms.dylib
        LDFLAGS = -shared -dynamiclib
    else
        TARGET  = algorithms.so
        LDFLAGS = -shared
    endif
endif

# ── Rules ─────────────────────────────────────────────────────────────────
.PHONY: all clean

all: $(TARGET)
	@echo "C backend compiled: $(TARGET)"

$(TARGET): $(SRC) algorithms.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(SRC)

clean:
	rm -f algorithms.dll algorithms.so algorithms.dylib *.o
