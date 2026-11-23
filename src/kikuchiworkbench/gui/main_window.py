"""Guided desktop workflow (PySide6) on top of the shared core.

Steps: 1 Scan · 2 Phases · 3 Masters · 4 Geometry · 5 Index · 6 Results.
Long operations (loading, master generation, indexing) run in worker threads
with progress, cancellation and a log panel.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..errors import WorkbenchError
from .images import to_pixmap
from .workers import Worker, start_worker

STEPS = ["1. Open a scan", "2. Candidate phases", "3. Masters", "4. Detector geometry",
         "5. Build & match", "6. Inspect & export"]


class ClickableLabel(QLabel):
    """QLabel reporting clicks in image-array coordinates."""

    def __init__(self, on_click=None):
        super().__init__()
        self.on_click = on_click
        self.array_shape = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, ev):  # noqa: N802 (Qt API)
        if self.on_click is None or self.array_shape is None or self.pixmap() is None:
            return
        pm = self.pixmap()
        off_x = (self.width() - pm.width()) / 2
        off_y = (self.height() - pm.height()) / 2
        x = (ev.position().x() - off_x) / pm.width() * self.array_shape[1]
        y = (ev.position().y() - off_y) / pm.height() * self.array_shape[0]
        if 0 <= x < self.array_shape[1] and 0 <= y < self.array_shape[0]:
            self.on_click(int(y), int(x))


class MainWindow(QMainWindow):
    def __init__(self, jobs_root: str | None = None):
        super().__init__()
        self.setWindowTitle(f"KikuchiWorkbench {__version__}")
        self.resize(1200, 800)
        self.jobs_root = Path(jobs_root or Path(tempfile.gettempdir()) / "kwb_gui_jobs")
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.scan = None
        self.scan_path: str | None = None
        self.phases: list[dict] = []  # {"name", "master", "info"}
        self.result = None
        self.current_job = None
        self.worker: Worker | None = None
        self.thread = None
        self.selected_point: int | None = None

        self.steps = QListWidget()
        self.steps.addItems(STEPS)
        self.steps.setMaximumWidth(220)
        self.stack = QStackedWidget()
        self.steps.currentRowChanged.connect(self.stack.setCurrentIndex)
        for build in (self._build_scan_page, self._build_phase_page, self._build_master_page,
                      self._build_geometry_page, self._build_index_page, self._build_results_page):
            self.stack.addWidget(build())

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.cancel_btn = QPushButton("Cancel job")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_job)
        self.status_label = QLabel("Ready")

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        row = QHBoxLayout()
        row.addWidget(self.status_label, 1)
        row.addWidget(self.progress, 2)
        row.addWidget(self.cancel_btn)
        bl.addLayout(row)
        bl.addWidget(self.log)

        top = QSplitter()
        top.addWidget(self.steps)
        top.addWidget(self.stack)
        top.setStretchFactor(1, 1)
        main = QSplitter(Qt.Orientation.Vertical)
        main.addWidget(top)
        main.addWidget(bottom)
        main.setStretchFactor(0, 4)
        self.setCentralWidget(main)
        self.steps.setCurrentRow(0)

        act = QAction("Open bundled example", self)
        act.triggered.connect(self.open_example)
        self.menuBar().addMenu("&File").addAction(act)
        self.append_log(f"KikuchiWorkbench {__version__}. Jobs folder: {self.jobs_root}")

    # ------------------------------------------------------------------ infra

    def append_log(self, msg: str) -> None:
        self.log.appendPlainText(msg)

    def busy(self) -> bool:
        return self.worker is not None

    def run_in_worker(self, fn, on_done, label: str, *args, **kwargs) -> Worker:
        if self.busy():
            raise WorkbenchError("Another job is running; wait or cancel it first.")
        self.worker = Worker(fn, *args, **kwargs)
        self._on_done_cb = on_done
        # Bound QObject slots (not lambdas) so Qt queues these calls into the GUI thread.
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText(label)
        self.progress.setValue(0)
        self.append_log(f"Started: {label}")
        self.thread = start_worker(self, self.worker)
        return self.worker

    @Slot(float, str)
    def _on_progress(self, f: float, msg: str) -> None:
        self.progress.setValue(int(1000 * f))
        if msg:
            self.status_label.setText(msg)

    def _done(self):
        self.worker = None
        self.cancel_btn.setEnabled(False)

    @Slot(object)
    def _on_finished(self, result):
        on_done = self._on_done_cb
        self._done()
        self.progress.setValue(1000)
        self.status_label.setText("Done")
        on_done(result)

    @Slot(str)
    def _on_failed(self, msg: str):
        self._done()
        self.status_label.setText("Failed")
        self.append_log("ERROR: " + msg)

    @Slot()
    def _on_cancelled(self):
        self._done()
        self.status_label.setText("Cancelled")
        self.append_log("Job cancelled; its outputs are marked INVALID and are not reused.")

    def cancel_job(self):
        if self.worker is not None:
            self.worker.cancel_token.cancel()
            if self.current_job is not None:
                self.current_job.cancel_token.cancel()
            self.append_log("Cancellation requested...")

    # ------------------------------------------------------------------ step 1: scan

    def _build_scan_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        b1 = QPushButton("Open scan…")
        b1.clicked.connect(self._choose_scan)
        b2 = QPushButton("Open bundled example")
        b2.clicked.connect(self.open_example)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        lay.addLayout(row)
        self.scan_info = QPlainTextEdit()
        self.scan_info.setReadOnly(True)
        lay.addWidget(self.scan_info, 1)
        pv = QHBoxLayout()
        self.map_preview = ClickableLabel(self._preview_point)
        self.raw_preview = QLabel("raw pattern")
        self.pre_preview = QLabel("preprocessed pattern")
        for lab, title in ((self.map_preview, "Map (mean intensity) — click a point"),
                           (self.raw_preview, "Raw pattern (read-only)"),
                           (self.pre_preview, "Preprocessed pattern")):
            box = QGroupBox(title)
            QVBoxLayout(box).addWidget(lab)
            pv.addWidget(box)
        lay.addLayout(pv, 2)
        return w

    def _choose_scan(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open EBSD scan", "",
            "EBSD scans (*.h5oina *.ebsp *.h5 *.oh5 *.up1 *.up2 *.hdf5);;All files (*)")
        if path:
            self.load_scan(path)

    def load_scan(self, path: str, **kwargs):
        from ..io.readers import load_scan

        def job(worker):
            worker.report(0.1, "Reading scan")
            return load_scan(path, **kwargs)

        def done(scan):
            self.set_scan(scan, path)

        return self.run_in_worker(job, done, f"Loading {Path(path).name}")

    def set_scan(self, scan, path: str | None = None):
        self.scan = scan
        self.scan_path = path
        s = scan.summary()
        lines = [f"File: {path}", f"Format: {s['file_format']} ({s['vendor']}), dataset {s['dataset_path']}",
                 "Grid: {grid_type} {nrows} x {ncols} = {n_points} points, step {step_x:.4g} x {step_y:.4g} "
                 "{unit}".format(**s["grid"]),
                 f"Patterns: {s['pattern_shape']} px, {s['dtype']}",
                 "PC (Bruker): ({:.4f}, {:.4f}, {:.4f}); binning {}; sample tilt {:.1f}°".format(
                     *s["detector"]["pc_bruker_mean"], s["detector"]["binning"],
                     s["detector"]["sample_tilt_deg"]),
                 f"Geometry source: {s['geometry_source']}"]
        lines += [f"WARNING: {w}" for w in s["warnings"]]
        self.scan_info.setPlainText("\n".join(lines))
        # mean-intensity map over all points (chunked; strided subsample for very large scans)
        step = max(1, scan.n_points // 200_000)
        mean = np.full(scan.n_points, np.nan)
        for i0 in range(0, scan.n_points, 8192 * step):
            i1 = min(scan.n_points, i0 + 8192 * step)
            chunk = scan.patterns[i0:i1:step]
            if hasattr(chunk, "compute"):
                chunk = chunk.compute()
            mean[i0:i1:step] = np.asarray(chunk, dtype=np.float32).mean(axis=(1, 2))
        img = scan.to_map(mean)
        self.map_preview.array_shape = img.shape
        self.map_preview.setPixmap(to_pixmap(img, 260))
        self._preview_point(0, 0)
        self._sync_geometry_fields()
        self.append_log(f"Loaded scan {path}: {scan.n_points} points")

    def _preview_point(self, r: int, c: int):
        if self.scan is None:
            return
        rr, cc = self.scan.map_indices()
        hit = np.nonzero((rr == r) & (cc == c))[0]
        if hit.size == 0:
            return
        i = int(hit[0])
        raw = self.scan.get_patterns(i, i + 1)
        self.raw_preview.setPixmap(to_pixmap(raw[0], 240))
        from ..indexing.preprocessing import DEFAULT_PIPELINE, Preprocessor

        pre = Preprocessor(list(DEFAULT_PIPELINE), self.scan.pattern_shape)
        if self.scan.n_points <= 2000:
            pre.fit(self.scan)
        else:
            pre.fit(self.scan, max_patterns=500)
        self.pre_preview.setPixmap(to_pixmap(pre.apply_experimental(raw)[0], 240))

    def open_example(self):
        """Create the offline example (synthetic Ni from the bundled EMsoft master) and load it."""
        from ..demo import bundled_ni_master
        from ..io.readers import write_fixture
        from ..masters.importer import load_master
        from ..synthetic import SyntheticSpec, make_synthetic_scan

        out = self.jobs_root / "example"
        out.mkdir(exist_ok=True)
        fx = out / "example_ni_scan.h5"
        mp = bundled_ni_master()
        if not fx.exists():
            m = load_master(mp, phase_name="Ni")
            scan, truth = make_synthetic_scan([m], SyntheticSpec(nrows=8, ncols=8))
            write_fixture(fx, scan, truth=truth, provenance={"example": "bundled Ni synthetic"})
        if not any(p["master"] == mp for p in self.phases):
            self.add_master(mp, "Ni")
        self.load_scan(str(fx))

    # ------------------------------------------------------------------ step 2: phases

    def _build_phase_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        b1 = QPushButton("Add EMsoft master…")
        b1.clicked.connect(self._choose_master)
        b2 = QPushButton("Validate CIF…")
        b2.clicked.connect(self._choose_cif)
        b3 = QPushButton("Remove selected")
        b3.clicked.connect(self._remove_phase)
        for b in (b1, b2, b3):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.phase_list = QListWidget()
        self.phase_list.currentRowChanged.connect(self._show_phase)
        lay.addWidget(self.phase_list, 1)
        self.phase_info = QPlainTextEdit()
        self.phase_info.setReadOnly(True)
        lay.addWidget(self.phase_info, 2)
        return w

    def _choose_master(self):
        path, _ = QFileDialog.getOpenFileName(self, "EMsoft master", "", "HDF5 (*.h5 *.hdf5)")
        if path:
            self.add_master(path)

    def add_master(self, path: str, name: str | None = None):
        from ..masters.importer import inspect_master
        from ..masters.kinematical import is_kinematical

        try:
            info = inspect_master(path)
        except WorkbenchError as e:
            self.append_log(f"Master rejected: {e}")
            QMessageBox.warning(self, "Master rejected", str(e)) if self.isVisible() else None
            return None
        name = name or info.phase_name
        self.phases.append({"name": name, "master": path, "info": info})
        tag = " [KINEMATICAL]" if is_kinematical(info.program) else ""
        self.phase_list.addItem(f"{name} — SG {info.space_group} ({info.point_group}){tag}")
        self.append_log(f"Added phase {name} from {path}")
        return info

    def _remove_phase(self):
        r = self.phase_list.currentRow()
        if r >= 0:
            self.phases.pop(r)
            self.phase_list.takeItem(r)

    def _show_phase(self, r: int):
        if r < 0 or r >= len(self.phases):
            return
        info = self.phases[r]["info"]
        lines = [f"Phase: {self.phases[r]['name']}", f"Master: {info.path}", f"sha256: {info.sha256}",
                 f"Space group {info.space_group}, point group {info.point_group}",
                 f"Lattice (nm, deg): {info.lattice_nm_deg}",
                 f"Energies (keV): {info.energies_keV}; npx {info.npx}; hemispheres {info.hemispheres}",
                 f"Program: {info.program} {info.emsoft_version or ''}; MC tilt {info.sample_tilt_deg}"]
        lines += [f"ok: {c}" for c in info.checks] + [f"WARNING: {w}" for w in info.warnings]
        self.phase_info.setPlainText("\n".join(lines))

    def _choose_cif(self):
        path, _ = QFileDialog.getOpenFileName(self, "CIF", "", "CIF (*.cif)")
        if path:
            self.validate_cif(path)

    def validate_cif(self, path: str):
        from ..crystal.cif import read_cif

        try:
            m = read_cif(Path(path))
        except WorkbenchError as e:
            self.phase_info.setPlainText(f"CIF rejected:\n{e}")
            self.append_log(f"CIF rejected: {e.message}")
            return None
        self.phase_info.setPlainText("\n".join(m.summary_lines() + [f"ok: {c}" for c in m.checks]
                                               + [f"WARNING: {w}" for w in m.warnings]))
        self.last_cif = path
        return m

    # ------------------------------------------------------------------ step 3: masters

    def _build_master_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.kv = QDoubleSpinBox()
        self.kv.setRange(5, 30)
        self.kv.setValue(20)
        self.kv.setSuffix(" kV")
        self.tilt = QDoubleSpinBox()
        self.tilt.setRange(0, 90)
        self.tilt.setValue(70)
        self.tilt.setSuffix(" °")
        self.preset = QComboBox()
        self.preset.addItems(["quick", "standard"])
        form.addRow("Beam voltage", self.kv)
        form.addRow("Specimen tilt", self.tilt)
        form.addRow("EMsoft preset", self.preset)
        lay.addLayout(form)
        row = QHBoxLayout()
        b1 = QPushButton("Generate with EMsoft (CIF → MC → master)")
        b1.clicked.connect(lambda: self._emsoft_from_cif())
        b2 = QPushButton("Kinematical master (synthetic only)")
        b2.clicked.connect(lambda: self._kinematical_from_cif())
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)
        self.master_status = QPlainTextEdit()
        self.master_status.setReadOnly(True)
        self.master_status.setPlainText(
            "Native EMsoft generation requires KWB_EMSOFT_BIN and an OpenCL device; it has not yet been "
            "validated on Windows (see docs/emsoft.md). Imported EMsoft masters are verified before use.")
        lay.addWidget(self.master_status, 1)
        return w

    def _need_cif(self):
        path = getattr(self, "last_cif", None)
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "CIF", "", "CIF (*.cif)")
        return path

    def _kinematical_from_cif(self, path: str | None = None):
        from ..crystal.cif import read_cif
        from ..masters.kinematical import simulate_kinematical_master

        path = path or self._need_cif()
        if not path:
            return None
        model = read_cif(Path(path))
        out = self.jobs_root / f"{model.name}_kinematical_{self.kv.value():g}kV.h5"

        def job(worker):
            worker.report(0.1, "Simulating kinematical master")
            return simulate_kinematical_master(model, out, voltage_kV=self.kv.value(),
                                               sample_tilt_deg=self.tilt.value(), half_size=150)

        return self.run_in_worker(job, lambda p: self.add_master(str(p), model.name),
                                  "Kinematical master")

    def _emsoft_from_cif(self):
        from ..cache import ArtifactCache
        from ..crystal.cif import read_cif
        from ..emsoft.jobs import EMsoftInstall, EMsoftPreset, plan_master_job, run_master_job
        from ..jobs import Job

        inst = EMsoftInstall.discover()
        if inst is None:
            self.master_status.setPlainText("EMsoft not found: set KWB_EMSOFT_BIN to the EMsoft bin folder.")
            return None
        path = self._need_cif()
        if not path:
            return None
        model = read_cif(Path(path))
        preset = EMsoftPreset.named(self.preset.currentText())
        preset.voltage_kV = self.kv.value()
        preset.sample_tilt_deg = self.tilt.value()
        job = Job.create(self.jobs_root, "emsoft")
        self.current_job = job

        def run(worker):
            job.add_listener(lambda f, m: worker.report(f, m))
            plan = plan_master_job(model, preset, job.work)
            return job.run(lambda j: run_master_job(plan, inst, cache=ArtifactCache(), job=j))

        return self.run_in_worker(run, lambda rec: self.add_master(rec["cached_master"], model.name),
                                  "EMsoft master generation")

    # ------------------------------------------------------------------ step 4: geometry

    def _build_geometry_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.pc = []
        for lab in ("PCx", "PCy", "PCz"):
            sb = QDoubleSpinBox()
            sb.setDecimals(4)
            sb.setRange(-2, 3)
            sb.setSingleStep(0.001)
            self.pc.append(sb)
            form.addRow(f"{lab} (Bruker convention)", sb)
        self.det_tilt = QDoubleSpinBox()
        self.det_tilt.setRange(-90, 90)
        form.addRow("Detector tilt (°)", self.det_tilt)
        self.binning = QSpinBox()
        self.binning.setRange(1, 64)
        form.addRow("Binning", self.binning)
        lay.addLayout(form)
        b = QPushButton("Apply geometry to scan (recorded as user geometry)")
        b.clicked.connect(self.apply_geometry)
        lay.addWidget(b)
        bc = QPushButton("Calibrate PC on the first phase (shared by all phases)")
        bc.clicked.connect(lambda: self.calibrate_geometry())
        lay.addWidget(bc)
        self.calib_label = QLabel("")
        self.calib_label.setWordWrap(True)
        lay.addWidget(self.calib_label)
        b2 = QPushButton("Compare experimental vs simulated (after indexing an ROI)")
        b2.clicked.connect(lambda: self.compare_geometry())
        lay.addWidget(b2)
        row = QHBoxLayout()
        self.geo_exp, self.geo_sim, self.geo_res = QLabel(), QLabel(), QLabel()
        for lab, t in ((self.geo_exp, "Experimental"), (self.geo_sim, "Simulated (best)"),
                       (self.geo_res, "Residual")):
            box = QGroupBox(t)
            QVBoxLayout(box).addWidget(lab)
            row.addWidget(box)
        lay.addLayout(row, 1)
        return w

    def _sync_geometry_fields(self):
        if self.scan is None:
            return
        d = self.scan.detector
        for sb, v in zip(self.pc, np.asarray(d.pc_average).ravel(), strict=True):
            sb.setValue(float(v))
        self.det_tilt.setValue(float(d.tilt))
        self.binning.setValue(int(d.binning))

    def calibrate_geometry(self, n_points: int = 9, resolution_deg: float = 4.0):
        """Run the shared PC calibration in a worker and apply the median PC to the scan."""
        if self.scan is None or not self.phases:
            self.append_log("Load a scan and at least one phase before calibrating.")
            return None
        from ..indexing.calibration import apply_calibration, calibrate_pc
        from ..indexing.preprocessing import DEFAULT_PIPELINE, Preprocessor
        from ..masters.importer import load_master

        self.apply_geometry()  # start from the values shown in the fields
        scan = self.scan
        ref = self.phases[0]

        def job(worker):
            worker.report(0.05, f"Calibrating PC with {ref['name']}")
            m = load_master(ref["master"], phase_name=ref["name"])
            pre = Preprocessor(list(DEFAULT_PIPELINE), scan.pattern_shape).fit(scan, max_patterns=500)
            return calibrate_pc(scan, m, pre, n_points=n_points, resolution_deg=resolution_deg)

        def done(cal):
            self.scan = apply_calibration(self.scan, cal)
            self._sync_geometry_fields()
            self.calib_label.setText(
                "Calibrated PC (Bruker) {} from {} points with {}; start {}; spread (std) {}".format(
                    [round(v, 4) for v in cal["pc_bruker"]], cal["n_used"], cal["reference_phase"],
                    [round(v, 4) for v in cal["pc_bruker_start"]], [round(v, 4) for v in cal["pc_spread_std"]]))
            self.append_log("PC calibration applied; it is shared by all phases and recorded in the scan metadata.")

        return self.run_in_worker(job, done, "PC calibration")

    def apply_geometry(self):
        if self.scan is None:
            return
        from kikuchipy.detectors import EBSDDetector

        d = self.scan.detector
        self.scan.detector = EBSDDetector(shape=d.shape, pc=[sb.value() for sb in self.pc],
                                          binning=self.binning.value(), px_size=d.px_size,
                                          tilt=self.det_tilt.value(), azimuthal=d.azimuthal, twist=d.twist,
                                          sample_tilt=d.sample_tilt)
        self.scan.geometry_source = "user"
        self.scan.metadata["user_geometry"] = {"pc": [sb.value() for sb in self.pc], "pc_convention": "bruker",
                                               "tilt": self.det_tilt.value(), "binning": self.binning.value()}
        self.append_log(f"Geometry applied: PC {[round(sb.value(), 4) for sb in self.pc]} (Bruker)")

    def compare_geometry(self, i: int | None = None):
        if self.result is None:
            self.append_log("Index an ROI first (step 5) to compare experimental and simulated patterns.")
            return
        if i is None:
            i = self.selected_point or 0
        p = int(self.result.decision.best_phase_any[i])
        exp = self.result.measured_pattern(i)
        sim = self.result.simulated_pattern(i, p)
        self.geo_exp.setPixmap(to_pixmap(exp, 220))
        if sim is not None:
            self.geo_sim.setPixmap(to_pixmap(sim, 220))
            z = lambda a: (a - a.mean()) / (a.std() + 1e-9)  # noqa: E731
            self.geo_res.setPixmap(to_pixmap(z(exp) - z(sim), 220))

    # ------------------------------------------------------------------ step 5: index

    def _build_index_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.resolution = QDoubleSpinBox()
        self.resolution.setRange(0.5, 15)
        self.resolution.setValue(4.0)
        self.resolution.setSuffix(" °")
        self.backend = QComboBox()
        self.backend.addItems(["auto", "cpu", "gpu"])
        self.min_score = QDoubleSpinBox()
        self.min_score.setDecimals(3)
        self.min_score.setRange(0, 1)
        self.min_score.setValue(0.10)
        self.amb_margin = QDoubleSpinBox()
        self.amb_margin.setDecimals(4)
        self.amb_margin.setRange(0, 0.5)
        self.amb_margin.setSingleStep(0.001)
        self.amb_margin.setValue(0.005)
        self.preset = QComboBox()
        self.preset.addItems(["(custom)", "quick", "standard", "phase_study"])
        self.preset.currentTextChanged.connect(self.apply_preset)
        self.preset_label = QLabel("")
        self.preset_label.setWordWrap(True)
        self.use_roi = QCheckBox("Index a region of interest only")
        roi_row = QHBoxLayout()
        self.roi_spins = []
        for lab, val in (("rows", 0), ("to", 4), ("cols", 0), ("to", 4)):
            sb = QSpinBox()
            sb.setRange(0, 100000)
            sb.setValue(val)
            roi_row.addWidget(QLabel(lab))
            roi_row.addWidget(sb)
            self.roi_spins.append(sb)
        roi_row.addStretch(1)
        self.bin2 = QCheckBox("Bin patterns ×2 (faster)")
        self.refine = QCheckBox("Refine orientations (equal budget per phase)")
        self.cache_dict = QCheckBox("Cache dictionaries")
        form.addRow("Preset", self.preset)
        form.addRow(self.preset_label)
        form.addRow("Angular resolution", self.resolution)
        form.addRow("Compute device", self.backend)
        form.addRow("Unindexed below NCC", self.min_score)
        form.addRow("Ambiguous at margin ≤", self.amb_margin)
        form.addRow(self.use_roi)
        form.addRow("ROI (half-open)", roi_row)
        form.addRow(self.bin2)
        form.addRow(self.refine)
        form.addRow(self.cache_dict)
        lay.addLayout(form)
        self.estimate_label = QLabel("")
        lay.addWidget(self.estimate_label)
        row = QHBoxLayout()
        be = QPushButton("Estimate resources")
        be.clicked.connect(self.estimate)
        br = QPushButton("Run indexing")
        br.clicked.connect(self.run_indexing)
        row.addWidget(be)
        row.addWidget(br)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def apply_preset(self, name: str):
        """Set the step-5 widgets from a preset; widgets stay editable afterwards."""
        from ..presets import PRESETS

        if name not in PRESETS:
            self.preset_label.setText("")
            return
        p = PRESETS[name]
        self.resolution.setValue(p["sampling"]["resolution_deg"])
        self.bin2.setChecked(any(st["op"] == "bin" for st in p["preprocessing"]))
        self.refine.setChecked(bool(p["refinement"].get("enabled")))
        self.cache_dict.setChecked(bool(p["matching"].get("cache_dictionary")))
        note = p["description"]
        if p["calibration"].get("enabled"):
            note += " Run the PC calibration in step 4 first."
        self.preset_label.setText(note)
        self.append_log(f"Preset applied: {name}")

    def _config(self):
        from ..indexing.preprocessing import DEFAULT_PIPELINE
        from ..pipeline import IndexingConfig, PhaseSpec

        pre = [dict(s) for s in DEFAULT_PIPELINE]
        if self.bin2.isChecked():
            pre.append({"op": "bin", "factor": 2})
        return IndexingConfig(
            scan={"path": self.scan_path or "<memory>"},
            phases=[PhaseSpec(master=p["master"], name=p["name"]) for p in self.phases],
            sampling={"resolution_deg": self.resolution.value()},
            preprocessing=pre,
            matching={"backend": self.backend.currentText(), "cache_dictionary": self.cache_dict.isChecked()},
            refinement={"enabled": True} if self.refine.isChecked() else {},
            decision={"min_score": self.min_score.value(), "ambiguity_margin": self.amb_margin.value(),
                      "provenance": "user-set in GUI"},
            roi=[sb.value() for sb in self.roi_spins] if self.use_roi.isChecked() else None,
        )

    def estimate(self):
        from orix.crystal_map import Phase

        if self.scan is None or not self.phases:
            self.estimate_label.setText("Load a scan and at least one phase first.")
            return None
        from ..presets import launch_check

        pgs = {p["name"]: Phase(space_group=p["info"].space_group).point_group for p in self.phases}
        n = self.scan.n_points
        if self.use_roi.isChecked():
            r0, r1, c0, c1 = (sb.value() for sb in self.roi_spins)
            n = max(0, r1 - r0) * max(0, c1 - c0)
        px = int(np.prod(self.scan.pattern_shape)) // (4 if self.bin2.isChecked() else 1)
        chk = launch_check(n, px, pgs, self.resolution.value(), refine=self.refine.isChecked(),
                           cached=False)
        d = chk.to_dict()
        d["n_orientations"] = chk.n_orientations
        text = "Estimate: " + chk.summary()
        if chk.warnings:
            text += "\nWARNING: " + "\nWARNING: ".join(chk.warnings)
        self.estimate_label.setText(text)
        return d

    def run_indexing(self):
        from ..jobs import Job
        from ..masters.importer import load_master
        from ..pipeline import run_indexing

        if self.scan is None or not self.phases:
            self.append_log("Load a scan and at least one phase before indexing.")
            return None
        cfg = self._config()
        if self.scan.geometry_source.startswith("missing"):
            self.append_log("The scan has no calibrated PC; set it in step 4 before indexing.")
            return None
        job = Job.create(self.jobs_root, "indexing")
        self.current_job = job
        (job.path / "config.json").write_text(json.dumps(cfg.to_dict(), indent=2, default=str))
        scan = self.scan

        def work(worker):
            job.add_listener(lambda f, m: worker.report(f, m))
            masters = [load_master(p["master"], phase_name=p["name"]) for p in self.phases]
            return job.run(lambda j: run_indexing(cfg, job=j, scan=scan, masters=masters))

        return self.run_in_worker(work, self.show_result, "Indexing")

    # ------------------------------------------------------------------ step 6: results

    def _build_results_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.map_kind = QComboBox()
        self.map_kind.addItems(["Phase", "IPF-Z", "Best score", "Phase margin", "Signal"])
        self.map_kind.currentIndexChanged.connect(self.refresh_map)
        row.addWidget(QLabel("Map:"))
        row.addWidget(self.map_kind)
        self.report_margin = QDoubleSpinBox()
        self.report_margin.setDecimals(4)
        self.report_margin.setRange(0, 0.5)
        self.report_margin.setSingleStep(0.001)
        self.report_margin.setValue(0.005)
        self.report_margin.valueChanged.connect(self.apply_reporting_threshold)
        row.addWidget(QLabel("Ambiguity margin:"))
        row.addWidget(self.report_margin)
        bexp = QPushButton("Export…")
        bexp.clicked.connect(lambda: self.export_results())
        row.addWidget(bexp)
        row.addStretch(1)
        lay.addLayout(row)
        self.counts_label = QLabel("")
        lay.addWidget(self.counts_label)
        body = QHBoxLayout()
        self.result_map = ClickableLabel(self.select_point)
        body.addWidget(self.result_map, 2)
        right = QVBoxLayout()
        self.cand_table = QTableWidget(0, 4)
        self.cand_table.setHorizontalHeaderLabels(["Phase", "Rank", "NCC", "Euler (°)"])
        right.addWidget(self.cand_table, 1)
        pats = QHBoxLayout()
        self.pat_measured = QLabel("")
        box = QGroupBox("Measured (preprocessed)")
        QVBoxLayout(box).addWidget(self.pat_measured)
        pats.addWidget(box)
        self.pat_sims: list[QLabel] = []
        self.pat_row = pats
        right.addLayout(pats, 1)
        body.addLayout(right, 3)
        lay.addLayout(body, 1)
        return w

    def show_result(self, result):
        self.result = result
        self.append_log(f"Indexing finished: {result.decision.counts()} (job {result.job_dir})")
        for e in result.manifest.events:
            self.append_log(f"  [{e['kind']}] {e['message']}")
        self.report_margin.setValue(float(result.manifest.thresholds.get("ambiguity_margin", 0.005)))
        for box in getattr(self, "pat_boxes", []):
            box.deleteLater()
        self.pat_sims, self.pat_boxes = [], []
        for name in result.phase_names:
            lab = QLabel("")
            box = QGroupBox(f"{name}: best simulation")
            QVBoxLayout(box).addWidget(lab)
            self.pat_sims.append(lab)
            self.pat_boxes.append(box)
            self.pat_row.addWidget(box)
        self.refresh_map()
        self.steps.setCurrentRow(5)

    def _map_array(self):
        from ..export import ipf_rgb, phase_rgb

        r = self.result
        scan = r.context["scan"]
        kind = self.map_kind.currentText()
        if kind == "Phase":
            return scan.to_map(phase_rgb(r), fill=1.0)
        if kind == "IPF-Z":
            return scan.to_map(ipf_rgb(r), fill=1.0)
        if kind == "Best score":
            return scan.to_map(r.decision.best_score)
        if kind == "Phase margin":
            return scan.to_map(np.nan_to_num(r.decision.margin, nan=0.0))
        return scan.to_map(r.signal)

    def refresh_map(self):
        if self.result is None:
            return
        img = self._map_array()
        self.result_map.array_shape = img.shape[:2]
        self.result_map.setPixmap(to_pixmap(img, 420))
        self.counts_label.setText(f"Counts: {self.result.decision.counts()}  "
                                  "(phase margin is a ranking diagnostic, not a probability)")

    def apply_reporting_threshold(self, value: float):
        if self.result is None:
            return
        from ..indexing.decision import DecisionPolicy

        t = dict(self.result.manifest.thresholds)
        t["ambiguity_margin"] = float(value)
        t["provenance"] = "user-adjusted reporting threshold in GUI"
        self.result.redecide(DecisionPolicy(**t))
        self.refresh_map()

    def select_point(self, r: int, c: int):
        if self.result is None:
            return
        scan = self.result.context["scan"]
        rr, cc = scan.map_indices()
        hit = np.nonzero((rr == r) & (cc == c))[0]
        if hit.size == 0:
            return
        i = int(hit[0])
        self.selected_point = i
        cands = self.result.candidates(i)
        self.cand_table.setRowCount(len(cands))
        for k, cd in enumerate(cands):
            vals = [cd["phase"], str(cd["rank"] + 1), f"{cd['score']:.4f}",
                    ", ".join(f"{v:.1f}" for v in cd["euler_deg"])]
            for j, v in enumerate(vals):
                self.cand_table.setItem(k, j, QTableWidgetItem(v))
        self.cand_table.resizeColumnsToContents()
        self.pat_measured.setPixmap(to_pixmap(self.result.measured_pattern(i), 180))
        for p, lab in enumerate(self.pat_sims):
            sim = self.result.simulated_pattern(i, p)
            if sim is not None:
                lab.setPixmap(to_pixmap(sim, 180))
                lab.setToolTip(f"{self.result.phase_names[p]} best match, NCC "
                               f"{self.result.per_phase_best[i, p]:.4f}")
        d = self.result.decision
        from ..indexing.decision import LABEL_NAMES

        self.status_label.setText(
            f"Point {i} (row {r}, col {c}): {LABEL_NAMES[int(d.label[i])]}, best NCC {d.best_score[i]:.4f}, "
            f"phase margin {'n/a (single phase)' if np.isnan(d.margin[i]) else f'{d.margin[i]:.4f}'}, "
            f"signal {self.result.signal[i]:.2f}")

    def export_results(self, out_dir: str | None = None):
        from ..export import export_csv, export_h5, export_maps

        if self.result is None:
            return None
        if not out_dir:
            out_dir = QFileDialog.getExistingDirectory(self, "Export folder")
            if not out_dir:
                return None
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        scan = self.result.context["scan"]
        files = export_maps(self.result, scan, out)
        files["table_csv"] = export_csv(self.result, scan, out / "results.csv")
        files["results_h5"] = export_h5(self.result, scan, out / "results.h5")
        man = self.result.manifest
        man.outputs = files
        man.log_event("export", f"GUI export to {out}")
        man.write(out / "manifest.json")
        self.append_log(f"Exported results to {out}")
        return files


def main(argv=None) -> int:
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    w = MainWindow()
    w.show()
    return app.exec()
