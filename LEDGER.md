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
