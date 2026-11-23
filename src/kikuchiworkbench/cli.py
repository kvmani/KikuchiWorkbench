"""Headless command-line interface: ``kwb``.

Subcommands share the same core services as the GUI:

* ``kwb inspect SCAN``            detect format, show grid/detector/metadata
* ``kwb master inspect FILE``     verify an EMsoft master
* ``kwb master add FILE``         verify and copy into the master cache
* ``kwb cif validate FILE``       validate a CIF against the EMsoft representation
* ``kwb cif xtal FILE OUT``       write an EMsoft .xtal
* ``kwb kinematical CIF OUT``     kinematical master (synthetic fixtures only)
* ``kwb index CONFIG``            run indexing from a YAML/JSON config in a job folder
* ``kwb demo``                    offline CPU demo with the bundled Ni master
* ``kwb emsoft plan CIF``         write EMsoft job inputs (namelists) without running
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

from . import __version__
from .errors import WorkbenchError


def _print_json(d) -> None:
    print(json.dumps(d, indent=2, default=str))


def _geometry_args(a) -> dict | None:
    if a.pc is None:
        return None
    g = {"pc": a.pc, "pc_convention": a.pc_convention}
    for k in ("binning", "px_size", "sample_tilt", "tilt"):
        v = getattr(a, k, None)
        if v is not None:
            g[k] = v
    return g


def cmd_inspect(a) -> int:
    from .io.readers import load_scan

    scan = load_scan(a.scan, nav_shape=tuple(a.nav_shape) if a.nav_shape else None, step=a.step,
                     grid_type=a.grid_type, geometry=_geometry_args(a), companion=a.companion,
                     prefer_raw=not a.processed, lazy=True)
    s = scan.summary()
    if a.json:
        _print_json(s)
        return 0
    print(f"File:        {scan.source_path}")
    print(f"Format:      {s['file_format']} ({s['vendor']})  dataset: {s['dataset_path']}")
    g = s["grid"]
    print(f"Grid:        {g['grid_type']} {g['nrows']} x {g['ncols']} ({s['n_points']} points), "
          f"step {g['step_x']:.4g} x {g['step_y']:.4g} {g['unit']}")
    print(f"Patterns:    {s['pattern_shape'][0]} x {s['pattern_shape'][1]} px, {s['dtype']}")
    d = s["detector"]
    print("Detector:    PC (Bruker) = ({:.4f}, {:.4f}, {:.4f}), binning {}, sample tilt {:.1f}°, "
          "detector tilt {:.1f}°".format(*d["pc_bruker_mean"], d["binning"], d["sample_tilt_deg"],
                                         d["detector_tilt_deg"]))
    print(f"Geometry:    {s['geometry_source']}")
    for w in s["warnings"]:
        print(f"WARNING:     {w}")
    return 0


def cmd_master(a) -> int:
    from .masters.importer import inspect_master

    if a.master_cmd == "inspect":
        info = inspect_master(a.file)
        if a.json:
            _print_json(info.to_dict())
        else:
            print(f"{info.phase_name}: space group {info.space_group} ({info.point_group}), "
                  f"lattice (nm,deg) {info.lattice_nm_deg}")
            print(f"energies (keV): {info.energies_keV}; npx {info.npx}; hemispheres {info.hemispheres}")
            print(f"program: {info.program} version {info.emsoft_version}; MC tilt {info.sample_tilt_deg}")
            print(f"sha256: {info.sha256}")
            for c in info.checks:
                print(f"  ok: {c}")
            for w in info.warnings:
                print(f"  WARNING: {w}")
        return 0
    if a.master_cmd == "add":
        from .cache import ArtifactCache
        from .masters.cache import add_master

        p = add_master(ArtifactCache(a.cache), a.file)
        print(p)
        return 0
    return 2


def cmd_cif(a) -> int:
    from .crystal.cif import read_cif

    model = read_cif(Path(a.file))
    if a.cif_cmd == "validate":
        if a.json:
            _print_json(model.to_dict())
        else:
            for line in model.summary_lines():
                print(line)
            for c in model.checks:
                print(f"  ok: {c}")
            for w in model.warnings:
                print(f"  WARNING: {w}")
        return 0
    if a.cif_cmd == "xtal":
        from .crystal.xtal import write_xtal

        print(write_xtal(model, a.out))
        return 0
    return 2


def cmd_kinematical(a) -> int:
    from .crystal.cif import read_cif
    from .masters.kinematical import simulate_kinematical_master

    model = read_cif(Path(a.cif))
    p = simulate_kinematical_master(model, a.out, voltage_kV=a.kv, dmin_A=a.dmin, half_size=a.half_size,
                                    sample_tilt_deg=a.tilt)
    print(f"{p}  (KINEMATICAL master - synthetic fixtures only, not a dynamical EMsoft result)")
    return 0


def _progress_printer(quiet: bool):
    state = {"last": -1}

    def fn(f, msg):
        pct = int(100 * f)
        if not quiet and (pct != state["last"]) and (pct % 5 == 0 or pct == 100):
            state["last"] = pct
            print(f"[{pct:3d}%] {msg}", flush=True)

    return fn


def _summarise(job, result) -> None:
    print(f"\nJob folder: {job.path}")
    print(f"Counts: {result.decision.counts()}")
    for k, v in (result.manifest.outputs or {}).items():
        print(f"  {k}: {v}")
    for e in result.manifest.events:
        if e["kind"] in ("warning", "fallback", "batch_size_change", "pc_approximation"):
            print(f"  NOTE [{e['kind']}]: {e['message']}")


def cmd_index(a) -> int:
    from .pipeline import IndexingConfig, run_indexing_job

    cfg = IndexingConfig.from_file(a.config, preset=a.preset)
    if a.backend:
        cfg.matching["backend"] = a.backend
    job, result = run_indexing_job(cfg, a.jobs, listener=_progress_printer(a.quiet))
    _summarise(job, result)
    return 0


def cmd_presets(a) -> int:
    from .presets import PRESETS

    for name, p in PRESETS.items():
        print(f"{name:12s} {p['description']}")
    return 0


def cmd_demo(a) -> int:
    from .demo import run_demo

    job, result, report = run_demo(a.jobs, n_rows=a.rows, n_cols=a.cols, resolution_deg=a.resolution,
                                   backend=a.backend, listener=_progress_printer(a.quiet),
                                   two_phase=a.two_phase)
    _summarise(job, result)
    print("\nDemo check:")
    _print_json(report)
    return 0 if report["passed"] else 1


def cmd_emsoft(a) -> int:
    from .crystal.cif import read_cif
    from .emsoft.jobs import EMsoftInstall, EMsoftPreset, plan_master_job, run_master_job

    if a.emsoft_cmd == "check":
        inst = EMsoftInstall.discover()
        if inst is None:
            print("EMsoft not found. Set KWB_EMSOFT_BIN to the EMsoft bin folder.", file=sys.stderr)
            return 2
        _print_json(inst.check())
        return 0
    model = read_cif(Path(a.cif))
    preset = EMsoftPreset.named(a.preset)
    if a.kv:
        preset.voltage_kV = a.kv
    if a.tilt:
        preset.sample_tilt_deg = a.tilt
    if a.emsoft_cmd == "plan":
        plan = plan_master_job(model, preset, a.out)
        _print_json(plan.describe())
        return 0
    from .cache import ArtifactCache
    from .jobs import Job

    inst = EMsoftInstall.discover()
    if inst is None:
        print("EMsoft not found. Set KWB_EMSOFT_BIN to the EMsoft bin folder.", file=sys.stderr)
        return 2
    job = Job.create(a.jobs, "emsoft")
    job.add_listener(_progress_printer(False))
    plan = plan_master_job(model, preset, job.work)
    rec = job.run(lambda j: run_master_job(plan, inst, cache=ArtifactCache(a.cache), job=j))
    (job.outputs / "emsoft_record.json").write_text(json.dumps(rec, indent=2, default=str))
    print(f"Verified master cached at: {rec.get('cached_master')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kwb", description="KikuchiWorkbench headless runner")
    p.add_argument("--version", action="version", version=f"KikuchiWorkbench {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("inspect", help="inspect a scan file")
    s.add_argument("scan")
    s.add_argument("--nav-shape", type=int, nargs=2, metavar=("ROWS", "COLS"))
    s.add_argument("--step", type=float)
    s.add_argument("--grid-type", choices=["square", "hexagonal", "points"])
    s.add_argument("--companion", help="H5OINA providing geometry for a .ebsp file")
    s.add_argument("--processed", action="store_true", help="read processed instead of raw patterns")
    s.add_argument("--pc", type=float, nargs=3)
    s.add_argument("--pc-convention", default="bruker", choices=["bruker", "tsl", "oxford", "emsoft", "emsoft4"])
    s.add_argument("--binning", type=int)
    s.add_argument("--px-size", type=float)
    s.add_argument("--sample-tilt", type=float)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_inspect)

    m = sub.add_parser("master", help="EMsoft master patterns")
    msub = m.add_subparsers(dest="master_cmd", required=True)
    mi = msub.add_parser("inspect")
    mi.add_argument("file")
    mi.add_argument("--json", action="store_true")
    ma = msub.add_parser("add")
    ma.add_argument("file")
    ma.add_argument("--cache", default=None)
    m.set_defaults(fn=cmd_master)

    c = sub.add_parser("cif", help="crystal structures")
    csub = c.add_subparsers(dest="cif_cmd", required=True)
    cv = csub.add_parser("validate")
    cv.add_argument("file")
    cv.add_argument("--json", action="store_true")
    cx = csub.add_parser("xtal")
    cx.add_argument("file")
    cx.add_argument("out")
    c.set_defaults(fn=cmd_cif)

    k = sub.add_parser("kinematical", help="kinematical master from CIF (synthetic fixtures only)")
    k.add_argument("cif")
    k.add_argument("out")
    k.add_argument("--kv", type=float, default=20.0)
    k.add_argument("--dmin", type=float, default=0.8, help="minimum d-spacing (Å)")
    k.add_argument("--half-size", type=int, default=200)
    k.add_argument("--tilt", type=float, default=70.0)
    k.set_defaults(fn=cmd_kinematical)

    i = sub.add_parser("index", help="run dictionary indexing from a config file")
    i.add_argument("config")
    i.add_argument("--jobs", default="kwb_jobs")
    i.add_argument("--backend", choices=["auto", "cpu", "gpu"])
    i.add_argument("--preset", choices=["quick", "standard", "phase_study"],
                   help="base settings; values in the config file override them")
    i.add_argument("--quiet", action="store_true")
    i.set_defaults(fn=cmd_index)

    d = sub.add_parser("demo", help="offline CPU demo with the bundled Ni master")
    d.add_argument("--jobs", default="kwb_jobs")
    d.add_argument("--rows", type=int, default=6)
    d.add_argument("--cols", type=int, default=6)
    d.add_argument("--resolution", type=float, default=4.0)
    d.add_argument("--backend", default="cpu", choices=["auto", "cpu", "gpu"])
    d.add_argument("--two-phase", action="store_true",
                   help="add a kinematical Cu phase vs kinematical Ni (synthetic discrimination)")
    d.add_argument("--quiet", action="store_true")
    d.set_defaults(fn=cmd_demo)

    g = sub.add_parser("gui", help="start the desktop GUI")
    g.set_defaults(fn=lambda a: __import__("kikuchiworkbench.gui.main_window", fromlist=["main"]).main([]))

    pr = sub.add_parser("presets", help="list indexing presets")
    pr.set_defaults(fn=cmd_presets)

    e = sub.add_parser("emsoft", help="EMsoft simulation jobs")
    esub = e.add_subparsers(dest="emsoft_cmd", required=True)
    ep = esub.add_parser("plan", help="write EMsoft inputs for CIF -> MC -> master (no execution)")
    ep.add_argument("cif")
    ep.add_argument("out")
    ep.add_argument("--preset", default="quick")
    ep.add_argument("--kv", type=float)
    ep.add_argument("--tilt", type=float)
    er = esub.add_parser("run", help="run EMMCOpenCL + EMEBSDmaster in a job folder and cache the master")
    er.add_argument("cif")
    er.add_argument("--preset", default="quick")
    er.add_argument("--kv", type=float)
    er.add_argument("--tilt", type=float)
    er.add_argument("--jobs", default="kwb_jobs")
    er.add_argument("--cache", default=None)
    esub.add_parser("check", help="locate EMsoft executables")
    e.set_defaults(fn=cmd_emsoft)
    return p


def main(argv: list[str] | None = None) -> int:
    warnings.filterwarnings("ignore")
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except WorkbenchError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"ERROR: file not found: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
