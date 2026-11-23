"""Build the one-folder bundle with PyInstaller, outside the repository.

    pip install pyinstaller
    python packaging/build_bundle.py [--out ~/kwb_build]

Then on Windows compile the installer with Inno Setup:  iscc packaging/kikuchiworkbench.iss
(pass /DBundleDir=<out>\\dist\\KikuchiWorkbench). Nothing produced here is committed (cardinal rule).
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / "kwb_build"))
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(out / "dist"),
           "--workpath", str(out / "build"), str(HERE / "kikuchiworkbench.spec")]
    print(" ".join(cmd))
    sys.exit(subprocess.call(cmd))
