# Reference frames and conventions

This document is the contract for geometry inside KikuchiWorkbench. Code lives in
`src/kikuchiworkbench/conventions.py`; tests in `tests/test_conventions.py` use an asymmetric, off-centre,
non-square geometry and cross-check every formula against kikuchipy 0.14.2.

## Detector pixels

* Patterns are stored as `patterns[point, row, col]`.
* Row index increases **downwards**, column index increases **to the right**, as seen from the sample looking at
  the scintillator (kikuchipy convention). Pixel centres sit at integer indices.
* Shapes are in *binned* pixels; `binning` and unbinned `px_size` (µm) are stored separately.
* Crop: not applied by importers. Any crop/mask becomes part of the recorded preprocessing pipeline.

## Projection centre (PC)

Internal convention: **Bruker / kikuchipy** `(PCx, PCy, PCz)`

| Quantity | Definition |
| --- | --- |
| PCx | fraction of detector width from the left edge (column 0) |
| PCy | fraction of detector height from the top edge (row 0) |
| PCz | sample–scintillator distance as a fraction of detector height |

Conversions (N<sub>x</sub>, N<sub>y</sub> binned columns/rows, b binning, δ unbinned pixel size, r = N<sub>x</sub>/N<sub>y</sub>):

| Source | To Bruker | Notes |
| --- | --- | --- |
| EDAX/TSL `(x*, y*, z*)` | PCx = x*, PCy = 1 − y*, PCz = z* · min(N<sub>x</sub>,N<sub>y</sub>)/N<sub>y</sub> | Origin bottom-left. **Non-square detectors: follows kikuchipy; verify on a real non-square TSL export.** |
| Oxford `(PCx, PCy, DD)` | PCx = PCx<sub>O</sub>, PCy = 1 − PCy<sub>O</sub> · r, PCz = DD · r | All Oxford values are fractions of detector width, origin bottom-left. |
| EMsoft ≥ 5 `(xpc, ypc, L)` | PCx = ½ − xpc/(N<sub>x</sub> b), PCy = ½ − ypc/(N<sub>y</sub> b), PCz = L/(N<sub>y</sub> b δ) | xpc, ypc in unbinned pixels from the detector centre, L in µm. |
| EMsoft 4 | as EMsoft 5 with xpc → −xpc | |

Every imported scan records `geometry_source`: `file`, `user`, or `missing (default placeholder)`. A missing or
implausible PC (e.g. all zeros, as in some EDAX exports without calibration) is flagged and must be supplied before
indexing.

## Orientations

* orix `Rotation`/`Orientation` objects: **passive** rotations taking the sample frame to the crystal frame
  (MTEX/orix convention), quaternions with non-negative scalar part.
* Euler angles: Bunge ZXZ `(φ1, Φ, φ2)`; radians internally, **degrees** in exports.
* Sample frame (kikuchipy/EDAX): X to the right on the map (scan column direction), Y down the map (scan row
  direction), Z into the sample. Detector tilt, azimuthal and twist angles and sample tilt follow kikuchipy
  `EBSDDetector` (degrees).
* Vendor orientations are stored only as optional comparisons; frame differences between vendor exports and the
  internal sample frame must be checked on real data before they are compared quantitatively.

## Scan grids and order

* Points are stored in **acquisition order**: row-major, left-to-right, top-to-bottom.
* Square grid: `n = nrows × ncols`; point `i` → `(row, col) = divmod(i, ncols)`.
* Hexagonal grid (EDAX/TSL): odd rows (1st, 3rd, …) have `ncols` points; even rows have `ncols − 1` points shifted
  right by half a step; row spacing `step_y = step_x · √3/2`. **Assumption to verify on a real EDAX hexagonal
  export.** Map display places hex points in a `(nrows, ncols)` array with empty cells.
* Coordinates from the file (EDAX `X Position`/`Y Position`) are preserved when present; otherwise nominal grid
  coordinates are generated and `coordinates_source` says so.
* Missing points are tracked with a per-point `valid` mask.

## Units

| Quantity | Unit |
| --- | --- |
| Lengths, steps, pixel size | µm |
| Beam voltage | kV |
| Angles in exports and user input | degrees |
| Lattice parameters | Å in user-facing input; nm where EMsoft requires it (converted explicitly) |

## Validation against EMsoft's own detector projection

`benchmarks/emsoft_projection_check.py` (also run as a test) projects an EMsoft Ni master through the workbench
(master import → EMsoft 4/5 PC conversion → orix rotation from TSL Euler angles → kikuchipy projection) and compares
with the pattern EMsoft 4.2 `EMEBSD` computed itself (`EBSD_TEST_Ni.h5`: 640 × 480 px, xpc = ypc = 20 px,
L = 15000 µm, δ = 50 µm, detector tilt 10°, Euler (120°, 45°, 60°)).

| Projection | NCC vs EMsoft (Zenodo 7498645 master) | NCC (kikuchipy small 8-bit master) |
| --- | --- | --- |
| documented conventions | **0.99996** | **0.947** |
| wrong xpc sign (EMsoft 5 vs 4) | 0.001 | −0.010 |
| vertical mirror | −0.011 | −0.014 |
| horizontal mirror | −0.037 | −0.041 |
| φ1 + 90° (HKL vs TSL Euler convention) | 0.077 | 0.090 |
| φ1 ↔ φ2 swapped | 0.030 | 0.030 |

Results: `benchmarks/results/emsoft_projection_2026-11-23/`.
