# PyInstaller spec: one-folder bundle with the GUI (KikuchiWorkbench) and the CLI (kwb).
# Build:  python packaging/build_bundle.py      (output goes OUTSIDE the repository; no binaries in Git)
# -*- mode: python -*-
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

block_cipher = None
datas, binaries, hiddenimports = [], [], []
# rsciio is the import name of the "rosettasciio" distribution (HyperSpy I/O plug-ins)
for pkg in ("kikuchipy", "orix", "diffsims", "diffpy.structure", "hyperspy", "rsciio", "numba",
            "kikuchiworkbench", "pooch", "CifFile"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # optional packages
        print(f"spec: skipping {pkg}: {e}")
hiddenimports += collect_submodules("scipy") + ["yaml"]
# HyperSpy/kikuchipy discover plug-ins through package metadata (entry points)
for dist in ("hyperspy", "rosettasciio", "kikuchipy", "orix", "kikuchiworkbench", "diffsims"):
    try:
        datas += copy_metadata(dist)
    except Exception as e:
        print(f"spec: no metadata for {dist}: {e}")

SRC = os.path.join(SPECPATH, "entry_points.py")

common = dict(pathex=[], binaries=binaries, datas=datas, hiddenimports=hiddenimports, hookspath=[],
              runtime_hooks=[], excludes=["torch", "tkinter", "IPython", "jupyter"], cipher=block_cipher,
              noarchive=False)
a_gui = Analysis([SRC], **common)
a_cli = Analysis([os.path.join(SPECPATH, "entry_cli.py")], **common)
pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)
pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)
exe_gui = EXE(pyz_gui, a_gui.scripts, [], exclude_binaries=True, name="KikuchiWorkbench", console=False)
exe_cli = EXE(pyz_cli, a_cli.scripts, [], exclude_binaries=True, name="kwb", console=True)
coll = COLLECT(exe_gui, a_gui.binaries, a_gui.zipfiles, a_gui.datas,
               exe_cli, a_cli.binaries, a_cli.zipfiles, a_cli.datas, name="KikuchiWorkbench")
