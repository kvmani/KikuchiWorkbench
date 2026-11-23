"""Reproduce the controlled cubic discrimination tables.

    python benchmarks/run_cubic_discrimination.py --mode quick   # ~minutes on a laptop CPU
    python benchmarks/run_cubic_discrimination.py --mode full

Outputs go to benchmarks/results/<mode>_<date>/ (report.md, results.json, thresholds.json, CSVs).
Generated masters and dictionaries are cached under --cache (default: <out>/cache, not committed).
"""

import argparse
import datetime as dt
import warnings
from pathlib import Path

from kikuchiworkbench.benchmark import run_benchmark

if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["quick", "full"], default="quick")
    ap.add_argument("--n-side", type=int, default=None, help="scan is n_side x n_side points")
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache", default=None)
    ap.add_argument("--refine", action="store_true", help="equal-budget orientation refinement per phase")
    a = ap.parse_args()
    out = Path(a.out or Path(__file__).parent / "results" / f"{a.mode}{'_refined' if a.refine else ''}_{dt.date.today().isoformat()}")
    run_benchmark(out, mode=a.mode, n_side=a.n_side, cache_dir=a.cache, refine=a.refine)
