# Progress Ledger

Append-only log of work done against [ROADMAP.md](ROADMAP.md). Each entry records what changed, the evidence
(tests, commands, outputs), and any blockers or limitations. Planned features belong in the roadmap, not here.

**How to resume after an interruption:** read the latest entry's "Next" line, check `git log`, run
`pytest -q`, then continue with the first unticked roadmap item in the current phase.

---

## 2026-11-23 — Entry 1: Roadmap and ledger

- Created `ROADMAP.md` (phases 0–7 + release gate) and this ledger.
- Environment probed: Linux container, Python 3.13, 4 CPU, 15 GB RAM, no GPU/OpenCL, no Windows.
  Packages installable from PyPI: kikuchipy 0.14.2, orix 0.15.0, h5py 3.16, numpy 2.5, PySide6 6.12.
- kikuchipy ships small offline files usable in tests (not redistributed by us): Ni EMsoft master
  (`emsoft_ebsd_master_pattern`), Ni 3×3 patterns, and reader samples for Oxford `.ebsp`, EDAX `.up1/.up2`,
  EDAX H5EBSD and EMsoft simulated EBSD. These are reader test files, **not** verified real vendor exports.
- Blocker (roadmap 3.7, release gate): native Windows 11 EMsoft + OpenCL cannot run in this container.
  Continuing with master import and the headless CPU demo, as AGENTS.md directs.
- Next: Phase 0 scaffolding.

## 2026-11-23 — Entry 2: Scaffolding, conventions, importers

- Package `src/kikuchiworkbench` with `pyproject.toml` (console script `kwb` declared; CLI to come), `.gitignore`.
- `conventions.py` + `docs/conventions.md`: internal Bruker PC; explicit TSL/Oxford/EMsoft(4/5) conversions.
  Tests use an asymmetric, off-centre, non-square geometry and cross-check against kikuchipy 0.14.2.
- `manifest.py` (schema 1.0), `provenance.py` (sha256, software versions, hardware), `errors.py` (actionable advice).
- `io/detect.py`: structural detection (HDF5 `Manufacturer`, incl. EDAX's leading-space keys; UP header; `.ebsp`
  version), pattern-free rejection (`.ang/.ctf/.osc/.cpr`, pattern-free H5OINA/EDAX/EMsoft) with export advice.
- `io/readers.py` → `ScanData` (read-only patterns, grid, coordinates, valid mask, detector, geometry source):
  H5OINA (prefers `Unprocessed Patterns`), `.ebsp` (+ companion H5OINA geometry), EDAX H5EBSD (own reader, square +
  hexagonal), UP1/UP2 v1/v3 (incl. hexagonal), EMsoft EBSD, kikuchipy h5ebsd, project fixture format (with truth).
- Evidence: `pytest -q` → 45 passed (Linux, Python 3.13, kikuchipy 0.14.2, orix 0.15.0); `ruff check` clean.
- Limitations: H5OINA/EDAX tests use **synthetic structural files**, not real exports. kikuchipy's bundled
  EDAX H5 sample stores PC = 0 (flagged as missing). kikuchipy's bundled hexagonal `.up2` has 10 patterns for a
  3×3 hex header, inconsistent with the assumed `ncols_even = ncols_odd − 1`; we refuse it as a grid and allow
  `grid_type="points"`. Hexagonal layout assumption must be verified on a real OIM export (roadmap 2.7).
- Next: master import/verification + cache (3.1, 3.2), then CIF validation (3.3).

## 2026-11-23 — Entry 3: Crystals, masters, cache

- `crystal/cif.py`: CIF → `CrystalModel` validated against the EMsoft representation (space group, origin choice,
  Å/° cell, asymmetric unit, occupancy, B). Origin choice for the 24 two-origin groups from operators, `:1/:2`
  symbols or tags; ambiguous → rejected. Origin-2 coordinates are shifted to origin 1 for orix/diffpy (which only
  tabulate origin 1). Rejects: rhombohedral axes, non-standard monoclinic/tetragonal metrics, nm cells, malformed or
  >1 occupancies, modulated and magnetic CIFs, isotopes.
  Controls in `tests/data/cif/`: Ni, Cu, Ni with shifted origin, Si origin 1/2 (identical |F|, diamond 200
  extinction), and 6 negative controls.
- `crystal/xtal.py`: EMsoft `CrystalData` writer/reader (nm, nm² B). Trigonal crystal-system code and string widths
  still to be confirmed against EMmkxtal (3.4 partial, needs 3.7).
- `masters/importer.py`: verifies EMsoft master HDF5 (projection, hemispheres, energy bins strictly increasing,
  finite non-constant content, space group, MC tilt/energy), drops personal header fields, sha256. Loads Lambert
  data directly with h5py (kikuchipy's reader only accepts EMsoft program names); data identical to kikuchipy's for
  the Ni master. Energy: max / nearest keV / weighted (global MC-histogram weights — recorded as an approximation).
- `masters/kinematical.py`: kinematical masters (kikuchipy simulator) written in EMsoft layout and labelled
  `NOT dynamical EMsoft` in `ProgramName`; used for offline synthetic fixtures only.
- `cache.py` + `masters/cache.py`: content-addressed cache, staging dir, verify-then-atomic-promote, `COMPLETE`
  marker; failed verification never promotes.
- Evidence: `pytest -q` → 68 passed; `ruff check` clean. kikuchipy's Al2Cu multi-energy sample is rejected as
  constant (it is a synthetic reader fixture) — used as a negative control.
- Next: indexing core — sampling, dictionary projection in bounded batches, CPU NCC matcher, phase decision (4.x).

## 2026-11-23 — Entry 4: Headless indexing core, CLI and offline demo

- `indexing/preprocessing.py`: recorded pipeline (static background from file or scan mean, Gaussian dynamic
  background, binning, circular mask); raw patterns untouched; shared steps also applied to simulations; signal
  metric (smoothed/residual std) for low-signal flags, separate from orientation fit.
- `indexing/sampling.py`: orix cubochoric fundamental-zone sampling; count estimate (empirical constant, ±5% for
  m-3m) and RAM/disk estimate recorded in the manifest.
- `indexing/dictionary.py`: per-phase chunked projection with kikuchipy (single mean PC; spread recorded as a
  `pc_approximation` event).
- `indexing/matching.py`: NCC (float32), running top-k per phase with deterministic tie policy (score desc, index
  asc; verified invariant to chunk size with heavy ties), CPU backend, optional PyTorch CUDA backend, Auto
  selection, OOM → batch halving → CPU fallback, all recorded as manifest events.
- `indexing/decision.py`: labels indexed / ambiguous / unindexed / low_signal / missing; per-phase best scores,
  runner-up, margin, exact-tie flag. Default thresholds are explicitly marked *provisional, not calibrated*.
- `jobs.py`: job folders with `status.json`, `job.log`, `work/`, `outputs/`; `COMPLETE` only on success, `INVALID`
  on failure/cancel (scratch removed); thread-safe cancel token.
- `export.py`: phase, IPF-Z, score, margin, signal PNG maps; CSV; HDF5 results (top-k per phase); manifest.
- `pipeline.py`: shared core (`IndexingConfig` from YAML/JSON, ROI, equal sampling for all phases, warnings for
  kinematical masters and tilt/voltage mismatches); `synthetic.py`: seeded synthetic scans with ground truth.
- `cli.py` (`kwb inspect | master | cif | kinematical | index | demo | emsoft plan`), `demo.py`.
- Evidence (this container, CPU only):
  - `kwb demo` (EMsoft dynamical Ni master bundled with kikuchipy, 6×6 off-grid random orientations, asymmetric
    PC, background + Poisson noise, 4° grid): 36/36 indexed, median misorientation 1.97°, max 3.88°, 7 s.
  - `kwb demo --two-phase` (kinematical Ni a=3.524 Å vs Cu a=3.615 Å): 36/36 correct phase, median
    misorientation 1.90°; phase margins only 0.02–0.07 NCC on clean synthetic data — a first indication of how
    small the Ni/Cu separation is. Kinematical masters, not a dynamical result.
  - Tests: exact-grid recovery (<0.5°, NCC>0.99), identical masters → all ambiguous with tie flag, pure-noise
    patterns → unindexed with lower signal metric, cancellation (callback and cross-thread) → INVALID job, missing
    geometry → failed job, OOM fallback. `pytest -q` → 93 passed in 17 s; `ruff` clean.
- Found and fixed: dynamic background *division* with σ = 4 px destroyed band contrast on 60×60 patterns
  (median NCC 0.10 vs 0.49); default is now subtraction with σ = width/8.
- Next: EMsoft job adapter (namelists, no-shell runner, mock executable tests) for `kwb emsoft plan`; then CI
  workflow, GUI skeleton.

## 2026-11-23 — Entry 5: EMsoft adapter, CI, licence notes

- `emsoft/jobs.py`: presets (`quick`, `standard`, both `validated: false`), namelist writers for `&MCCLdata`,
  `&EBSDmastervars`, `&Bethelist` (key set from EMsoft 5.0 templates shipped with kikuchipy), plan → run MC →
  verify MC (`accum_e`/`accum_z`, non-empty) → run master → verify master (space group, MC tilt) → cache promotion
  with namelists/logs. Per-job `EMsoftConfig.json` via job-local HOME/USERPROFILE; argument-list subprocess,
  terminate/kill on cancel, timeout.
- `kwb emsoft plan|run|check`; `docs/emsoft.md` with the Windows recipe and native-run checklist.
- Evidence: mock executables (`tests/mock_emsoft/`, run through the Python interpreter, reading the job-local
  config) → full chain cached; simulated MC and master failures leave the cache empty; cancelling a running stage
  → job INVALID. `pytest -q` → 99 passed, 1 deselected (`-m emsoft` real run).
- Not verified: real EMsoft execution, Windows config resolution, trigonal crystal-system code (3.7 open).
- `.github/workflows/ci.yml`: Linux + Windows, Python 3.11/3.12, ruff, pytest, both demos; uploads demo outputs.
  CI has not run yet at the time of writing (check the Actions tab after push).
- `docs/THIRD_PARTY.md`: dependency licences (GPL-3.0 kikuchipy/orix affects bundling), test-data provenance.
- Next: PySide6 GUI skeleton on the shared core (6.1–6.3, 6.7), then benchmark scripts (5.2–5.4).

## 2026-11-23 — Entry 6: PySide6 GUI skeleton on the shared core

- `gui/main_window.py`: six guided steps (scan, phases, masters, geometry, build & match, inspect & export), log
  panel, progress bar, cancel button. Scan page: summary, warnings, mean-intensity map, raw vs preprocessed pattern.
  Phase page: master verification report, CIF validation messages (kinematical masters tagged). Masters page:
  EMsoft generation (needs `KWB_EMSOFT_BIN`) or kinematical (labelled synthetic). Geometry page: editable Bruker
  PC/tilt/binning recorded as user geometry; experimental vs simulated vs residual after an ROI run. Index page:
  resolution, device, thresholds, ROI preview, resource estimate. Results page: phase / IPF-Z / score / margin /
  signal maps, click a pixel → candidate table (all phases, top-k) + measured and best simulated pattern per phase,
  live ambiguity threshold (re-decision without re-matching), export (PNG, CSV, HDF5, manifest).
- `gui/workers.py`: QThread workers; results delivered through bound slots (queued to the GUI thread).
  Two crashes found and fixed: PySide double deletion (`deleteLater` + GC) and GUI updates from the worker thread
  via lambda connections.
- Core additions: `IndexingResult.redecide/measured_pattern/simulated_pattern/candidates`.
- Entry points: `kwb-gui`, `kwb gui`. Screenshot: `docs/images/gui_results_example.png` (offscreen, Linux).
- Evidence: offscreen GUI tests (load example in worker → ROI index → inspect pixel → change threshold → export;
  cancel mid-run → no result) pass. `pytest -q` → 101 passed. Linux container needed `libegl1` etc.; CI installs them.
- Not verified: Windows GUI launch (6.8, needs Windows runner/workstation — CI windows job will be the first check).
- Next: check CI results; benchmark scripts for the controlled cubic study (5.2–5.5); quick start docs.

## 2026-11-23 — Entry 7: Dictionary cache; first CI results

- CI run 2 (commit f297278): Linux 3.11/3.12 passed; Windows 3.11/3.12 98/99 passed — including the mock EMsoft
  subprocess chain, so argument-list process launch and job folders work on Windows runners. The one failure was a
  test bug (JSON-escaped backslashes); fixed in 09cd742. CI now triggers on `main` only (avoids duplicate runs).
- Dictionary cache (`matching.cache_dictionary: true`): normalised float32 dictionary as `.npy` per phase, key =
  master checksum + energy selection, detector, sampling, shared preprocessing key and mask, kikuchipy version;
  verified (shape, finite, unit norm) before promotion; read back as memmap. Test: cache hit gives identical top-k
  to the uncached path; a different PC misses. `pytest tests/test_pipeline.py` → 9 passed.
- Next: controlled cubic benchmark script (dev/held-out split, frozen thresholds, stress conditions).

## 2026-11-23 — Entry 8: Cubic discrimination benchmark — reflector-cutoff artifact found and removed

- `kikuchiworkbench/benchmark.py` + `benchmarks/run_cubic_discrimination.py`: dev (seed 1001) and held-out
  (seed 2002) scans with random off-grid orientations; ambiguity margin selected on the dev baseline (smallest
  margin with error ≤ 1% and ≥ 10 indexed points) and written to `thresholds.json` before held-out runs, which read
  the frozen file. Conditions: noise (50/400/2000 counts), PC error (0.005/0.01/0.02), binning 2, step 3/4/6°,
  identical masters, 50/50 mixed patterns, same-chemistry lattice sweep (0.5/1/2%), matched vs mismatched master
  routes. Outputs: report.md, results.json, thresholds.json, coverage-vs-error CSVs.
- **Artifact found.** The first runs showed perfect Ni/Cu separation with matched routes and a suspicious jump
  between a 1% (no separation) and 2% (perfect) lattice change. Cause: a fixed d-spacing cutoff (0.8 Å) admits
  {420} (h²+k²+l² = 20) for Cu (d = 0.808 Å) and Ni+2% but not for Ni (0.788 Å), so one master had an extra band
  family. The earlier `kwb demo --two-phase` "100% accuracy" (Entry 4) was this artifact and is withdrawn.
  Fix: kinematical masters accept `max_hkl_sq` (identical hkl families for all compared cubic phases) and store the
  rule and family list; the pipeline warns when competing kinematical masters have different families (tested).
- **Artifact-free result** (`benchmarks/results/full_2026-11-23/report.md`, 196 points/scan, kinematical masters):
  Ni vs Cu median true-phase NCC margin ≈ 0.0005–0.0012. At zero ambiguity margin the error among indexed points
  is 0.27–0.30 with matched master routes and 0.45 (near chance) with the mismatched route; noise, PC error,
  binning and step size do not change this materially. The dev-selected threshold could not meet the 1% error
  target (`met_target: false`) and froze at the largest margin tested (0.05), so held-out pixels are reported
  ambiguous — **no confidently wrong labels in any condition**; identical masters and 50/50 mixed patterns are
  100% ambiguous as required.
- Interpretation (to test next): the 4° dictionary grid gives ~2° orientation error, whose NCC penalty is ~100×
  the phase effect, so the per-phase best orientation differs by chance. Equal-budget orientation refinement for
  each phase (scope: phase decision) is the next step (roadmap 5.8).
- Two-phase demo pass rule changed to "no confidently wrong labels and orientation within the grid resolution";
  it now reports all 36 pixels ambiguous, true phase scores higher for 24/36.
- Docs: `docs/quickstart.md`, `docs/vendor_export.md` (unverified against lab exports). `pytest -q` → 106 passed.
- Next: orientation refinement with equal budget per phase; rerun the benchmark.

## 2026-11-23 — Entry 9: Equal-budget refinement; benchmark report

- `indexing/refinement.py`: kikuchipy NCC refinement per phase from each phase's best dictionary candidate(s)
  with an identical budget (method, trust region = grid step by default, rtol, maxeval, number of starts), fixed
  shared PC; recorded in the manifest (`parameters.refinement`, mean evaluations per phase, time). Config:
  `refinement: {enabled: true, ...}`; pre-refinement scores kept (`per_phase_best_dictionary` in results.h5).
  Test: refinement lowers orientation error below 1° and identical phases stay exactly tied.
- Benchmark `--refine` run: `benchmarks/results/full_refined_2026-11-23/`. Summary in `docs/benchmark_report.md`:
  forced-choice Ni/Cu accuracy 93% (matched fine route), 88% (matched coarse), 63% (mismatched); true-phase
  margins ~0.001–0.003 NCC; frozen threshold → all ambiguous, no confident wrong labels (≤ 2/196 isolated points in
  two conditions). The dev 1%-error target was not achievable.
- Roadmap 5.8 done; 5.4/5.5 done for the synthetic kinematical case (dynamical + real data still open).
- Next: README overhaul + docs index; parameter reference; CUDA parity script (to run on a GPU machine); then
  real-data interoperability prep (Al–Si public data download script, roadmap 5.7).

## 2026-11-23 — Entry 10: CI green on Windows; docs; parity script; public data fetch

- CI runs 4–6 (commits 09cd742, c34c97a, 070991d): **success** on ubuntu-latest and windows-latest, Python 3.11 and
  3.12 — default test suite incl. offscreen GUI tests and both CLI demos. First evidence that the core, job
  folders, subprocess launch (mock EMsoft) and the Qt GUI (offscreen) work on Windows (Server runner, not a
  Windows 11 workstation with a display).
- `benchmarks/gpu_cpu_parity.py` (CPU vs CUDA scores, best-index agreement, near ties, time, peak RSS/VRAM,
  optional VRAM cap to exercise batch shrinking/fallback) and `tests/test_cuda.py` (`-m cuda`). Here the GPU leg
  is recorded as not run (no CUDA). 5.6 remains open until run on a CUDA machine.
- `benchmarks/fetch_public_data.py`: Zenodo download with md5 verification (Al–Si Oxford zip 968 MB, EMsoft Ni
  master 305 MB, CC-BY-4.0) into a data folder outside Git. Download in progress (~0.4 MB/s).
- Docs: README rewritten (status, verified platforms), `docs/parameters.md` (config keys, preprocessing steps,
  CLI, outputs), `docs/troubleshooting.md`.
- Next: when data arrive — real Oxford `.ebsp` load-to-export check on an ROI with EMsoft Al/Si masters (5.7),
  and Ni reference-master projection comparison (dynamical vs kinematical).

## 2026-11-23 — Entry 11: Shared PC calibration

- `indexing/calibration.py`: choose high-signal points spread over the map, index them with a reference phase,
  refine orientation (stage 1) then orientation + PC jointly (stage 2, kikuchipy), iterate 3× from the median PC;
  the median PC is applied to the scan (`geometry_source = calibrated`) and shared by **all** phases; per-point PC,
  spread, history and scores recorded in `parameters.pc_calibration`. Config: `calibration: {enabled: true,
  phase: 0, n_points: 16}`.
- Evidence: synthetic Ni scan with PC offset (+0.015, 0, +0.015): calibrated PC within 0.004 of truth using 6
  points from a 6° grid (single-stage joint refinement only reached 0.013). `pytest -q` → 109 passed.
- Al–Si public dataset downloaded and md5-verified (Zenodo 20290635); Ni reference master download in progress.
