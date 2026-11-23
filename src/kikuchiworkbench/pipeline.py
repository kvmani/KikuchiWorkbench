"""End-to-end indexing workflow shared by the CLI and the GUI.

load scan -> load/verify masters -> preprocess -> sample orientations per phase
-> project dictionary in bounded chunks -> NCC match (top-k per phase)
-> phase decision -> export maps/CSV/HDF5 + manifest.
"""

from __future__ import annotations

import copy
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import __version__
from .cache import make_key
from .errors import MissingMetadataError, WorkbenchError
from .export import export_csv, export_h5, export_maps
from .indexing.decision import DecisionPolicy, PhaseDecision, decide
from .indexing.dictionary import (
    DictionaryProjector,
    detector_key_fields,
    dictionary_cache_fields,
    get_or_build_dictionary,
    single_pc_detector,
)
from .indexing.matching import Matcher, TopK, normalize, select_backend
from .indexing.preprocessing import DEFAULT_PIPELINE, Preprocessor, signal_metric
from .indexing.sampling import SamplingSpec, estimate_count, estimate_resources, sample_orientations
from .io.readers import load_scan
from .io.scan import GEOMETRY_MISSING, ScanData
from .jobs import Job
from .manifest import RunManifest
from .masters.importer import LoadedMaster, load_master
from .masters.kinematical import is_kinematical

# --------------------------------------------------------------------------- config


@dataclass
class PhaseSpec:
    master: str
    name: str | None = None
    energy: str | float = "max"


@dataclass
class IndexingConfig:
    scan: dict
    phases: list[PhaseSpec]
    sampling: dict = field(default_factory=lambda: {"resolution_deg": 3.0})
    preprocessing: list = field(default_factory=lambda: copy.deepcopy(DEFAULT_PIPELINE))
    matching: dict = field(default_factory=dict)
    decision: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    roi: list | None = None  # [row0, row1, col0, col1] (half-open) on the map grid
    allow_placeholder_geometry: bool = False

    @classmethod
    def from_dict(cls, d: dict, base_dir: str | os.PathLike | None = None) -> IndexingConfig:
        d = copy.deepcopy(d)
        base = Path(base_dir) if base_dir else None

        def resolve(p):
            if p is None or base is None:
                return p
            q = Path(p)
            return str(q if q.is_absolute() else (base / q))

        scan = d.pop("scan")
        if isinstance(scan, str):
            scan = {"path": scan}
        scan["path"] = resolve(scan["path"])
        if scan.get("companion"):
            scan["companion"] = resolve(scan["companion"])
        phases = []
        for ph in d.pop("phases"):
            if isinstance(ph, str):
                ph = {"master": ph}
            ph["master"] = resolve(ph["master"])
            phases.append(PhaseSpec(**ph))
        out = d.get("output", {})
        if out.get("dir"):
            out["dir"] = resolve(out["dir"])
        return cls(scan=scan, phases=phases, **d)

    @classmethod
    def from_file(cls, path: str | os.PathLike) -> IndexingConfig:
        p = Path(path)
        text = p.read_text()
        if p.suffix.lower() in (".yaml", ".yml"):
            import yaml

            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        return cls.from_dict(data, base_dir=p.parent)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


MATCHING_DEFAULTS = {"backend": "auto", "top_k": 5, "dictionary_chunk": 2000, "pattern_chunk": 2048}


# --------------------------------------------------------------------------- result


@dataclass
class IndexingResult:
    phase_names: list[str]
    phases: list  # orix Phase objects
    decision: PhaseDecision
    per_phase_best: np.ndarray  # (N, n_phases)
    topk_scores: list[np.ndarray]
    topk_index: list[np.ndarray]
    topk_quaternion: list[np.ndarray]  # (N, k, 4)
    n_dictionary: list[int]
    signal: np.ndarray
    point_index: np.ndarray  # indices into the full scan (ROI support)
    manifest: RunManifest | None = None
    job_dir: str | None = None
    timings: dict = field(default_factory=dict)

    context: dict = field(default_factory=dict, repr=False)  # in-memory only (not exported)

    @property
    def n_points(self) -> int:
        return int(self.per_phase_best.shape[0])

    def redecide(self, policy: DecisionPolicy) -> PhaseDecision:
        """Re-apply a decision policy (e.g. a new reporting threshold) without re-matching."""
        valid = self.context["scan"].valid if "scan" in self.context else None
        self.decision = decide(self.per_phase_best, policy, signal=self.signal, valid=valid)
        if self.manifest is not None:
            self.manifest.thresholds = policy.to_dict()
            self.manifest.results["counts"] = self.decision.counts()
        return self.decision

    def measured_pattern(self, i: int, preprocessed: bool = True) -> np.ndarray:
        scan = self.context["scan"]
        raw = scan.get_patterns(i, i + 1)
        if not preprocessed:
            return raw[0]
        return self.context["preprocessor"].apply_experimental(raw)[0]

    def simulated_pattern(self, i: int, phase: int, rank: int = 0) -> np.ndarray | None:
        """Best (or rank-th) simulated pattern of ``phase`` for point ``i``."""
        from orix.quaternion import Rotation

        q = self.topk_quaternion[phase][i, rank]
        if not np.all(np.isfinite(q)):
            return None
        proj = DictionaryProjector(self.context["masters"][phase].signal, self.context["detector"],
                                   self.context["preprocessor"])
        return proj.project(Rotation(q[None]), normalise=False)[0]

    def candidates(self, i: int) -> list[dict]:
        from orix.quaternion import Rotation

        out = []
        eul = [np.rad2deg(Rotation(q[i]).to_euler()) for q in self.topk_quaternion]
        for p, name in enumerate(self.phase_names):
            for r in range(self.topk_scores[p].shape[1]):
                s = float(self.topk_scores[p][i, r])
                if not np.isfinite(s):
                    continue
                out.append({"phase": name, "phase_index": p, "rank": r, "score": s,
                            "euler_deg": [float(v) for v in eul[p][r]]})
        return sorted(out, key=lambda d: (-d["score"], d["phase_index"], d["rank"]))

    @property
    def best_quaternion(self) -> list[np.ndarray]:
        return [q[:, 0] for q in self.topk_quaternion]

    def best_euler_deg(self) -> list[np.ndarray]:
        from orix.quaternion import Rotation

        return [np.rad2deg(Rotation(q).to_euler()) for q in self.best_quaternion]


# --------------------------------------------------------------------------- helpers


def roi_indices(scan: ScanData, roi) -> np.ndarray:
    if roi is None:
        return np.arange(scan.n_points)
    rr, cc = scan.map_indices()
    r0, r1, c0, c1 = (int(v) for v in roi)
    sel = (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
    idx = np.nonzero(sel)[0]
    if idx.size == 0:
        raise WorkbenchError(f"ROI {roi} contains no scan points.")
    return idx


def subset_scan(scan: ScanData, idx: np.ndarray) -> ScanData:
    """A view of ``scan`` restricted to points ``idx`` (patterns sliced lazily)."""
    from .io.scan import GRID_POINTS, GridInfo

    if idx.size == scan.n_points:
        return scan
    rr, cc = scan.map_indices()
    r0, r1 = int(rr[idx].min()), int(rr[idx].max()) + 1
    c0, c1 = int(cc[idx].min()), int(cc[idx].max()) + 1
    contiguous_rect = scan.grid.grid_type == "square" and idx.size == (r1 - r0) * (c1 - c0)
    pats = np.asarray(scan.patterns[idx]) if not hasattr(scan.patterns, "compute") else \
        scan.patterns[idx].compute()
    grid = (GridInfo("square", r1 - r0, c1 - c0, scan.grid.step_x, scan.grid.step_y, scan.grid.unit)
            if contiguous_rect else GridInfo(GRID_POINTS, 1, idx.size, scan.grid.step_x, scan.grid.step_y))
    det = scan.detector
    if det.navigation_size > 1:
        pc = np.asarray(det.pc).reshape(-1, 3)[idx]
        from kikuchipy.detectors import EBSDDetector

        det = EBSDDetector(shape=det.shape, pc=pc, binning=det.binning, px_size=det.px_size,
                           tilt=det.tilt, azimuthal=det.azimuthal, twist=det.twist,
                           sample_tilt=det.sample_tilt)
    sub = ScanData(
        patterns=pats, grid=grid, detector=det, x=scan.x[idx], y=scan.y[idx], valid=scan.valid[idx],
        vendor=scan.vendor, file_format=scan.file_format, geometry_source=scan.geometry_source,
        metadata={**scan.metadata, "roi_of": scan.source_path, "roi_n": int(idx.size)},
        warnings=list(scan.warnings),
        vendor_euler_deg=None if scan.vendor_euler_deg is None else scan.vendor_euler_deg[idx],
        static_background=scan.static_background, source_path=scan.source_path,
        dataset_path=scan.dataset_path,
    )
    return sub


def _quaternions(rotations, index: np.ndarray) -> np.ndarray:
    q = rotations.data
    safe = np.clip(index, 0, q.shape[0] - 1)
    out = q[safe]
    out[index < 0] = np.nan
    return out


# --------------------------------------------------------------------------- run


def run_indexing(
    config: IndexingConfig,
    job: Job | None = None,
    scan: ScanData | None = None,
    masters: list[LoadedMaster] | None = None,
    export: bool = True,
) -> IndexingResult:
    """Run the full workflow. ``job`` provides progress, cancellation and the output folder."""
    t_start = time.perf_counter()
    timings: dict = {}
    mcfg = {**MATCHING_DEFAULTS, **(config.matching or {})}
    manifest = RunManifest(kind="indexing")
    manifest.parameters["config"] = config.to_dict()
    events = manifest.log_event

    def progress(f, msg=""):
        if job is not None:
            job.progress(f, msg)

    # ---- scan
    progress(0.0, "Loading scan")
    if scan is None:
        sc = dict(config.scan)
        path = sc.pop("path")
        scan = load_scan(path, **{k: v for k, v in sc.items() if v is not None})
    if scan.source_path and Path(scan.source_path).exists():
        manifest.add_input("scan", scan.source_path, summary=scan.summary())
    else:
        manifest.inputs["scan"] = {"summary": scan.summary()}
    if scan.geometry_source == GEOMETRY_MISSING:
        if not config.allow_placeholder_geometry:
            raise MissingMetadataError(
                "The scan has no usable projection centre.",
                "Supply scan.geometry with pc and pc_convention (from your vendor calibration).",
            )
        events("warning", "Indexing with placeholder geometry (demo only); results are not physical.")
    full_n = scan.n_points
    idx = roi_indices(scan, config.roi)
    work_scan = subset_scan(scan, idx)
    if config.roi is not None:
        events("roi", f"ROI {config.roi}: {idx.size} of {full_n} points")

    # ---- masters
    progress(0.02, "Loading masters")
    if masters is None:
        masters = [load_master(p.master, energy=p.energy, phase_name=p.name) for p in config.phases]
    names = [m.info.phase_name for m in masters]
    if len(set(names)) != len(names):
        names = [f"{n}_{i}" for i, n in enumerate(names)]
        for m, n in zip(masters, names, strict=True):
            m.signal.phase.name = n
    for i, m in enumerate(masters):
        manifest.inputs[f"master_{i}"] = {**m.describe(), "info": m.info.to_dict()}
        if is_kinematical(m.info.program):
            events("warning", f"Phase {names[i]}: master is KINEMATICAL (synthetic), not dynamical EMsoft.")
        if m.info.sample_tilt_deg is not None and abs(m.info.sample_tilt_deg - scan.detector.sample_tilt) > 1.0:
            events("warning", f"Phase {names[i]}: master MC tilt {m.info.sample_tilt_deg}° differs from "
                   f"scan sample tilt {scan.detector.sample_tilt}°.")
        kv = scan.metadata.get("beam_voltage_kV")
        if kv and m.energy_keV and abs(float(kv) - m.energy_keV) > 1.0:
            events("warning", f"Phase {names[i]}: master energy {m.energy_keV} keV vs beam {kv} kV.")

    # ---- geometry and preprocessing
    det_raw, spread = single_pc_detector(work_scan.detector)
    if spread > 0:
        events("pc_approximation", f"Scan PC varies by up to {spread:.4f} (Bruker units); dictionary "
               "uses the mean PC.", {"max_abs_deviation": spread})
    pre = Preprocessor(list(config.preprocessing), work_scan.pattern_shape)
    pre.fit(work_scan)
    mask = pre.mask()
    det = pre.adapt_detector(det_raw)
    proj_det = det_raw  # projection at raw resolution; shared binning applied afterwards
    manifest.parameters["preprocessing"] = pre.describe()
    manifest.parameters["detector_used"] = detector_key_fields(det)
    manifest.parameters["detector_projection"] = detector_key_fields(proj_det)

    n = work_scan.n_points
    p = int(mask.sum())
    chunk_e = int(mcfg["pattern_chunk"])
    t0 = time.perf_counter()
    exp = np.empty((n, p), dtype=np.float32)
    sig = np.empty(n, dtype=np.float32)
    for i0 in range(0, n, chunk_e):
        i1 = min(n, i0 + chunk_e)
        x = pre.apply_experimental(work_scan.get_patterns(i0, i1))
        sig[i0:i1] = signal_metric(x, mask)
        exp[i0:i1] = normalize(x, mask)
        progress(0.02 + 0.08 * i1 / n, f"Preprocessed {i1}/{n} patterns")
    timings["preprocess_s"] = time.perf_counter() - t0

    # ---- sampling (equal resolution for every phase)
    spec = SamplingSpec(float(config.sampling.get("resolution_deg", 3.0)),
                        config.sampling.get("method", "cubochoric"))
    rotations = []
    for m in masters:
        rotations.append(sample_orientations(m.phase, spec))
    n_dict = {names[i]: int(r.size) for i, r in enumerate(rotations)}
    est = estimate_resources(n, n_dict, p, int(mcfg["dictionary_chunk"]), chunk_e, int(mcfg["top_k"]),
                             master_bytes=sum(m.signal.data.nbytes for m in masters))
    manifest.parameters["sampling"] = {**spec.to_dict(), "n_orientations": n_dict,
                                       "estimate_formula_count": {names[i]: estimate_count(m.phase.point_group, spec.resolution_deg)
                                                                  for i, m in enumerate(masters)}}
    manifest.parameters["resources_estimate"] = est.to_dict()

    # ---- matching
    backend = select_backend(str(mcfg["backend"]), on_event=lambda k, msg, d=None: events(k, msg, **(d or {})))
    matcher = Matcher(backend, chunk_e, on_event=lambda k, msg, d: events(k, msg, **d))
    k = int(mcfg["top_k"])
    total = sum(r.size for r in rotations)
    done = 0
    topks = []
    t0 = time.perf_counter()
    t_proj = 0.0
    cache = None
    if mcfg.get("cache_dictionary"):
        from .cache import ArtifactCache

        cache = ArtifactCache(mcfg.get("cache_dir"))
    chunk_d = int(mcfg["dictionary_chunk"])
    for ph_i, (m, rot) in enumerate(zip(masters, rotations, strict=True)):
        tk = TopK(n, k)
        projector = DictionaryProjector(m.signal, proj_det, pre)
        if cache is not None:
            fields = dictionary_cache_fields(m.describe(), proj_det, spec.to_dict(), pre, rot.size)
            tp = time.perf_counter()
            full, hit = get_or_build_dictionary(
                cache, projector, rot, fields, chunk_d,
                progress=lambda f, ph_i=ph_i: progress(0.1 + 0.4 * (ph_i + f) / len(masters),
                                                      f"{names[ph_i]}: building dictionary"),
                cancel=job.cancel_token if job is not None else None)
            t_proj += time.perf_counter() - tp
            events("dictionary_cache", f"{names[ph_i]}: dictionary cache {'hit' if hit else 'miss (built)'}",
                   key=make_key(fields))
            blocks = ((c0, np.asarray(full[c0:c0 + chunk_d])) for c0 in range(0, rot.size, chunk_d))
        else:
            blocks = None
        c0 = 0
        while c0 < rot.size:
            if job is not None:
                job.cancel_token.raise_if_cancelled()
            tp = time.perf_counter()
            if blocks is not None:
                c0, dic = next(blocks)
            else:
                dic = projector.project(rot[c0:c0 + chunk_d])
            t_proj += time.perf_counter() - tp
            matcher.match_block(exp, dic, tk, 0, c0)
            done += dic.shape[0]
            progress(0.1 + 0.85 * done / total, f"{names[ph_i]}: matched {c0 + dic.shape[0]}/{rot.size} "
                     "dictionary patterns")
            c0 += dic.shape[0]
        topks.append(tk)
    timings["projection_s"] = t_proj
    timings["matching_s"] = time.perf_counter() - t0 - t_proj
    manifest.parameters["matching"] = {**mcfg, "backend_used": matcher.backend.name,
                                       "pattern_chunk_final": matcher.pattern_chunk,
                                       "score": "NCC (zero-mean, unit-norm dot product, float32)",
                                       "tie_policy": "descending score, then ascending dictionary index",
                                       "coverage": "identical sampling resolution and method for all phases"}
    if hasattr(matcher.backend, "peak_memory_bytes"):
        manifest.results["gpu_peak_memory_bytes"] = matcher.backend.peak_memory_bytes()

    # ---- decision
    policy = DecisionPolicy(**config.decision) if config.decision else DecisionPolicy()
    per_phase_best = np.stack([t.scores[:, 0] for t in topks], axis=1)
    decision = decide(per_phase_best, policy, signal=sig, valid=work_scan.valid)
    manifest.thresholds = policy.to_dict()
    result = IndexingResult(
        phase_names=names,
        phases=[m.phase for m in masters],
        decision=decision,
        per_phase_best=per_phase_best,
        topk_scores=[t.scores for t in topks],
        topk_index=[t.valid_index() for t in topks],
        topk_quaternion=[_quaternions(r, t.valid_index()) for r, t in zip(rotations, topks, strict=True)],
        n_dictionary=[int(r.size) for r in rotations],
        signal=sig,
        point_index=idx,
        manifest=manifest,
        context={"scan": work_scan, "masters": masters, "detector": proj_det, "preprocessor": pre},
        job_dir=str(job.path) if job else None,
    )
    timings["total_s"] = time.perf_counter() - t_start
    timings["patterns_per_s"] = n / max(timings["matching_s"] + timings["projection_s"], 1e-9)
    result.timings = timings
    manifest.results.update({"counts": decision.counts(), "n_points": n, "timings": timings,
                             "score_summary": {names[i]: {"median_best": float(np.median(per_phase_best[:, i]))}
                                               for i in range(len(names))}})

    # ---- export
    if export:
        out_dir = Path(job.outputs if job is not None else config.output.get("dir", "kwb_output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        progress(0.96, "Exporting")
        files = export_maps(result, work_scan, out_dir) if config.output.get("png", True) else {}
        files["table_csv"] = export_csv(result, work_scan, out_dir / "results.csv")
        files["results_h5"] = export_h5(result, work_scan, out_dir / "results.h5")
        manifest.outputs = files
    manifest.status = "completed"
    if export:
        manifest.write(out_dir / "manifest.json")
        manifest.outputs["manifest"] = str(out_dir / "manifest.json")
    progress(1.0, "Done")
    return result


def run_indexing_job(config: IndexingConfig, jobs_root: str | os.PathLike, listener=None,
                     job: Job | None = None) -> tuple[Job, IndexingResult]:
    job = job or Job.create(jobs_root, "indexing")
    if listener:
        job.add_listener(listener)
    (job.path / "config.json").write_text(json.dumps(config.to_dict(), indent=2, default=str))
    job.log(f"KikuchiWorkbench {__version__}: indexing job started")
    result = job.run(lambda j: run_indexing(config, job=j))
    return job, result
