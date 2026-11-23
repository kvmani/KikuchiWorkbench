"""Offscreen GUI smoke test: load example, index, inspect a pixel, change threshold, export."""

import os
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kikuchiworkbench.gui.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_idle(app, win, timeout=120):
    t0 = time.time()
    while win.busy():
        app.processEvents()
        time.sleep(0.01)
        if time.time() - t0 > timeout:
            raise TimeoutError("worker did not finish")
    for _ in range(20):
        app.processEvents()


def test_gui_workflow(app, tmp_path):
    win = MainWindow(jobs_root=str(tmp_path))
    win.show()
    win.open_example()
    assert win.busy()  # loading happens in a worker thread
    wait_idle(app, win)
    assert win.scan is not None and win.scan.n_points == 64
    assert len(win.phases) == 1 and "Geometry source: file" in win.scan_info.toPlainText()
    assert win.raw_preview.pixmap() is not None and not win.raw_preview.pixmap().isNull()

    win.preset.setCurrentText("phase_study")
    assert win.refine.isChecked() and win.bin2.isChecked() and win.resolution.value() == 2.5
    win.preset.setCurrentText("quick")
    assert not win.refine.isChecked() and win.resolution.value() == 5.0
    win.bin2.setChecked(False)
    est = win.estimate()
    assert "Estimate:" in win.estimate_label.text()
    assert est["n_orientations"]["Ni"] > 0
    win.resolution.setValue(6.0)
    win.use_roi.setChecked(True)
    win.backend.setCurrentText("cpu")
    win.run_indexing()
    wait_idle(app, win)
    r = win.result
    assert r is not None and r.n_points == 16
    assert r.decision.counts()["indexed"] >= 14
    assert win.stack.currentIndex() == 5

    win.select_point(1, 2)
    assert win.cand_table.rowCount() >= 1
    assert win.pat_measured.pixmap() is not None
    assert win.pat_sims[0].pixmap() is not None and not win.pat_sims[0].pixmap().isNull()
    for k in range(win.map_kind.count()):
        win.map_kind.setCurrentIndex(k)
    win.report_margin.setValue(0.2)  # single phase: margin is NaN so labels stay
    files = win.export_results(str(tmp_path / "export"))
    assert os.path.exists(files["table_csv"]) and (tmp_path / "export" / "manifest.json").exists()
    win.select_point(1, 2)
    fit0 = win.wizard_from_result()
    # the wizard reproduces the indexing score (background estimated on the full scan, so not exact)
    assert win.wizard["n_bands"] > 3
    assert abs(fit0 - float(r.decision.best_score[win.selected_point])) < 0.05
    win.pc[0].setValue(win.pc[0].value() + 0.03)  # live update via debounced timer
    t0 = time.time()
    while time.time() - t0 < 5 and win.wizard.get("last_fit") == fit0:
        app.processEvents()
        time.sleep(0.05)
    assert win.wizard["last_fit"] < fit0
    win.pc[0].setValue(win.pc[0].value() - 0.03)
    files = win.make_report()
    assert os.path.exists(files["html"])
    win.compare_geometry(0)
    assert win.geo_res.pixmap() is not None
    win.calibrate_geometry(n_points=4, resolution_deg=6.0)
    wait_idle(app, win)
    assert win.scan.geometry_source == "calibrated" and "Calibrated PC" in win.calib_label.text()
    win.close()


def test_gui_cancel_and_cif(app, tmp_path):
    win = MainWindow(jobs_root=str(tmp_path))
    win.open_example()
    wait_idle(app, win)
    win.resolution.setValue(3.0)
    win.backend.setCurrentText("cpu")
    win.run_indexing()
    win.cancel_job()
    wait_idle(app, win)
    assert win.result is None
    assert "cancel" in win.status_label.text().lower() or "Cancelled" in win.log.toPlainText()
    here = os.path.dirname(__file__)
    assert win.validate_cif(os.path.join(here, "data", "cif", "bad_mixed_site.cif")) is None
    assert "rejected" in win.phase_info.toPlainText()
    assert win.validate_cif(os.path.join(here, "data", "cif", "cu.cif")) is not None
    win.close()


def test_gui_project_save_and_reopen(app, tmp_path):
    win = MainWindow(jobs_root=str(tmp_path))
    win.open_example()
    wait_idle(app, win)
    win.pc[0].setValue(0.43)
    win.apply_geometry()
    win.resolution.setValue(6.0)
    win.refine.setChecked(True)
    win.use_roi.setChecked(True)
    p = win.save_project(str(tmp_path / "proj" / "example.kwbproj"))
    assert p.exists()
    win.close()
    win2 = MainWindow(jobs_root=str(tmp_path))
    win2.open_project(str(p))
    wait_idle(app, win2)
    assert win2.scan is not None and len(win2.phases) == 1
    assert win2.resolution.value() == 6.0 and win2.refine.isChecked() and win2.use_roi.isChecked()
    assert abs(win2.scan.detector.pc_average.ravel()[0] - 0.43) < 1e-6
    win2.run_indexing()
    wait_idle(app, win2)
    assert len(win2.project.runs) == 1  # run recorded and project auto-saved
    from kikuchiworkbench.project import Project

    assert len(Project.load(p).runs) == 1
    win2.close()


def test_gui_drag_roi(app, tmp_path):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    win = MainWindow(jobs_root=str(tmp_path))
    win.resize(1400, 900)
    win.show()
    win.open_example()
    wait_idle(app, win)
    lab = win.map_preview
    pm = lab.pixmap()
    ox, oy = (lab.width() - pm.width()) / 2, (lab.height() - pm.height()) / 2
    cell = pm.width() / 8  # 8 x 8 example map

    def ev(kind, x, y):
        p = QPointF(ox + x * cell, oy + y * cell)
        return QMouseEvent(kind, p, p, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    lab.mousePressEvent(ev(QMouseEvent.Type.MouseButtonPress, 1.2, 2.2))
    lab.mouseMoveEvent(ev(QMouseEvent.Type.MouseMove, 4.5, 6.5))
    lab.mouseReleaseEvent(ev(QMouseEvent.Type.MouseButtonRelease, 4.5, 6.5))
    assert win.use_roi.isChecked()
    assert [sb.value() for sb in win.roi_spins] == [2, 7, 1, 5]
    # a plain click does not change the ROI
    lab.mousePressEvent(ev(QMouseEvent.Type.MouseButtonPress, 0.5, 0.5))
    lab.mouseReleaseEvent(ev(QMouseEvent.Type.MouseButtonRelease, 0.5, 0.5))
    assert [sb.value() for sb in win.roi_spins] == [2, 7, 1, 5]
    win.backend.setCurrentText("cpu")
    win.resolution.setValue(6.0)
    win.run_indexing()
    wait_idle(app, win)
    assert win.result.n_points == 20 and win.result.context["roi_origin"] == (2, 1)
    win.close()


def test_gui_phase_library(app, tmp_path, kp_data_dir):
    from kikuchiworkbench.library import PhaseLibrary

    mp = os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")
    PhaseLibrary(tmp_path / "cache").add(mp, name="NiLib")
    win = MainWindow(jobs_root=str(tmp_path))
    dlg = win.open_library(str(tmp_path / "cache"), show=False)
    assert dlg.table.rowCount() == 1
    dlg.search.setText("zz")
    assert dlg.table.rowCount() == 0
    dlg.search.setText("ni")
    dlg.table.selectRow(0)
    dlg.add_selected()
    assert [p["name"] for p in win.phases] == ["NiLib"]
    win.close()


def test_gui_batch_panel(app, tmp_path, kp_data_dir):
    import yaml

    from kikuchiworkbench.io.readers import write_fixture
    from kikuchiworkbench.masters.importer import load_master
    from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan

    mp = os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")
    scan, truth = make_synthetic_scan([load_master(mp)], SyntheticSpec(nrows=2, ncols=2))
    fx = write_fixture(tmp_path / "s.h5", scan, truth)
    cfg = tmp_path / "c.yaml"
    cfg.write_text(yaml.safe_dump({"scan": str(fx), "phases": [mp], "sampling": {"resolution_deg": 6}}))
    win = MainWindow(jobs_root=str(tmp_path / "jobs"))
    dlg = win.open_batch(show=False)
    dlg.add_path(str(cfg))
    dlg.add_path(str(cfg))
    assert dlg.table.rowCount() == 2
    dlg.run()
    wait_idle(app, win)
    items = dlg.refresh()
    assert [it.status for it in items] == ["completed", "completed"]
    win.close()
