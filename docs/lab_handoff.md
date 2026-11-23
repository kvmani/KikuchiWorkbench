# Lab hand-off: checks that need your hardware or data

These release-gate items cannot run in the cloud container used so far. Each has a script or test ready; run it,
then paste the output (or the generated JSON/report) into a new `LEDGER.md` entry.

| # | Item (roadmap) | Needs | Command | Record |
| --- | --- | --- | --- | --- |
| 1 | Native EMsoft CIF → MC → master (3.7, release gate) | Windows 11, pinned EMsoft 5 release, OpenCL GPU | `set KWB_EMSOFT_BIN=C:\EMsoft\bin` · `kwb emsoft check` · `kwb emsoft run tests\data\cif\ni.cif --preset quick` · `pytest -m emsoft` | EMsoft revision + checksum, GPU/driver, `platid/devid`, wall time per stage, `kwb master inspect` of the result (see docs/emsoft.md checklist) |
| 2 | Generated master vs reference projection (3.7) | output of 1 | `python benchmarks/emsoft_projection_check.py --master <cached master.h5>` | NCC table (expect ≥ 0.95 for "documented", ≈ 0 for wrong conventions) |
| 3 | CPU/GPU parity and memory (5.6) | NVIDIA GPU, `pip install -e ".[cuda]"` | `python benchmarks/gpu_cpu_parity.py --n-side 20 --resolution 3` and again with `--vram-fraction 0.25` (≈ 4 GB card) · `pytest -m cuda` | `parity.json` (ΔNCC, best-index agreement, times, peak VRAM, fallback events) |
| 4 | EDAX/TSL real export (2.7, 5.7) | small pattern-bearing H5EBSD/`.oh5` or `.up1/.up2` + OIM version + calibration | add it to `realdata.yaml` (see `tests/test_realdata.py`), `pytest -m realdata`, then `kwb inspect` and a ROI `kwb index` | software version, grid type (square/hex), PC as read, maps from the ROI |
| 5 | Oxford real export from the lab (2.7) | H5OINA with unprocessed patterns + AZtec version | as 4 | as 4; confirm raw dataset chosen and binning |
| 6 | Windows GUI on a workstation (6.8) | Windows 11 with display | `kwb-gui` → *File → Open bundled example* → step 5 *Run indexing* (ROI) → step 6 click pixels → *Export…*; also cancel a run | screenshot, any errors from the log panel |
| 7 | Offline install (7.x) | machine without internet | follow docs/quickstart.md §1 offline steps, then `kwb demo` | pass/fail, missing wheels |

Keep lab scans outside the repository (`KWB_REALDATA_DIR`). If a check fails, record the exact error and the
command — a documented blocker is useful evidence.
