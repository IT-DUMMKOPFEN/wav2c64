"""Print the end of a log file as a GitHub error annotation (so it can be
read without downloading the full job log)."""
import sys

try:
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        text = f.read()[-15000:]
except OSError:
    text = "(no log file)"
text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
print("::error title=log::" + text)
