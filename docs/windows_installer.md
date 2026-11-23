# Offline Windows installer (preparation)

Status: **prepared, not yet built on Windows.** The PyInstaller spec was verified on Linux: the one-folder bundle
(≈ 720 MB) builds, the frozen `kwb demo` passes in a clean environment (no Python on PATH) and the frozen GUI
starts. Building and signing on Windows is a release step after the native EMsoft gate (roadmap 3.7, 8.10).

Build outputs are never committed (no binary files in Git).

## Build on the Windows workstation

```bat
python -m venv kwb-build
kwb-build\Scripts\activate
pip install -e ".[gui]" pyinstaller
python packaging\build_bundle.py --out C:\kwb_build
```

Check the bundle before packaging:

```bat
C:\kwb_build\dist\KikuchiWorkbench\kwb.exe demo --rows 3 --cols 3 --resolution 6
C:\kwb_build\dist\KikuchiWorkbench\KikuchiWorkbench.exe
```

Then compile the installer with [Inno Setup](https://jrsoftware.org/isinfo.php):

```bat
iscc /DBundleDir=C:\kwb_build\dist\KikuchiWorkbench packaging\kikuchiworkbench.iss
```

The installer copies the bundle to Program Files, adds Start-menu entries for the GUI and a `kwb` prompt, and
offers to run the offline self-check demo after installation.

## Before distributing

* Choose the application licence (open decision) and review bundled licences — kikuchipy and orix are
  GPL-3.0, PySide6 is LGPL-3.0 (see docs/THIRD_PARTY.md).
* Sign the executables and installer with the lab's code-signing certificate.
* EMsoft is **not** bundled; point `KWB_EMSOFT_BIN` to the separately installed, pinned EMsoft release.
* Record the Windows build, Python version and the demo result in LEDGER.md.
