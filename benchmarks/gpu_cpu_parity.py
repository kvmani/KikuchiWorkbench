"""Measure CPU/GPU parity, throughput and memory on the same fixture.

Run on a machine with an NVIDIA GPU and PyTorch+CUDA (`pip install -e ".[cuda]"`):

    python benchmarks/gpu_cpu_parity.py --n-side 20 --resolution 3 --vram-fraction 0.5

Writes benchmarks/results/parity_<date>_<host>/parity.json and report.md. On a machine without CUDA the
script records that the GPU leg did not run (it never reports parity it did not measure).
"""

import argparse
import datetime as dt
import json
import platform
import time
import warnings
from pathlib import Path

import numpy as np


def peak_rss_bytes():
    try:
        import resource

        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(r * (1 if platform.system() == "Darwin" else 1024))
    except ImportError:  # Windows
        try:
            import psutil

            return int(psutil.Process().memory_info().peak_wset)
        except Exception:
            return None


def run(backend, scan, masters, res, chunk, extra=None):
    from kikuchiworkbench.pipeline import IndexingConfig, PhaseSpec, run_indexing

    cfg = IndexingConfig(scan={"path": "<synthetic>"},
                         phases=[PhaseSpec(master=m.info.path, name=m.info.phase_name) for m in masters],
                         sampling={"resolution_deg": res},
                         matching={"backend": backend, "pattern_chunk": chunk, **(extra or {})})
    t0 = time.perf_counter()
    r = run_indexing(cfg, scan=scan, masters=masters, export=False)
    return r, time.perf_counter() - t0


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-side", type=int, default=20)
    ap.add_argument("--resolution", type=float, default=3.0)
    ap.add_argument("--chunk", type=int, default=4096)
    ap.add_argument("--vram-fraction", type=float, default=None,
                    help="cap PyTorch VRAM (e.g. 0.25 on an 8 GB card ~ 2 GB) to exercise batch shrinking")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    from kikuchiworkbench.demo import bundled_ni_master
    from kikuchiworkbench.indexing.matching import cuda_available
    from kikuchiworkbench.masters.importer import load_master
    from kikuchiworkbench.provenance import hardware_info, software_versions
    from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan

    m = load_master(bundled_ni_master(), phase_name="Ni")
    scan, _ = make_synthetic_scan([m], SyntheticSpec(nrows=a.n_side, ncols=a.n_side, seed=7))
    out = Path(a.out or Path(__file__).parent / "results" /
               f"parity_{dt.date.today().isoformat()}_{platform.node() or 'host'}")
    out.mkdir(parents=True, exist_ok=True)
    rec = {"n_patterns": scan.n_points, "resolution_deg": a.resolution, "software": software_versions(),
           "hardware": hardware_info()}
    r_cpu, t_cpu = run("cpu", scan, [m], a.resolution, a.chunk)
    rec["cpu"] = {"time_s": t_cpu, "timings": r_cpu.timings, "peak_rss_bytes": peak_rss_bytes()}
    if not cuda_available():
        rec["gpu"] = {"ran": False, "reason": "PyTorch CUDA not available on this machine"}
    else:
        import torch

        if a.vram_fraction:
            torch.cuda.set_per_process_memory_fraction(a.vram_fraction)
        torch.cuda.reset_peak_memory_stats()
        r_gpu, t_gpu = run("gpu", scan, [m], a.resolution, a.chunk)
        s_c, s_g = r_cpu.topk_scores[0], r_gpu.topk_scores[0]
        same_best = np.mean(r_cpu.topk_index[0][:, 0] == r_gpu.topk_index[0][:, 0])
        gap = s_c[:, 0] - s_c[:, 1]
        rec["gpu"] = {
            "ran": True, "device": torch.cuda.get_device_name(0), "time_s": t_gpu, "timings": r_gpu.timings,
            "peak_vram_bytes": int(torch.cuda.max_memory_allocated()),
            "max_abs_score_diff_top1": float(np.max(np.abs(s_c[:, 0] - s_g[:, 0]))),
            "max_abs_score_diff_topk": float(np.max(np.abs(s_c - s_g))),
            "fraction_same_best_index": float(same_best),
            "near_ties_top1_top2_lt_1e-5": int(np.sum(gap < 1e-5)),
            "events": [e for e in r_gpu.manifest.events if e["kind"] in ("fallback", "batch_size_change")],
            "backend_used": r_gpu.manifest.parameters["matching"]["backend_used"],
        }
    (out / "parity.json").write_text(json.dumps(rec, indent=2, default=str))
    g = rec["gpu"]
    lines = [f"# CPU/GPU parity ({dt.date.today()})", "", f"Patterns: {rec['n_patterns']}, grid {a.resolution}°",
             f"CPU: {rec['cpu']['time_s']:.2f} s", ""]
    if g["ran"]:
        lines += [f"GPU ({g['device']}): {g['time_s']:.2f} s, peak VRAM {g['peak_vram_bytes'] / 1e9:.2f} GB, "
                  f"backend used {g['backend_used']}",
                  f"max |ΔNCC| top-1 {g['max_abs_score_diff_top1']:.2e}, top-k {g['max_abs_score_diff_topk']:.2e}; "
                  f"same best index {g['fraction_same_best_index']:.4f}; near ties {g['near_ties_top1_top2_lt_1e-5']}",
                  f"fallback/batch events: {g['events']}"]
    else:
        lines.append(f"GPU leg did NOT run: {g['reason']}")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
