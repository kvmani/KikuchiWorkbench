# Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `... contains orientations but no Kikuchi patterns` | You opened `.ang/.ctf/.osc/.cpr`. Export patterns (see vendor_export.md). |
| `Geometry: missing (default placeholder)` / `The scan has no usable projection centre` | The file has no PC (e.g. `.ebsp`, UP files, EDAX files with zero PC). Pass `--pc` with `--pc-convention`, or `scan.geometry` in the config, or a `--companion` H5OINA. |
| `UP version 1 ... does not store map dimensions` | Add `--nav-shape ROWS COLS --step STEP`. |
| `... patterns in file but grid ... implies ...` (hexagonal) | Check grid type; hexagonal assumes `ncols_even = ncols_odd - 1`; use `--grid-type points` to read as a list. |
| `CIF rejected: two origin choices` | Write the symbol with `:1` or `:2` or include the symmetry-operator loop. |
| `Rhombohedral axes are not supported` | Convert the CIF to hexagonal axes. |
| `master slice is constant` | The master file is empty/failed; regenerate it. |
| NOTE `Competing kinematical masters include different reflector families` | Regenerate the kinematical masters with the same `max_hkl_sq`. |
| NOTE `pc_approximation` | The scan PC varies; the dictionary uses the mean PC. Use a smaller ROI if the spread is large. |
| NOTE `fallback` / `batch_size_change` | GPU memory was insufficient; the run continued with smaller batches or CPU (recorded). |
| Everything is `ambiguous` | Phase margins are below `decision.ambiguity_margin`. This is expected for very similar phases; see the benchmark report before lowering the threshold. |
| GUI does not start on Linux (`libEGL.so.1`) | Install `libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3`. |
| `EMsoft executable ... not found` | Set `KWB_EMSOFT_BIN` to the EMsoft `bin` folder; run `kwb emsoft check`. |
