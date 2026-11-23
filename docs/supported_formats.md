# Supported input formats and verification status

"Structural" means tested against files written by the test suite that mimic the vendor layout; "sample"
means kikuchipy's bundled reader samples; "real export" means a representative file from vendor software with a
known software version. Release requires real exports for both vendors (roadmap 2.7).

| Vendor | Format | Variants handled | Geometry source | Verification so far |
| --- | --- | --- | --- | --- |
| Oxford | H5OINA (`.h5oina`) | format version from `Format Version`; raw `Unprocessed Patterns` preferred, `Processed Patterns` fallback (warned); per-point PC averaged for the dictionary (spread recorded) | file (Oxford PC → Bruker) | structural; **real export: pending** |
| Oxford | `.ebsp` | versions 0–5 via kikuchipy; missing patterns handled by kikuchipy | user `--pc` or companion H5OINA | sample; public Al–Si export (in progress) |
| EDAX/TSL | H5EBSD (`.h5`, `.oh5`) | OIM leading-space top-level keys; `SqrGrid` and `HexGrid`; file X/Y positions preserved | file `Pattern Center Calibration` (TSL → Bruker); zeros flagged missing | sample + structural; **real export: pending**; hexagonal layout assumption unverified |
| EDAX/TSL | `.up1` / `.up2` | version 1 (needs nav shape), version ≥ 3 (grid in header, hex flag); version 2 rejected | user `--pc` | sample + structural; **real export: pending** |
| EMsoft | simulated EBSD HDF5 | `EMData/EBSD/EBSDPatterns` with Euler angles | file (EMsoft PC) | sample |
| KikuchiWorkbench | fixture HDF5 | patterns, grid, detector, truth, provenance | file | round-trip tests |
| kikuchipy | h5ebsd | as kikuchipy | file | sample |
| – | `.ang`, `.ctf`, `.osc`, `.cpr/.crc`, pattern-free HDF5 | rejected with export instructions | – | tests |

Master patterns: EMsoft 5 `EMEBSDmaster` HDF5 (Lambert, north/south, one or more energies); verified on
kikuchipy's Ni sample; multi-energy layout tested structurally.

Please send small real exports (with the producing software version) to extend this table; keep proprietary
scans outside the repository and point `KWB_REALDATA_DIR` at them for `pytest -m realdata`.
