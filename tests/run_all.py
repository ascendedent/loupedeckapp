"""Run every test_*.py in this directory and summarise."""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

rc = 0
results = []
for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
    name = os.path.basename(path)
    p = subprocess.run([sys.executable, path], capture_output=True, text=True)
    tail = [l for l in p.stdout.splitlines() if "checks failed" in l]
    ok = p.returncode == 0
    rc |= 0 if ok else 1
    results.append((name, ok, tail[-1] if tail else "(no summary)"))
    if not ok:
        print(p.stdout)
        print(p.stderr)

print("=" * 60)
for name, ok, summary in results:
    print("%-24s %-5s %s" % (name, "ok" if ok else "FAIL", summary.strip()))
sys.exit(rc)
