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
