import sys
msg = sys.stdin.read()
lines = [l for l in msg.splitlines() if "Co-Authored-By:" not in l]
cleaned = "\n".join(lines).rstrip()
print(cleaned)
