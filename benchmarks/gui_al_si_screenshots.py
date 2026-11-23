"""Drive the desktop GUI on the public Al-Si data and save screenshots of each workflow step.

    QT_QPA_PLATFORM=offscreen python benchmarks/gui_al_si_screenshots.py --data ~/kwb_data --out ~/kwb_review_artifacts/review
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

from PySide6.QtWidgets import QApplication


def wait_idle(app, win, timeout=3600):
    t0 = time.time()
    while win.busy():
        app.processEvents()
        time.sleep(0.02)
        if time.time() - t0 > timeout:
            raise TimeoutError
    for _ in range(30):
        app.processEvents()


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Path.home() / "kwb_data"))
    ap.add_argument("--out", default=str(Path.home() / "kwb_review_artifacts" / "review"),
                    help="artifact folder OUTSIDE the repository (no binaries in Git)")
    ap.add_argument("--jobs", default="kwb_gui_jobs")
    ap.add_argument("--roi", type=int, nargs=4, default=[90, 140, 90, 150])
    a = ap.parse_args()
    d = Path(a.data).expanduser()
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    from kikuchiworkbench.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(jobs_root=a.jobs)
    win.resize(1500, 950)
    win.show()

    def shot(name):
        for _ in range(30):
            app.processEvents()
        win.grab().save(str(out / f"gui_{name}.png"))
        print("saved", name, flush=True)

    scan = d / "al_si/x/al10si_oxford/260d272e-5d2a-4adc-b195-f3230f03ee22.ebsp"
    win.add_master(str(d / "al_master/al_mc_mp_20kv.h5"), "Al")
    win.add_master(str(d / "si_master/si_mc_mp_20kv.h5"), "Si")
    win.steps.setCurrentRow(0)
    win.load_scan(str(scan))
    wait_idle(app, win)
    win._preview_point(120, 100)
    shot("1_scan")

    win.steps.setCurrentRow(1)
    win.phase_list.setCurrentRow(1)
    shot("2_phases")
    win.steps.setCurrentRow(2)
    shot("3_masters")

    win.steps.setCurrentRow(3)
    for sb, v in zip(win.pc, (0.50, 0.15, 1.25)):
        sb.setValue(v)
    win.det_tilt.setValue(5.0)
    win.apply_geometry()
    win.calibrate_geometry(n_points=12, resolution_deg=4.0)
    wait_idle(app, win)
    shot("4_geometry_calibrated")

    win.steps.setCurrentRow(4)
    win.resolution.setValue(2.5)
    win.backend.setCurrentText("cpu")
    win.use_roi.setChecked(True)
    for sb, v in zip(win.roi_spins, a.roi):
        sb.setValue(v)
    win.bin2.setChecked(True)
    win.refine.setChecked(True)
    win.cache_dict.setChecked(True)
    win.estimate()
    shot("5_index_settings")
    t0 = time.time()
    win.run_indexing()
    wait_idle(app, win)
    elapsed = time.time() - t0
    r = win.result
    if r is None:
        print(win.log.toPlainText()[-3000:])
        raise SystemExit("indexing failed")

    for kind, name in (("Phase", "6a_phase_map"), ("IPF-Z", "6b_ipf_map"), ("Best score", "6c_score_map"),
                       ("Phase margin", "6d_margin_map")):
        win.map_kind.setCurrentText(kind)
        if kind == "Phase":
            win.select_point(5, 5)
        shot(name)
    # inspect one Si and one Al pixel
    rr, cc = r.context["scan"].map_indices()
    si = [i for i in range(r.n_points) if r.decision.phase[i] == 1]
    al = [i for i in range(r.n_points) if r.decision.phase[i] == 0]
    win.map_kind.setCurrentText("Phase")
    win.select_point(int(rr[si[len(si) // 2]]), int(cc[si[len(si) // 2]]))
    shot("6e_inspect_si_pixel")
    win.select_point(int(rr[al[len(al) // 2]]), int(cc[al[len(al) // 2]]))
    shot("6f_inspect_al_pixel")
    win.steps.setCurrentRow(3)
    win.compare_geometry(al[len(al) // 2])
    shot("4b_geometry_compare")
    files = win.export_results(str(out / "export"))
    summary = {"counts": r.decision.counts(), "n_points": r.n_points, "gui_wall_time_s": round(elapsed, 1),
               "timings": r.timings, "phase_names": r.phase_names,
               "pc_calibrated": win.scan.metadata.get("pc_calibration", {}).get("pc_bruker"),
               "events": [e["message"] for e in r.manifest.events], "exports": files}
    (out / "gui_run_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: summary[k] for k in ("counts", "gui_wall_time_s", "pc_calibrated")}, indent=2))
    win.close()


if __name__ == "__main__":
    main()
