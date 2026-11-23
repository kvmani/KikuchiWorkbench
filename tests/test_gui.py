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

    est = win.estimate()
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
