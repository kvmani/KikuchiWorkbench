"""EMsoft 5 job adapter: CIF -> .xtal -> Monte Carlo (EMMCOpenCL) -> master (EMEBSDmaster).

Design (see ``docs/emsoft.md``):

* The crystal file is written by :mod:`kikuchiworkbench.crystal.xtal` (no
  interactive ``EMmkxtal``).
* Monte Carlo and master generation are separate stages with separate
  namelists, logs and verification. The master stage starts only from a
  verified MC file.
* Each job runs in its own working directory. EMsoft resolves namelist paths
  against ``EMdatapathname``/``EMXtalFolderpathname`` from ``EMsoftConfig.json``
  in ``$HOME/.config/EMsoft`` (``%USERPROFILE%`` on Windows). The adapter writes a
  job-local config and points HOME/USERPROFILE at the job folder for the
  subprocess, so the user's own configuration is never modified.
* Executables are started with an argument list (never through a shell),
  with cancellation by terminate/kill.
* Results are promoted into the master cache only after HDF5 verification.

**Status:** namelist content follows the EMsoft 5.0 templates bundled with
kikuchipy; execution has only been tested with mock executables. A native
Windows 11 + OpenCL run is a release gate (roadmap 3.7).
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import h5py

from ..cache import ArtifactCache
from ..crystal.cif import CrystalModel
from ..crystal.xtal import write_xtal
from ..errors import EMsoftError, JobCancelled
from ..masters.importer import inspect_master

MC_EXE = "EMMCOpenCL"
MASTER_EXE = "EMEBSDmaster"


@dataclass
class EMsoftPreset:
    """Simulation settings. Units: kV, degrees, nm, keV."""

    name: str = "quick"
    voltage_kV: float = 20.0
    sample_tilt_deg: float = 70.0
    omega_deg: float = 0.0
    mc_numsx: int = 501  # MC Lambert grid (odd)
    totnum_el: int = 2_000_000_000
    multiplier: int = 1
    num_el: int = 10
    globalworkgrpsz: int = 150
    platid: int = 1
    devid: int = 1
    ehistmin_keV: float = 10.0
    ebinsize_keV: float = 1.0
    depthmax_nm: float = 100.0
    depthstep_nm: float = 1.0
    master_npx: int = 500
    dmin_nm: float = 0.05
    nthreads: int = 0
    bethe_c1: float = 4.0
    bethe_c2: float = 8.0
    bethe_c3: float = 50.0
    bethe_sgdbdiff: float = 1.0
    validated: bool = False  # set True only for presets checked against a reference

    PRESETS = {}  # filled below

    @classmethod
    def named(cls, name: str) -> EMsoftPreset:
        if name not in cls.PRESETS:
            raise EMsoftError(f"Unknown EMsoft preset {name!r}; available: {sorted(cls.PRESETS)}")
        return copy.deepcopy(cls.PRESETS[name])

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}

    def validate(self) -> None:
        if self.mc_numsx % 2 != 1:
            raise EMsoftError("mc_numsx must be odd (EMsoft requirement).")
        if not 1.0 <= self.voltage_kV <= 40.0:
            raise EMsoftError("voltage_kV must be within 1-40 kV.")
        if not 0 <= self.sample_tilt_deg <= 90:
            raise EMsoftError("sample_tilt_deg must be within 0-90 degrees.")
        if self.ehistmin_keV >= self.voltage_kV:
            raise EMsoftError("ehistmin_keV must be below the beam energy.")
        if self.totnum_el <= 0 or self.totnum_el > 2**31 - 1:
            raise EMsoftError("totnum_el must be in 1..2^31-1; use multiplier for more electrons.")


EMsoftPreset.PRESETS = {
    # quick: smoke tests on a new installation (minutes on a laptop GPU); not for science
    "quick": EMsoftPreset(name="quick", mc_numsx=201, totnum_el=200_000_000, ehistmin_keV=19.0,
                          master_npx=200, depthmax_nm=100.0),
    # standard: EMsoft tutorial-like settings, single energy bin at the beam energy
    "standard": EMsoftPreset(name="standard", mc_numsx=501, totnum_el=2_000_000_000, ehistmin_keV=10.0,
                             master_npx=500),
}


def _fbool(v: bool) -> str:
    return ".TRUE." if v else ".FALSE."


def mc_namelist(preset: EMsoftPreset, xtalname: str, dataname: str) -> str:
    p = preset
    return f""" &MCCLdata
 mode = 'full',
 xtalname = '{xtalname}',
 numsx = {p.mc_numsx},
 sig = {p.sample_tilt_deg:.4f},
 omega = {p.omega_deg:.4f},
 sigstart = 0.0,
 sigend = 30.0,
 sigstep = 2.0,
 ivolx = 1001,
 ivoly = 1001,
 ivolz = 101,
 ivolstepx = 1.0,
 ivolstepy = 1.0,
 ivolstepz = 1.0,
 num_el = {p.num_el},
 platid = {p.platid},
 devid = {p.devid},
 globalworkgrpsz = {p.globalworkgrpsz},
 totnum_el = {p.totnum_el},
 multiplier = {p.multiplier},
 EkeV = {p.voltage_kV:.4f}D0,
 Ehistmin = {p.ehistmin_keV:.4f}D0,
 Ebinsize = {p.ebinsize_keV:.4f}D0,
 depthmax = {p.depthmax_nm:.4f}D0,
 depthstep = {p.depthstep_nm:.4f}D0,
 dataname = '{dataname}',
 Notify = 'Off',
 /
"""


def master_namelist(preset: EMsoftPreset, energyfile: str, bethe_file: str) -> str:
    p = preset
    return f""" &EBSDmastervars
 dmin = {p.dmin_nm:.4f},
 npx = {p.master_npx},
 nthreads = {p.nthreads},
 energyfile = '{energyfile}',
 BetheParametersFile = '{bethe_file}',
 Notify = 'Off',
 copyfromenergyfile = 'undefined',
 h5copypath = 'undefined',
 restart = {_fbool(False)},
 uniform = {_fbool(False)},
 useEnergyWeighting = {_fbool(False)},
 /
"""


def bethe_namelist(preset: EMsoftPreset) -> str:
    p = preset
    return f""" &Bethelist
 c1 = {p.bethe_c1:.2f},
 c2 = {p.bethe_c2:.2f},
 c3 = {p.bethe_c3:.2f},
 sgdbdiff = {p.bethe_sgdbdiff:.2f}
 /
"""


def parse_namelist(text: str) -> dict:
    """Minimal Fortran namelist parser (single group) for verification and tests."""
    out: dict = {}
    for raw in text.splitlines():
        line = raw.split("!")[0].strip().rstrip(",")
        if not line or line.startswith("&") or line == "/":
            continue
        if "=" not in line:
            continue
        k, v = (s.strip() for s in line.split("=", 1))
        v = v.rstrip(",").strip()
        if v.startswith("'") and v.endswith("'"):
            out[k] = v[1:-1]
        elif v.upper() in (".TRUE.", ".FALSE."):
            out[k] = v.upper() == ".TRUE."
        else:
            try:
                out[k] = int(v)
            except ValueError:
                out[k] = float(v.upper().replace("D", "E"))
    return out


# --------------------------------------------------------------------------- installation


@dataclass
class EMsoftInstall:
    """Location of EMsoft executables and the base EMsoftConfig.json values.

    ``launcher`` is an optional command prefix (used by tests to run mock
    executables through the Python interpreter).
    """

    bin_dir: str
    base_config: dict = field(default_factory=dict)
    launcher: list[str] = field(default_factory=list)
    version: str | None = None

    @classmethod
    def discover(cls) -> EMsoftInstall | None:
        cand = os.environ.get("KWB_EMSOFT_BIN")
        if not cand:
            exe = shutil.which(MC_EXE)
            cand = str(Path(exe).parent) if exe else None
        if not cand:
            return None
        base = {}
        cfg = Path.home() / ".config" / "EMsoft" / "EMsoftConfig.json"
        if cfg.exists():
            try:
                base = json.loads(cfg.read_text())
            except json.JSONDecodeError:
                base = {}
        return cls(bin_dir=cand, base_config=base)

    def exe(self, name: str) -> list[str]:
        b = Path(self.bin_dir)
        for cand in (b / name, b / f"{name}.exe", b / f"{name}.py"):
            if cand.exists():
                return [*self.launcher, str(cand)]
        raise EMsoftError(
            f"EMsoft executable {name} not found in {self.bin_dir}.",
            "Set KWB_EMSOFT_BIN to the EMsoft 'bin' folder of the pinned release.",
        )

    def check(self) -> dict:
        report = {"bin_dir": self.bin_dir, "executables": {}}
        for name in (MC_EXE, MASTER_EXE):
            try:
                report["executables"][name] = self.exe(name)[-1]
            except EMsoftError as e:
                report["executables"][name] = f"MISSING: {e.message}"
        return report


# --------------------------------------------------------------------------- plan


@dataclass
class MasterJobPlan:
    work_dir: Path
    model: CrystalModel
    preset: EMsoftPreset
    xtal: Path
    mc_nml: Path
    master_nml: Path
    bethe_nml: Path
    data_file: Path  # MC output, then also master output (EMsoft writes both into energyfile)
    config_home: Path

    def describe(self) -> dict:
        return {
            "work_dir": str(self.work_dir),
            "crystal": self.model.key_fields(),
            "preset": self.preset.to_dict(),
            "files": {"xtal": str(self.xtal), "mc_nml": str(self.mc_nml),
                      "master_nml": str(self.master_nml), "bethe_nml": str(self.bethe_nml),
                      "data_file": str(self.data_file)},
            "stages": [
                {"stage": "monte_carlo", "program": MC_EXE, "args": [self.mc_nml.name]},
                {"stage": "master", "program": MASTER_EXE, "args": [self.master_nml.name]},
            ],
            "status": "planned; native execution not yet validated (roadmap 3.7)",
        }

    def cache_fields(self, emsoft_version: str | None) -> dict:
        return {"crystal": self.model.key_fields(), "preset": self.preset.to_dict(),
                "emsoft_version": emsoft_version, "route": "EMMCOpenCL+EMEBSDmaster"}


def plan_master_job(model: CrystalModel, preset: EMsoftPreset, work_dir: str | os.PathLike) -> MasterJobPlan:
    preset.validate()
    wd = Path(work_dir)
    wd.mkdir(parents=True, exist_ok=True)
    name = model.name.lower().replace(" ", "_")
    xtal = write_xtal(model, wd / f"{name}.xtal")
    data = wd / f"{name}_mc_mp_{preset.voltage_kV:g}kV.h5"
    mc = wd / "EMMCOpenCL.nml"
    mc.write_text(mc_namelist(preset, xtal.name, data.name))
    bethe = wd / "BetheParameters.nml"
    bethe.write_text(bethe_namelist(preset))
    mp = wd / "EMEBSDmaster.nml"
    mp.write_text(master_namelist(preset, data.name, bethe.name))
    home = wd / "emsoft_home"
    (home / ".config" / "EMsoft").mkdir(parents=True, exist_ok=True)
    (wd / "plan.json").write_text(json.dumps({"crystal": model.to_dict(), "preset": preset.to_dict()},
                                             indent=2, default=str))
    return MasterJobPlan(wd, model, preset, xtal, mc, mp, bethe, data, home)


def job_config(base: dict, work_dir: Path) -> dict:
    cfg = dict(base)
    wd = str(work_dir.resolve())
    sep = os.sep
    cfg["EMdatapathname"] = wd + sep
    cfg["EMXtalFolderpathname"] = wd + sep
    cfg["EMtmppathname"] = wd + sep
    cfg.setdefault("Develop", "No")
    cfg.setdefault("Release", "Yes")
    return cfg


# --------------------------------------------------------------------------- run


def verify_mc_file(path: Path) -> dict:
    if not path.exists():
        raise EMsoftError(f"Monte Carlo output {path.name} was not written.")
    with h5py.File(path, "r") as h:
        if "EMData/MCOpenCL" not in h:
            raise EMsoftError(f"{path.name} has no EMData/MCOpenCL group (Monte Carlo failed?).")
        g = h["EMData/MCOpenCL"]
        for k in ("accum_e", "accum_z"):
            if k not in g:
                raise EMsoftError(f"{path.name}: EMData/MCOpenCL/{k} missing.")
        total = float(g["accum_e"][()].sum())
        if total <= 0:
            raise EMsoftError(f"{path.name}: Monte Carlo energy histogram is empty.")
        version = None
        if "EMheader/MCOpenCL/Version" in h:
            v = h["EMheader/MCOpenCL/Version"][()]
            version = (v[0] if hasattr(v, "__len__") else v)
            version = version.decode() if isinstance(version, bytes) else str(version)
    return {"accum_e_total": total, "emsoft_version": version}


def _run_stage(args: list[str], cwd: Path, env: dict, log_path: Path, cancel=None,
               timeout_s: float | None = None, poll_s: float = 0.2) -> int:
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write(f"# args: {args}\n# cwd: {cwd}\n")
        log.flush()
        proc = subprocess.Popen(args, cwd=str(cwd), env=env, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, shell=False)
        t0 = time.monotonic()
        while True:
            rc = proc.poll()
            if rc is not None:
                return rc
            if cancel is not None and cancel.cancelled:
                proc.terminate()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise JobCancelled("EMsoft stage cancelled")
            if timeout_s is not None and time.monotonic() - t0 > timeout_s:
                proc.kill()
                raise EMsoftError(f"{Path(args[-2] if len(args) > 1 else args[0]).name} timed out "
                                  f"after {timeout_s} s")
            time.sleep(poll_s)


def run_master_job(plan: MasterJobPlan, install: EMsoftInstall, cache: ArtifactCache | None = None,
                   job=None, timeout_s: float | None = None) -> dict:
    """Run MC then master; verify both; optionally promote the master into ``cache``."""
    env = dict(os.environ)
    home = plan.config_home
    (home / ".config" / "EMsoft" / "EMsoftConfig.json").write_text(
        json.dumps(job_config(install.base_config, plan.work_dir), indent=2))
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    cancel = job.cancel_token if job is not None else None
    record: dict = {"plan": plan.describe(), "stages": []}

    def progress(f, msg):
        if job is not None:
            job.progress(f, msg)

    progress(0.05, "EMsoft Monte Carlo (EMMCOpenCL)")
    rc = _run_stage([*install.exe(MC_EXE), plan.mc_nml.name], plan.work_dir, env,
                    plan.work_dir / "EMMCOpenCL.log", cancel, timeout_s)
    if rc != 0:
        raise EMsoftError(f"EMMCOpenCL exited with code {rc}; see {plan.work_dir / 'EMMCOpenCL.log'}",
                          "Check the OpenCL platform/device ids (platid/devid) and the EMsoft log.")
    mc = verify_mc_file(plan.data_file)
    record["stages"].append({"stage": "monte_carlo", "returncode": rc, "verification": mc})

    progress(0.5, "EMsoft dynamical master (EMEBSDmaster)")
    rc = _run_stage([*install.exe(MASTER_EXE), plan.master_nml.name], plan.work_dir, env,
                    plan.work_dir / "EMEBSDmaster.log", cancel, timeout_s)
    if rc != 0:
        raise EMsoftError(f"EMEBSDmaster exited with code {rc}; see {plan.work_dir / 'EMEBSDmaster.log'}")
    info = inspect_master(plan.data_file)
    if info.space_group != plan.model.space_group:
        raise EMsoftError(f"Master space group {info.space_group} differs from the crystal "
                          f"({plan.model.space_group}).")
    if info.sample_tilt_deg is not None and abs(info.sample_tilt_deg - plan.preset.sample_tilt_deg) > 1e-3:
        raise EMsoftError("Master MC tilt does not match the requested sample tilt.")
    record["stages"].append({"stage": "master", "returncode": rc, "verification": {
        "sha256": info.sha256, "checks": info.checks, "warnings": info.warnings}})
    record["master_info"] = info.to_dict()
    version = mc.get("emsoft_version") or info.emsoft_version
    if cache is not None:
        fields = plan.cache_fields(version)
        with cache.stage() as st:
            shutil.copy2(plan.data_file, st / "master.h5")
            for f in ("EMMCOpenCL.nml", "EMEBSDmaster.nml", "BetheParameters.nml", "EMMCOpenCL.log",
                      "EMEBSDmaster.log", plan.xtal.name):
                if (plan.work_dir / f).exists():
                    shutil.copy2(plan.work_dir / f, st / f)

            def verify(d: Path) -> dict:
                again = inspect_master(d / "master.h5")
                if again.sha256 != info.sha256:
                    raise EMsoftError("Master changed while copying into cache.")
                return {"sha256": again.sha256}

            entry = cache.promote(st, "masters", fields, verify, {"emsoft_record": record})
        record["cached_master"] = str(entry / "master.h5")
    progress(1.0, "EMsoft master verified")
    return record
