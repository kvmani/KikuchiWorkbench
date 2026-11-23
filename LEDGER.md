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
