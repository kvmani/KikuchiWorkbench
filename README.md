# KikuchiWorkbench

Desktop workbench (PySide6) and headless CLI for **master-pattern-based EBSD dictionary indexing** and
**phase discrimination**, built on EMsoft (simulation), kikuchipy (readers, projection) and orix (orientations).

> **Status: early development — not a release candidate.** What has been verified, on which platform, and what is
> still open is recorded in [LEDGER.md](LEDGER.md); the plan is in [ROADMAP.md](ROADMAP.md); the release contract is
> [the project scope](KikuchiWorkbench_Project_Scope.md).

## What works today (evidence in the ledger)

* Import: Oxford H5OINA (raw preferred) and `.ebsp`; EDAX/TSL H5EBSD (square and hexagonal) and `.up1/.up2`;
  EMsoft simulated EBSD; project fixtures. Pattern-free files are rejected with export advice. *Tested on
  synthetic structural files and kikuchipy's reader samples — not yet on representative lab exports.*
* Explicit, tested conventions for PC (Bruker internal; TSL/Oxford/EMsoft conversions), detector pixels,
  rotations and scan order — see [docs/conventions.md](docs/conventions.md).
* CIF validation against the EMsoft crystal representation, EMsoft `.xtal` writer, EMsoft master import and
  verification, content-addressed master and dictionary caches with verified promotion.
* EMsoft job adapter (CIF → MC → master) — **tested only with mock executables**; native Windows + OpenCL run is
  an open release gate ([docs/emsoft.md](docs/emsoft.md)).
* Dictionary indexing on CPU (NumPy/BLAS) with optional PyTorch CUDA, bounded batches, deterministic top-k per
  phase, automatic fallback recorded in the manifest; equal-budget orientation refinement per phase.
* Phase decision with distinct *indexed / ambiguous / unindexed / low-signal / missing* labels and score margins
  (diagnostics, not probabilities); PNG maps, CSV, HDF5 and a versioned JSON manifest.
* Guided GUI with worker threads, cancellation, pixel inspection (measured vs best simulated pattern per phase).
* Offline CPU demo and a synthetic Ni/Cu benchmark ([docs/benchmark_report.md](docs/benchmark_report.md)).

## Quick start

```bash
pip install -e ".[gui]"
```

```bash
kwb demo
```

```bash
kwb-gui
```

Full walkthrough: [docs/quickstart.md](docs/quickstart.md) · Vendor exports: [docs/vendor_export.md](docs/vendor_export.md)
· Parameters and CLI: [docs/parameters.md](docs/parameters.md) · Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)

## Development

```bash
pip install -e ".[dev,gui]"
```

```bash
pytest -q
```

Default tests run offline without OpenCL or CUDA. Marked suites: `pytest -m emsoft` (needs `KWB_EMSOFT_BIN`
and OpenCL), `pytest -m cuda` (needs PyTorch CUDA), `pytest -m realdata` (needs `KWB_REALDATA_DIR`).
Benchmarks: `benchmarks/run_cubic_discrimination.py`, `benchmarks/gpu_cpu_parity.py`,
`benchmarks/fetch_public_data.py`. Licences of dependencies and data: [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md)
(the repository licence is still an open decision).

## Validated platforms (so far)

| Platform | What ran |
| --- | --- |
| Linux container (Python 3.13, 4 CPU) | full test suite, demos, GUI offscreen, benchmarks |
| GitHub Actions ubuntu-latest / windows-latest (Python 3.11, 3.12) | full default test suite incl. offscreen GUI, both demos |
| Windows 11 workstation, OpenCL, CUDA | **not yet** |
