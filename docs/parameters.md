# Parameter reference and CLI reproduction guide

Every run writes `config.json` (the exact configuration) and `outputs/manifest.json` (what actually happened,
including automatic changes). Re-running `kwb index config.json` reproduces a run; compare the manifests.

## Configuration file (`kwb index run.yaml`)

| Key | Default | Meaning |
| --- | --- | --- |
| `scan.path` | – | scan file (relative paths are resolved against the config file) |
| `scan.scan_group` | first with patterns | HDF5 scan group (H5OINA `1`, EDAX `Scan 1`) |
| `scan.prefer_raw` | `true` | H5OINA: read `Unprocessed Patterns` when present |
| `scan.nav_shape`, `scan.step` | from file | map rows/cols and step (µm), required for UP v1 |
| `scan.grid_type` | from file | `square`, `hexagonal` or `points` |
| `scan.geometry` | from file | `{pc: [..], pc_convention: bruker|tsl|oxford|emsoft|emsoft4, binning, px_size, sample_tilt, tilt}` |
| `scan.companion` | – | H5OINA providing geometry for an `.ebsp` |
| `phases[]` | – | `{master: path, name: str, energy: max|<keV>|weighted}` |
| `sampling.resolution_deg` | 3.0 | cubochoric fundamental-zone step, **identical for all phases** |
| `preprocessing` | static (scan mean) + dynamic (σ = width/8) subtraction | list of steps, see below |
| `matching.backend` | `auto` | `auto`, `cpu`, `gpu` |
| `matching.top_k` | 5 | candidates kept per phase |
| `matching.dictionary_chunk` | 2000 | orientations projected per batch |
| `matching.pattern_chunk` | 2048 | experimental patterns per score block (halved automatically on OOM) |
| `matching.cache_dictionary` | `false` | store verified dictionaries in the cache |
| `matching.cache_dir` | user cache | `KWB_CACHE_DIR` or `%LOCALAPPDATA%\KikuchiWorkbench\cache` / `~/.cache/kikuchiworkbench` |
| `refinement.enabled` | `false` | equal-budget orientation refinement for every phase |
| `refinement.trust_region_deg` | grid step | ± search window per Euler angle |
| `refinement.maxeval`, `rtol`, `n_starts`, `method_kwargs` | 300, 1e-4, 1, Nelder-Mead | refinement budget |
| `decision.min_score` | 0.10 | NCC below which a pixel is *unindexed* |
| `decision.ambiguity_margin` | 0.005 | phase margin at or below which a pixel is *ambiguous* |
| `decision.min_signal` | none | signal metric below which a pixel is *low signal* |
| `decision.provenance` | "provisional" | record where thresholds came from (e.g. frozen dev selection) |
| `roi` | – | `[row0, row1, col0, col1]` half-open, for previews |
| `allow_placeholder_geometry` | `false` | allow indexing without a calibrated PC (demos only) |

### Preprocessing steps

| Step | Applied to | Parameters |
| --- | --- | --- |
| `static_background` | experimental | `mode: subtract|divide`, `source: scan_mean|file` |
| `dynamic_background` | experimental | `sigma` (px) or `sigma_frac` (of width), `mode: subtract|divide` |
| `bin` | both | `factor` |
| `mask` | both | `shape: circle`, `radius_frac` |

## CLI

| Command | Purpose |
| --- | --- |
| `kwb inspect SCAN [--pc .. --pc-convention ..] [--json]` | format, grid, detector, warnings |
| `kwb cif validate FILE`, `kwb cif xtal FILE OUT` | crystal validation / EMsoft crystal file |
| `kwb master inspect FILE`, `kwb master add FILE` | verify / cache a master |
| `kwb kinematical CIF OUT [--kv --half-size]` | kinematical master (synthetic use only) |
| `kwb emsoft check|plan|run` | EMsoft adapter |
| `kwb index CONFIG [--backend]` | indexing job |
| `kwb demo [--two-phase]` | offline demo with self-check |
| `kwb gui` / `kwb-gui` | desktop application |

## Outputs

`outputs/results.csv` columns: `index, row, col, x_um, y_um, label, phase, phase_name, phi1_deg, Phi_deg,
phi2_deg, best_score, runner_up_phase, runner_up_score, phase_margin, phase_tie, signal, low_signal,
best_phase_any, score_<phase>...`. Euler angles are Bunge, degrees, of the best orientation of `best_phase_any`.
