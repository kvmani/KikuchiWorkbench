# EMsoft simulation route (CIF → crystal → Monte Carlo → master)

**Status: native execution NOT yet demonstrated.** The adapter (`src/kikuchiworkbench/emsoft/jobs.py`) generates
inputs and runs/verifies stages; it is tested only with mock executables in `tests/mock_emsoft/`. A native
Windows 11 + OpenCL run with a pinned EMsoft release is a release gate (roadmap 3.7). Record the result in
`LEDGER.md` using the checklist at the end of this page.

## Stages

| Stage | Program | Input | Output | Verification before next stage |
| --- | --- | --- | --- | --- |
| 1. Crystal | (KikuchiWorkbench, no `EMmkxtal`) | validated CIF | `<name>.xtal` (HDF5 `CrystalData`) | CIF validator (`kwb cif validate`) |
| 2. Monte Carlo | `EMMCOpenCL` | `EMMCOpenCL.nml` (`&MCCLdata`) | `<name>_mc_mp_<kV>kV.h5` (`EMData/MCOpenCL`) | `accum_e`, `accum_z` present, non-empty histogram |
| 3. Master | `EMEBSDmaster` | `EMEBSDmaster.nml` (`&EBSDmastervars`), `BetheParameters.nml` | same HDF5, adds `EMData/EBSDmaster` | `inspect_master`: Lambert NH/SH, energies, finite non-constant, space group and MC tilt match |

Only after stage 3 verification is the file copied into the master cache, together with the namelists, logs and
`.xtal` (cache key: crystal fields + preset + EMsoft version + route).

## Isolation

EMsoft resolves namelist file names against `EMdatapathname` and `EMXtalFolderpathname` in
`EMsoftConfig.json`, read from `$HOME/.config/EMsoft/` (`%USERPROFILE%\.config\EMsoft\` on Windows). For every job the
adapter writes a job-local `EMsoftConfig.json` (copied from the user's, with the data/xtal/tmp paths pointing at
the job's `work/` folder) and sets `HOME`/`USERPROFILE` for the subprocess only. Executables are started with an
argument list, never through a shell.

**To verify on Windows:** that EMsoft 5 reads `EMsoftConfig.json` from `%USERPROFILE%` in this situation, that
trailing path separators are handled, and the OpenCL kernel location key (`EMsoftpathname`/`EMOpenCLpathname`) is
taken from the copied base config.

## Presets

| Preset | MC grid | Electrons | Energy bins | Master npx | Use |
| --- | --- | --- | --- | --- | --- |
| `quick` | 201 | 2×10⁸ | 19–20 keV | 200 | installation smoke test only |
| `standard` | 501 | 2×10⁹ | 10–20 keV, 1 keV bins | 500 | EMsoft-tutorial-like; not yet validated here |

Both presets are `validated: false` until compared against a reference master.

## Reproducible recipe (to run on the Windows workstation)

```bat
:: 1. Install the pinned EMsoft 5 release and set its bin folder
set KWB_EMSOFT_BIN=C:\EMsoft\bin
kwb emsoft check
:: 2. Validate the crystal and inspect the planned inputs
kwb cif validate tests\data\cif\ni.cif
kwb emsoft plan tests\data\cif\ni.cif plan_ni --preset quick
:: 3. Run MC + master in a job folder; the verified master is cached
kwb emsoft run tests\data\cif\ni.cif --preset quick --jobs kwb_jobs
:: 4. Integration test
pytest -m emsoft
```

Then compare the generated master with the EMsoft reference Ni master (Zenodo 7498645) by projecting both with the
same detector and orientations and recording NCC (planned script: `benchmarks/compare_masters.py`).

## Checklist for the native run (record in LEDGER.md)

- EMsoft release/revision, download URL and checksum; build type (binary release or SDK build)
- Windows build, GPU model, OpenCL platform/driver version, `platid`/`devid` used
- HDF5 library version reported by EMsoft; EMsoft data files present
- Wall time per stage; `kwb master inspect` output for the result
- Projection comparison against the reference (NCC, orientation set, detector)
