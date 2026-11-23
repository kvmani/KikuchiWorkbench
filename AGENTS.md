# AGENTS.md

## Project

KikuchiWorkbench is a Windows-first desktop application for master-pattern-based EBSD dictionary indexing. Read [KikuchiWorkbench_Project_Scope.md](KikuchiWorkbench_Project_Scope.md) before implementing or changing the workflow. Use the scope as the release contract. Record implementation evidence and benchmark limitations separately from planned features.

## Cardinal rule: no binary content in Git

Never commit binary files (images, screenshots, PDFs, slide decks, Office documents, HDF5/NumPy data, archives,
executables) unless the repository owner explicitly asks for a specific file. Keep review artifacts, figures and
generated data outside the repository (for example `~/kwb_review_artifacts`) and present them directly.
`tools/check_no_binaries.py` enforces this in `tools/checkpoint.sh` and in CI.

## First development task

Prove the smallest native Windows 11 simulation workflow and verify real Oxford and EDAX/TSL input fixtures. Identify a supported EMsoft revision, Windows build/runtime dependencies, EMsoft data files, HDF5 compatibility, and a compatible OpenCL device. Save a reproducible recipe for one cubic CIF through crystal conversion, Monte Carlo transport and dynamical master generation. Check the generated master against a reference detector projection. If native simulation cannot yet run, document the exact blocker and continue independent work on importing masters and the headless CPU demo. Keep native Windows generation as a release gate.

Then build a small end-to-end CLI that imports a fixture and compatible masters, projects a symmetry-reduced dictionary, matches patterns, and exports maps and a manifest. Use this same core from the GUI. Support both Oxford and EDAX/TSL in the first release.

## Scientific and implementation requirements

- Reuse EMsoft for transport and dynamical diffraction, kikuchipy for supported EBSD readers and projection, and orix for orientation symmetry and sampling. Confirm version-specific APIs, data schemas and licence terms before pinning dependencies or distributing binaries and fixtures.
- Make explicit the crystal and sample reference frames, active/passive rotation direction, PC convention, detector pixel axis directions, units, binning, crop and scan order. Use asymmetric or off-center geometry fixtures that reveal sign, transpose and mirroring errors. Preserve scan coordinates for rectangular and hexagonal grids.
- Validate CIF settings, cell units, sites and occupancies against the chosen EMsoft crystal representation. Reject unsupported cases with actionable messages. Keep Monte Carlo and master-pattern stages distinct. Pass executable arguments without a shell and use a separate working directory per job. Verify HDF5 results before promoting them into the cache.
- Keep raw patterns read-only. Make preprocessing, energy selection or weighting, and detector geometry reproducible. Cache masters by crystal, simulation settings and provenance; include detector, grid and preprocessing in any cached dictionary key.
- Use bounded batches for pattern projection and scoring. Retain best candidates per phase and use comparable coverage and processing. Use a CPU reference path and optional CUDA. Preserve documented score tolerance, tie policy and explicit ambiguity. Record batch-size changes and automatic fallbacks in run metadata.
- Keep phase identification, orientation quality and low signal distinct in UI and exports. Compare competing phases with shared calibrated detector geometry and equal optimization effort. Store score margins as diagnostics. Use a separate calibration study before describing any output as a probability.
- Keep the GUI responsive during simulation and indexing. Route long jobs through workers with progress, cancellation and logs. Ensure cancelled or failed outputs cannot be mistaken for valid cached results.
- Keep default tests and the small offline example independent of network, OpenCL and CUDA once dependencies are installed. Run external EMsoft and CUDA integration checks on appropriate runners and report which jobs actually executed. Retain labelled, off-grid validation data separate from the dictionary grid. Make fixture seeds, conversion scripts and per-vendor file checks reproducible.
- Keep local and proprietary lab scans outside the repository. Publish only approved, licence-compatible examples and the required attribution. Keep large raw scans and generated caches out of Git. Maintain an offline installation path for the lab.

## Completion evidence

A release candidate needs a demonstrated native Windows CIF-to-master run, load-to-export evidence for both vendors, a CPU cloud demo, measured GPU/CPU parity on tested hardware, and reports from the synthetic cubic and real-data benchmarks. Include a beginner quick start, vendor export instructions, and scripts that reproduce the benchmark tables. State the validated platforms, file variants and remaining limitations with each release.
