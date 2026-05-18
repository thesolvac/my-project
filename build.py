import argparse
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).parent / "src" / "c_backend"
SOURCES = ["flowscan.c", "skipstride.c", "twinhash.c", "bitanchor.c", "webscan.c", "tiermatch.c"]

def target() -> Path:
    if sys.platform.startswith("win"):
        return BACKEND / "algorithms.dll"
    if sys.platform.startswith("darwin"):
        return BACKEND / "algorithms.dylib"
    return BACKEND / "algorithms.so"

def build() -> bool:
    out = target()
    src = [str(BACKEND / f) for f in SOURCES]

    if sys.platform.startswith("win"):
        flags = ["-shared", "-O2", "-Wall"]
    elif sys.platform.startswith("darwin"):
        flags = ["-shared", "-dynamiclib", "-fPIC", "-O2", "-Wall"]
    else:
        flags = ["-shared", "-fPIC", "-O2", "-Wall"]

    cmd = ["gcc"] + flags + ["-o", str(out)] + src

    print(f"  Compiling: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BACKEND))
    except FileNotFoundError:
        print("  ✗  gcc not found on PATH.")
        print()
        print("  To install GCC on Windows, download MinGW-w64:")
        print("    https://winlibs.com/  (choose 'Release' → 'Win64' → 'UCRT')")
        print("  Then add the bin/ folder to your PATH and re-run this script.")
        print()
        print("  The app will run with its pure-Python FlowScan fallback in the meantime.")
        return False

    if result.returncode == 0:
        print(f"  OK  C backend compiled -> {out.name}")
        return True

    print(f"  FAIL  Compilation failed (gcc exit code {result.returncode}):")
    if result.stderr:
        print(result.stderr)
    print()
    print("  The app will fall back to the pure-Python FlowScan implementation.")
    return False

def clean():
    removed = []
    for ext in ("*.dll", "*.so", "*.dylib", "*.o"):
        for p in BACKEND.glob(ext):
            p.unlink()
            removed.append(p.name)
    if removed:
        print(f"  Removed: {', '.join(removed)}")
    else:
        print("  Nothing to clean.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the APME C backend")
    parser.add_argument("--clean", action="store_true", help="Remove compiled artifacts")
    args = parser.parse_args()

    print("\n  APME – C Backend Builder")
    print("  " + "-" * 40)

    if args.clean:
        clean()
    else:
        ok = build()
        sys.exit(0 if ok else 1)
