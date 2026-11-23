# Third-party software, data and licences

The licence of KikuchiWorkbench itself is an **open decision** (repository owner). Until it is chosen, do not
redistribute binaries or bundles. The table records what the code depends on and what must be checked before
distributing anything.

| Component | Use | Licence (to confirm for the pinned version) | Redistribution notes |
| --- | --- | --- | --- |
| kikuchipy 0.14.x | readers, master projection, kinematical simulator | GPL-3.0-or-later | A bundled installer that includes kikuchipy must comply with GPL-3.0; this affects the choice of application licence. |
| orix 0.15.x | orientations, symmetry, sampling, IPF colours | GPL-3.0-or-later | as above |
| diffsims / diffpy.structure | structure factors / CIF parsing | GPL-3.0 / BSD-3-Clause | |
| h5py, numpy, scipy, matplotlib | I/O and numerics | BSD-style / PSF-style | |
| PySide6 | GUI | LGPL-3.0 (Qt for Python) | dynamic linking; ship licence texts |
| PyTorch (optional) | CUDA matching | BSD-style; CUDA runtime under NVIDIA EULA | |
| EMsoft 5 | MC + dynamical masters (external executables) | BSD-3-Clause (EMsoft); bundled HDF5/OpenCL components have their own terms | Do not bundle until the pinned release's licence files are reviewed. |

## Data used in tests

* kikuchipy's packaged sample files (Ni master `ni_mc_mp_20kv_uint8_gzip_opts9.h5`, reader fixtures) are read from
  the installed kikuchipy package at test time and are **not** copied into this repository.
* `tests/data/cif/*.cif` were written for this project from public lattice parameters (Ni 3.524 Å, Cu 3.615 Å,
  Si 5.431 Å); negative controls are deliberately malformed.
* Planned external benchmark data (not in Git): EMsoft Ni reference master (Zenodo 7498645), public Oxford Al–Si
  `.ebsp` and Al/Si masters (Zenodo 20290635). Check their licences and attribution requirements before use in
  published reports.
