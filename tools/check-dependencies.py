"""Validate manually obtained dependencies without downloading or executing them."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'vendor/kss2vgm.exe'
expected='36314759d87c41077e8cc8dcd69f174d97da688883a8e62e506b5d7b87bdeeb6'
if not path.is_file():raise SystemExit('Obtain official kss2vgm 0.1.4 as documented in docs/BUILD.md, then place it in vendor/kss2vgm.exe.')
actual=hashlib.sha256(path.read_bytes()).hexdigest()
if actual!=expected:raise SystemExit('Converter hash differs from the verified 1.0.4 dependency; do not silently substitute another binary.')
print('kss2vgm 0.1.4: verified SHA-256')
