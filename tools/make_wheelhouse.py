"""Build an offline wheelhouse for installing KikuchiWorkbench on a machine without internet.

Run on a connected machine with the SAME OS, architecture and Python version as the target:

    python tools/make_wheelhouse.py --out wheelhouse [--extras gui]

Copy the folder to the target, then:

    pip install --no-index --find-links wheelhouse "kikuchiworkbench[gui]"

The script records the Python version, platform and every wheel's sha256 in wheelhouse/MANIFEST.json.
"""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="wheelhouse")
    ap.add_argument("--extras", default="gui", help="comma-separated extras, e.g. gui or gui,cuda")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = f"{ROOT}[{a.extras}]" if a.extras else str(ROOT)
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--wheel-dir", str(out), spec], check=True)
    wheels = {}
    for w in sorted(out.glob("*.whl")):
        wheels[w.name] = hashlib.sha256(w.read_bytes()).hexdigest()
    (out / "MANIFEST.json").write_text(json.dumps({
        "python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
        "extras": a.extras, "wheels": wheels}, indent=2))
    target = f"kikuchiworkbench[{a.extras}]" if a.extras else "kikuchiworkbench"
    print(f"{len(wheels)} wheels in {out}; install with: pip install --no-index --find-links {out} \"{target}\"")
