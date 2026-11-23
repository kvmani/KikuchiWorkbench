# Quick start

This walks a new user through the bundled offline example, then through their own scan. Nothing here needs
internet access, EMsoft, OpenCL or a GPU once the Python environment is installed.

## 1. Install

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate        # Windows (PowerShell: .venv\Scripts\Activate.ps1)
```

```bash
pip install -e ".[gui]"
```

For an offline lab machine: on a connected machine with the same OS and Python run `python tools/make_wheelhouse.py --out wheels` (records sha256 of every wheel), copy the `wheels`
folder, then `pip install --no-index --find-links wheels "kikuchiworkbench[gui]"`. (A packaged Windows installer is planned
after the native EMsoft workflow is validated.)

## 2. Run the bundled example (command line)

```bash
kwb demo
```

This projects the EMsoft Ni master shipped with kikuchipy onto an off-centre detector with 36 known random
orientations, adds background and Poisson noise, saves the scan as a fixture, re-imports it, indexes it on the
CPU and checks the result against the ground truth. The job folder printed at the end contains:

| File | Content |
| --- | --- |
| `outputs/phase_map.png`, `ipf_z_map.png` | phase and orientation (IPF-Z) maps |
| `outputs/score_map.png`, `signal_map.png` | orientation fit (NCC) and pattern signal (low-signal check) |
| `outputs/results.csv` | one row per point: label, phase, Euler angles, scores per phase, margin |
| `outputs/results.h5` | top candidates per phase (for later inspection) |
| `outputs/manifest.json` | inputs with checksums, conventions, parameters, software, thresholds, events |
| `status.json`, `job.log` | job state and log; `COMPLETE` marks a valid job, `INVALID` a failed/cancelled one |

`kwb demo --two-phase` runs a synthetic Ni vs Cu example with kinematical masters.

## 3. Run the example in the desktop app

```bash
kwb-gui
```

*File → Open bundled example*, then go to **5. Build & match**, tick *Preview ROI only*, press **Run indexing**,
and look at **6. Inspect & export**: click a map pixel to see the measured pattern, the best simulated pattern for
each phase and the candidate table. *Export…* writes the same files as the CLI.

## 4. Your own scan

1. Export the scan **with patterns** (see [vendor export instructions](vendor_export.md)). Orientation-only files
   (`.ang`, `.ctf`, `.osc`, `.cpr/.crc`) are rejected with instructions.
2. Inspect it: `kwb inspect myscan.h5oina`. Check grid, pattern size, PC and the *Geometry* line. If it says
   *missing*, supply the calibrated PC: `kwb inspect myscan.ebsp --pc 0.50 0.70 0.62 --pc-convention oxford`.
3. Get one verified master per candidate phase: `kwb master inspect phase.h5` (EMsoft master HDF5).
4. Write a config (YAML) and run it:

```yaml
scan:
  path: myscan.h5oina
  # geometry: {pc: [0.50, 0.70, 0.62], pc_convention: oxford}
phases:
  - {master: masters/Ni.h5, name: Ni}
  - {master: masters/Cu.h5, name: Cu}
sampling: {resolution_deg: 2.0}
matching: {backend: auto, cache_dictionary: true}
decision: {min_score: 0.10, ambiguity_margin: 0.005}
roi: [0, 20, 0, 20]   # remove to index the full scan
```

```bash
kwb index run.yaml --jobs kwb_jobs
```

Read the `NOTE` lines printed at the end (PC approximation, kinematical masters, tilt or voltage mismatch,
automatic backend fallback). The default decision thresholds are **provisional**; see the benchmark report for
how thresholds are selected and frozen.

## 5. Working faster

* Pick a **preset** in step 5 (or `--preset`): *quick* for a first look, *phase study* when phases are similar.
* **Drag a rectangle** on the map to choose an ROI; press *Estimate resources* before a full run.
* **File → Save project** keeps scan, phases, geometry, settings and run history; reopen it later.
* Step 4's **geometry wizard** draws band lines on the pattern while you adjust the PC.
* **Tools → Batch queue** runs several projects overnight and resumes after an interruption.
* Every run writes **report.html** into its job folder (results page → *Report*).
