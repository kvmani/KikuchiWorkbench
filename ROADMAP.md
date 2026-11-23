# KikuchiWorkbench Roadmap

This roadmap turns [KikuchiWorkbench_Project_Scope.md](KikuchiWorkbench_Project_Scope.md) (the release contract) and
[AGENTS.md](AGENTS.md) into ordered, checkable work packages. Progress, evidence and blockers are recorded in
[LEDGER.md](LEDGER.md). A box is ticked only when its stated evidence exists in the repository or the ledger.

Legend: `[ ]` not started · `[~]` in progress / partial · `[x]` done with evidence · `[!]` blocked (see ledger)

Environment note: development so far runs in a Linux cloud container (CPU only, no OpenCL, no CUDA, no Windows).
Items that need Windows 11, an OpenCL device, a CUDA GPU, or real lab scans are marked **[HW]** and stay open
until evidence from a suitable machine is recorded.

---

## Phase 0 — Project scaffolding

- [x] 0.1 Python package `kikuchiworkbench` (src layout), `pyproject.toml`, console script `kwb`.
- [~] 0.2 Pinned dependency ranges for kikuchipy, orix, h5py, numpy, PySide6 (optional `gui` extra), torch (optional `cuda` extra); record versions actually tested in the ledger.
- [x] 0.3 Default test suite (`pytest`) runs offline with no OpenCL/CUDA; integration tests behind markers (`emsoft`, `cuda`, `gui`, `realdata`).
- [x] 0.4 CI workflow: Linux + Windows CPU runners, lint + unit tests + headless demo smoke test.
- [x] 0.5 `.gitignore` excludes caches, job folders, large scans and generated masters.
- [x] 0.6 Third-party licence and attribution notes (`docs/THIRD_PARTY.md`); repository licence left as an open decision.

## Phase 1 — Conventions and data model (feasibility & formats, milestone 1)

- [x] 1.1 `docs/conventions.md`: crystal and sample frames, active/passive rotation, Bunge Euler, detector pixel axes, PC conventions (internal = Bruker/kikuchipy; EDAX/TSL, Oxford, EMsoft conversions), units, binning, crop, scan order, hexagonal grids.
- [x] 1.2 `conventions` module: PC conversion between vendors with round-trip tests and asymmetric/off-centre fixtures that expose sign, transpose and mirror errors.
- [x] 1.3 Scan data model: read-only pattern store, scan coordinates (square + hexagonal), missing points, detector geometry, metadata provenance.
- [x] 1.4 Versioned run manifest schema (JSON) with inputs, checksums, conventions, parameters, software, hardware, thresholds, fallbacks, exports.

## Phase 2 — Importers (milestone 1)

- [x] 2.1 Format detection by file structure and version (not extension only).
- [~] 2.2 Oxford H5OINA (prefer raw over processed dataset), Oxford `.ebsp` (uncompressed) + companion/user geometry.
- [~] 2.3 EDAX/TSL H5EBSD / `.oh5`, `.up1`/`.up2` with user-supplied map dimensions/geometry; hexagonal grids.
- [x] 2.4 EMsoft simulated EBSD HDF5 and project fixture format (known geometry, orientations, phases, coordinates).
- [x] 2.5 Actionable rejection of pattern-free inputs (`.ang`, `.ctf`, pattern-free HDF5) with export instructions.
- [~] 2.6 Per-vendor file checks (structure fingerprint, dims, bit depth, scan order) with tests on synthetic structural fixtures.
- [~] 2.7 **[HW/data]** Verify against real representative Oxford and EDAX/TSL exports; publish supported-versions matrix.

## Phase 3 — Master patterns and crystals (milestone 1–2)

- [x] 3.1 Import EMsoft master HDF5: verify projection, hemispheres, energy bins, phase/space group, checksum.
- [x] 3.2 Master cache keyed by crystal + simulation settings + provenance; atomic promotion only after verification.
- [x] 3.3 CIF reader/validator: cell units, setting/origin, sites, occupancies; positive and negative controls (equivalent axis settings, malformed occupancies, unsupported representations).
- [~] 3.4 EMsoft `.xtal` writer from validated CIF.
- [x] 3.5 EMsoft job adapter: namelist generation for crystal, Monte Carlo (`EMMCOpenCL`) and master (`EMEBSDmaster`) as distinct stages; no-shell subprocess, per-job working directory, logs, cancellation, HDF5 verification before cache promotion. Tested with a mock executable.
- [x] 3.6 Kinematical master generator (kikuchipy) for offline synthetic fixtures — clearly labelled as kinematical, never as dynamical EMsoft output.
- [!] 3.7 **[HW]** Native Windows 11 EMsoft CIF → xtal → MC → master run with OpenCL; reproducible recipe; compare with reference projection. Release gate.

## Phase 4 — Headless scientific workflow (milestone 2)

- [x] 4.1 Detector geometry service: import vendor PC, binning, crop; simulated vs experimental preview/residual.
- [x] 4.2 Preprocessing pipeline (background removal, normalisation, masks) recorded and reproducible; raw data never modified.
- [x] 4.3 Symmetry-reduced orientation sampling (orix) with resource estimate (orientations, RAM, disk).
- [x] 4.4 Bounded-batch dictionary projection per phase (kikuchipy), cache key including detector, grid, preprocessing.
- [x] 4.5 CPU NCC matcher (NumPy/BLAS), chunked, top-k per phase, deterministic tie policy.
- [x] 4.6 Phase decision: best score per phase, runner-up, margin, unindexed (low score) and ambiguous (small margin) kept distinct.
- [x] 4.7 Exports: PNG maps (phase, IPF, score, margin, ambiguity), CSV table, manifest.
- [x] 4.8 Job system: isolated job folders, status file, logs, progress callback, cancellation; failed/cancelled outputs never promoted.
- [x] 4.9 CLI `kwb`: `inspect`, `demo`, `index` (config file), `master import`, `cif validate`, `xtal`, `emsoft plan`.
- [x] 4.10 Offline small CPU demo end-to-end from the bundled Ni master; test asserting exact-grid orientation recovery up to symmetry.

## Phase 5 — Dictionary and phase validation (milestone 3)

- [~] 5.1 Optional PyTorch CUDA matcher; Auto/CPU/GPU selection; automatic fallback and batch shrink recorded in manifest.
- [x] 5.2 Synthetic two-phase cubic fixture generator (Ni a=3.524 Å vs Cu a=3.615 Å FCC Fm-3m), held-out off-grid orientations, seeds recorded.
- [x] 5.3 Identical-master control (must report ambiguity), lattice-parameter sweep, PC offset, noise, binning, angular-step stress tests.
- [x] 5.4 Benchmark scripts producing confusion matrices (incl. ambiguous/unindexed), per-phase recall, coverage vs error, misorientation error, margins, compute cost.
- [x] 5.5 Threshold selection on dev fixtures, frozen before held-out runs.
- [x] 5.8 Equal-budget orientation refinement per phase (needed: grid error swamps the Ni/Cu score difference).
- [ ] 5.6 **[HW]** Measured CPU/GPU parity, throughput, peak RAM/VRAM on a 4 GB CUDA GPU.
- [~] 5.7 **[HW/data]** Real-data interoperability: public Oxford Al–Si `.ebsp` + EMsoft Al/Si masters; TSL scan.

## Phase 6 — Desktop GUI (milestone 4)

- [~] 6.1 PySide6 guided workflow shell (6 steps) calling the shared core; advanced settings expandable.
- [x] 6.2 Worker threads with progress, cancel and log panel; GUI stays responsive.
- [x] 6.3 Scan view: map grid, pattern preview raw/preprocessed side by side.
- [x] 6.4 Phase view: crystal summary and validation messages.
- [x] 6.5 Geometry check: experimental vs simulated overlay/residual.
- [~] 6.6 Results: phase/IPF/score/margin maps, pixel picker with per-phase candidates and best simulated pattern, threshold slider, export.
- [x] 6.7 Offscreen GUI smoke test in CI.
- [ ] 6.8 **[HW]** Windows GUI launch + bundled demo smoke test; offline installer / portable bundle.

## Phase 7 — Documentation and release

- [~] 7.1 Beginner quick start (bundled example, offline).
- [~] 7.2 Vendor export instructions (Oxford AZtec, EDAX OIM/APEX).
- [ ] 7.3 Native Windows EMsoft CIF-to-master tutorial (after 3.7).
- [x] 7.4 Advanced parameter reference, CLI reproduction guide, troubleshooting.
- [ ] 7.5 Benchmark report with validated platforms, file variants and limitations.

## Phase 8 — Ease of use (from docs/ideas_and_research.md, section B)

Order chosen so later items reuse earlier ones (presets and project files feed the batch queue and reports).

- [x] 8.1 (B6) **Presets** — "quick look", "standard", "phase study": grid, binning, refinement, calibration;
  resource check warns on RAM/time before launch. CLI `--preset`, GUI preset selector.
- [x] 8.2 (B1) **Project files** — `.kwbproj` JSON (scan + load options, phases, geometry/calibration, settings,
  run history with job folders). Save/open in GUI, `kwb project` CLI, round-trip tests.
- [x] 8.3 (B2) **Interactive ROI** — drag a rectangle on the scan/result map; syncs the ROI fields.
- [x] 8.4 (B5) **One-click run report** — Markdown + self-contained HTML (maps embedded, written to the job folder,
  never into Git): inputs, settings, counts, warnings, timings, manifest link. CLI `kwb report JOB`, GUI button.
- [x] 8.5 (B3) **Phase library and cache browser** — list/search verified masters (formula, space group, energy,
  kinematical flag, provenance); add to project in one click; prune cache.
- [x] 8.6 (B4) **Geometry wizard** — kinematical band-line overlay on the measured pattern, live update while
  editing PC/tilt, residual and NCC readout.
- [x] 8.7 (B7) **Batch queue** — queue several scans/ROIs/projects, run sequentially in a worker, resume after
  restart (queue file), per-item status. CLI `kwb batch QUEUE`, GUI queue panel.
- [x] 8.8 (B8) **Comparison view** — vendor orientations/phases vs workbench: disorientation map, phase
  agreement/confusion table, exported in the report.
- [x] 8.9 (B10) **Reader plug-ins** — registry (Python entry points `kikuchiworkbench.readers`) so new formats plug
  into detection and `load_scan`; first plug-ins: NORDIF and Bruker h5ebsd via kikuchipy.
- [ ] 8.10 (B9) **Offline Windows installer** **[HW]** — PyInstaller spec + build script and docs prepared here;
  build and signing on Windows after the native EMsoft gate.

## Release-candidate gate (from AGENTS.md)

- [ ] Native Windows CIF→master run demonstrated **[HW]**
- [~] Load-to-export evidence for Oxford and EDAX/TSL **[data]** (Oxford public .ebsp done; EDAX/TSL pending)
- [~] CPU cloud demo
- [ ] Measured GPU/CPU parity **[HW]**
- [~] Synthetic cubic and real-data benchmark reports (synthetic kinematical interim report done)
- [ ] Quick start, vendor export instructions, benchmark reproduction scripts
