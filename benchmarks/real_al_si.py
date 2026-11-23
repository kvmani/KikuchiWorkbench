"""Real-data interoperability check: public Oxford Al-10Si .ebsp with EMsoft Al and Si masters.

Data (CC-BY-4.0): Zenodo 20290635 (scan), 7628365 (Al master), 7498729 (Si master). Fetch with
    python benchmarks/fetch_public_data.py al_si al_master si_master --dest ~/kwb_data
then
    python benchmarks/real_al_si.py --data ~/kwb_data --roi 100 140 100 150 --resolution 2.5

Workflow (shared core): load .ebsp (no calibration in file) with the starting PC used by the dataset authors
(Bruker (0.50, 0.15, 1.25), detector tilt 5 deg) -> shared PC calibration on Al -> Al + Si dictionaries with the same
sampling -> NCC matching -> equal-budget refinement -> phase decision -> maps, CSV, HDF5, manifest.
"""

import argparse
import json
import warnings
from pathlib import Path

from kikuchiworkbench.pipeline import IndexingConfig, PhaseSpec, run_indexing_job

SCAN = "al_si/x/al10si_oxford/260d272e-5d2a-4adc-b195-f3230f03ee22.ebsp"


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Path.home() / "kwb_data"))
    ap.add_argument("--roi", type=int, nargs=4, default=[100, 140, 100, 150], metavar=("R0", "R1", "C0", "C1"))
    ap.add_argument("--resolution", type=float, default=2.5)
    ap.add_argument("--jobs", default="kwb_jobs")
    ap.add_argument("--no-refine", action="store_true")
    a = ap.parse_args()
    d = Path(a.data).expanduser()
    scan = d / SCAN
    if not scan.exists():
        import zipfile

        with zipfile.ZipFile(d / "al_si" / "al10si_oxford.zip") as z:
            z.extractall(d / "al_si" / "x")
    cfg = IndexingConfig(
        scan={"path": str(scan), "geometry": {"pc": [0.50, 0.15, 1.25], "pc_convention": "bruker", "tilt": 5.0,
                                              "sample_tilt": 70.0}},
        phases=[PhaseSpec(master=str(d / "al_master" / "al_mc_mp_20kv.h5"), name="Al", energy=20.0),
                PhaseSpec(master=str(d / "si_master" / "si_mc_mp_20kv.h5"), name="Si", energy=20.0)],
        sampling={"resolution_deg": a.resolution},
        preprocessing=[{"op": "static_background", "mode": "subtract", "source": "scan_mean"},
                       {"op": "dynamic_background", "sigma_frac": 0.125, "mode": "subtract"},
                       {"op": "bin", "factor": 2}],
        matching={"backend": "auto", "cache_dictionary": True, "dictionary_chunk": 4000},
        calibration={"enabled": True, "phase": 0, "n_points": 12, "resolution_deg": 4.0, "pc_trust": 0.1},
        refinement={} if a.no_refine else {"enabled": True, "maxeval": 300},
        decision={"min_score": 0.10, "ambiguity_margin": 0.005,
                  "provenance": "provisional defaults; not calibrated for Al-Si"},
        roi=list(a.roi),
    )

    def progress(f, msg):
        if msg and ("Calibrat" in msg or "matched" not in msg or int(f * 100) % 10 == 0):
            print(f"[{100 * f:5.1f}%] {msg}", flush=True)

    job, r = run_indexing_job(cfg, a.jobs, listener=progress)
    m = r.manifest
    summary = {
        "job": str(job.path), "roi": a.roi, "n_points": r.n_points, "counts": r.decision.counts(),
        "phase_fraction_of_indexed": {n: float((r.decision.phase == i).sum() / max(1, (r.decision.label == 0).sum()))
                                      for i, n in enumerate(r.phase_names)},
        "pc_calibration": {k: m.parameters["pc_calibration"][k]
                           for k in ("pc_bruker_start", "pc_bruker", "pc_spread_std", "n_used")},
        "median_best_ncc": float(__import__("numpy").median(r.decision.best_score)),
        "timings": r.timings,
        "events": [e["message"] for e in m.events],
    }
    (job.outputs / "real_al_si_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
