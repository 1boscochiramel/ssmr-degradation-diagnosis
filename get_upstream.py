"""Fetch the pinned upstream benchmark (MIT) into ./upstream without modifying it."""
from pathlib import Path
import subprocess, sys

COMMIT = 'c6280844404cbef38da8a893a095a734bc0d4815'
URL = 'https://github.com/arcmateo/SSMR_Benchmark.git'
dst = Path(__file__).resolve().parent / 'upstream'
if not dst.exists():
    subprocess.run(['git', 'clone', URL, str(dst)], check=True)
subprocess.run(['git', '-C', str(dst), 'checkout', '--quiet', COMMIT], check=True)
head = subprocess.run(['git', '-C', str(dst), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
assert head == COMMIT, head
print('upstream at', head)
sys.exit(0)
