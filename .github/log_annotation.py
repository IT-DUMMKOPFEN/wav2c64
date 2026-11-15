"""Show a log file as GitHub error annotations (readable without
downloading the full job log): first the error lines, then the end."""
import re
import sys


def annotate(title, text):
    text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print("::error title=%s::%s" % (title, text))


try:
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        log = f.read()
except OSError:
    log = "(no log file)"
errors = [l for l in log.splitlines()
          if re.match(r"(E |>  |\S+\.py:\d+: |FAILED |ERROR |\w*Error)", l)]
if errors:
    annotate("errors", "\n".join(errors)[-3500:])
annotate("log", log[-15000:])
