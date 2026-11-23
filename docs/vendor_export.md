# Exporting scans with patterns

KikuchiWorkbench needs the recorded Kikuchi patterns. Orientation maps alone are not enough.

> These instructions describe the export options to look for; menu names differ between software versions.
> They have **not yet been verified** against representative exports from the lab (roadmap 2.7). Please record
> the software version that produced each file you use.

## Oxford Instruments (AZtec / AZtecCrystal)

* Preferred: **H5OINA** with patterns. When available, enable *unprocessed (raw) patterns*; KikuchiWorkbench reads
  `Unprocessed Patterns` in preference to `Processed Patterns` and warns if only processed patterns exist.
* Alternative: **`.ebsp`** binary pattern file. It has no detector calibration; supply the PC and tilt from the
  project (or export a pattern-free H5OINA of the same scan and pass it as `--companion`).
* Not usable alone: `.ctf`, `.cpr/.crc` (orientation data only).

## EDAX / TSL (OIM Analysis, APEX)

* Preferred: **H5EBSD** (`.h5` / `.oh5`) with patterns included. Square and hexagonal grids are supported; the
  PC is read from *Pattern Center Calibration* (`x-star`, `y-star`, `z-star`). If these are zero or missing the
  scan is flagged and you must supply the PC (`--pc ... --pc-convention tsl`).
* Alternative: **`.up1` / `.up2`** pattern files. Version 1 files store no map size: pass `--nav-shape ROWS COLS`
  and `--step`. Version ≥ 3 store the grid. Hexagonal grids assume `ncols_even = ncols_odd − 1`.
* Not usable alone: `.ang`, `.osc`.

## Geometry conventions

See [conventions](conventions.md). Pass the PC in the vendor's own convention with `--pc-convention tsl` or
`oxford`; it is converted to the internal Bruker convention and recorded in the manifest.
