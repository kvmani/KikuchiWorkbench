"""Fail if any tracked or staged file is binary (cardinal rule: no binary content in the repository).

Binary = contains a NUL byte in its first 8 KiB, or has a known binary extension. Review artifacts (decks,
screenshots, maps, HDF5 results) live outside the repository, e.g. in ~/kwb_review_artifacts.

    python tools/check_no_binaries.py          # checks git index (tracked + staged files)
"""

import subprocess
import sys
from pathlib import Path

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".ico", ".pdf", ".pptx", ".ppt",
    ".docx", ".doc", ".xlsx", ".xls", ".zip", ".gz", ".tar", ".7z", ".h5", ".hdf5", ".h5oina", ".oh5",
    ".ebsp", ".up1", ".up2", ".npy", ".npz", ".pkl", ".whl", ".exe", ".dll", ".so", ".bundle", ".mp4",
}


def is_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXT:
        return True
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(8192)
    except OSError:
        return False


def main() -> int:
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    bad = [f for f in files if f and (root / f).exists() and is_binary(root / f)]
    if bad:
        print("Binary files must not be committed (keep them outside the repository):", file=sys.stderr)
        for f in bad:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"OK: {len([f for f in files if f])} tracked files, no binaries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
