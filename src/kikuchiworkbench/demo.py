"""Offline CPU demo.

Single-phase (default): the EMsoft *dynamical* Ni master bundled with kikuchipy
is projected with known random (off-grid) orientations onto an asymmetric,
off-centre detector, with background and Poisson noise, written as a project
fixture, then re-imported and indexed through the normal pipeline.

Two-phase (``two_phase=True``): kinematical Ni (a = 3.524 Å) and Cu
(a = 3.615 Å) masters are generated from the CIFs shipped with the package
and used both to simulate and to index a two-phase scan. This is a synthetic
classification exercise; kinematical masters are not dynamical simulations.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from .io.readers import read_fixture_truth, write_fixture
from .jobs import Job
from .masters.importer import load_master
from .pipeline import IndexingConfig, PhaseSpec, run_indexing
from .synthetic import SyntheticSpec, make_synthetic_scan, misorientation_deg

DATA_DIR = Path(__file__).parent / "data"


def bundled_ni_master() -> str:
    import kikuchipy as kp

    p = Path(kp.__file__).parent / "data" / "emsoft_ebsd_master_pattern" / "ni_mc_mp_20kv_uint8_gzip_opts9.h5"
    if not p.exists():  # pragma: no cover
        raise FileNotFoundError(f"kikuchipy's bundled Ni master not found at {p}")
    return str(p)


def kinematical_pair(out_dir: str | os.PathLike, half_size: int = 150) -> list[str]:
    from .crystal.cif import read_cif
    from .masters.kinematical import simulate_kinematical_master

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in ("ni", "cu"):
        p = out / f"{name}_kinematical_20kV.h5"
        if not p.exists():
            model = read_cif(DATA_DIR / "cif" / f"{name}.cif", name=name.capitalize())
            simulate_kinematical_master(model, p, voltage_kV=20.0, dmin_A=0.8, half_size=half_size)
        paths.append(str(p))
    return paths


def evaluate(result, truth: dict) -> dict:
    q_true = np.asarray(truth["quaternion"])
    ph_true = np.asarray(truth["phase_id"]).astype(int)
    d = result.decision
    n = len(ph_true)
    mis = np.full(n, np.nan)
    for p, phase in enumerate(result.phases):
        sel = (d.phase == p) & (ph_true == p)
        if sel.any():
            mis[sel] = misorientation_deg(result.best_quaternion[p][sel], q_true[sel], phase.point_group)
    n_ph = len(result.phases)
    conf = np.zeros((n_ph, n_ph + 2), dtype=int)  # columns: phases..., ambiguous, unindexed/other
    for t, lab, ph in zip(ph_true, d.label, d.phase, strict=True):
        if lab == 0:
            conf[t, ph] += 1
        elif lab == 1:
            conf[t, n_ph] += 1
        else:
            conf[t, n_ph + 1] += 1
    correct_phase = (d.phase == ph_true) & (d.label == 0)
    return {
        "n_points": int(n),
        "phase_accuracy_of_all": float(correct_phase.mean()),
        "confusion_rows_true_cols_pred_amb_unidx": conf.tolist(),
        "median_misorientation_deg": float(np.nanmedian(mis)) if np.isfinite(mis).any() else None,
        "max_misorientation_deg": float(np.nanmax(mis)) if np.isfinite(mis).any() else None,
        "fraction_within_5deg": float(np.mean(np.nan_to_num(mis, nan=999) <= 5.0)),
    }


def run_demo(jobs_root: str | os.PathLike = "kwb_jobs", n_rows: int = 6, n_cols: int = 6,
             resolution_deg: float = 4.0, backend: str = "cpu", listener=None,
             two_phase: bool = False, seed: int = 42):
    job = Job.create(jobs_root, "demo")
    if listener:
        job.add_listener(listener)
    inputs = job.path / "inputs"
    inputs.mkdir()

    def body(j: Job):
        j.progress(0.0, "Preparing demo inputs")
        if two_phase:
            master_paths = kinematical_pair(inputs)
            names = ["Ni", "Cu"]
        else:
            master_paths = [bundled_ni_master()]
            names = ["Ni"]
        masters = [load_master(p, phase_name=n) for p, n in zip(master_paths, names, strict=True)]
        spec = SyntheticSpec(nrows=n_rows, ncols=n_cols, seed=seed,
                             phase_layout="halves" if two_phase else "single")
        scan, truth = make_synthetic_scan(masters, spec)
        fixture = write_fixture(inputs / "demo_scan.h5", scan, truth=truth,
                                provenance={"generator": "kikuchiworkbench.synthetic",
                                            "spec": spec.to_dict(), "masters": master_paths})
        cfg = IndexingConfig(
            scan={"path": str(fixture)},
            phases=[PhaseSpec(master=p, name=n) for p, n in zip(master_paths, names, strict=True)],
            sampling={"resolution_deg": resolution_deg},
            matching={"backend": backend},
            decision={"min_score": 0.10, "ambiguity_margin": 0.005,
                      "provenance": "demo defaults (provisional)"},
        )
        result = run_indexing(cfg, job=j)
        truth2 = read_fixture_truth(fixture)
        report = evaluate(result, truth2)
        report["resolution_deg"] = resolution_deg
        report["masters"] = {n: p for n, p in zip(names, master_paths, strict=True)}
        report["kinematical"] = bool(two_phase)
        med = report["median_misorientation_deg"]
        report["passed"] = bool(
            med is not None and med <= resolution_deg and report["phase_accuracy_of_all"] >= 0.9
        )
        result.manifest.results["demo_evaluation"] = report
        result.manifest.write(j.outputs / "manifest.json")
        return result, report

    result, report = job.run(body)
    return job, result, report
