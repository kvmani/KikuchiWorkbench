"""Geometry wizard helpers: kinematical band-line overlay and a live fit score.

Given a phase, a detector geometry and an orientation, ``band_segments`` returns the centre lines of the
strongest Kikuchi bands in detector pixel coordinates (x = column, y = row), for drawing over the measured
pattern. ``fit_score`` returns the NCC between the measured (preprocessed) pattern and the dynamical simulation
from the master at the same geometry, so the user sees whether a PC/tilt edit improves the match.
"""

from __future__ import annotations

import contextlib
import io
import warnings
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=16)
def _reflectors(space_group: int, lattice: tuple, sites: tuple, voltage_kV: float, n_families: int):
    from diffpy.structure import Atom, Lattice, Structure
    from diffsims.crystallography import ReciprocalLatticeVector
    from orix.crystal_map import Phase

    atoms = [Atom(el, xyz, occupancy=occ) for el, xyz, occ in sites] or [Atom("Ni", [0, 0, 0])]
    phase = Phase(space_group=space_group, structure=Structure(atoms=atoms, lattice=Lattice(*lattice)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = ReciprocalLatticeVector.from_min_dspacing(phase, min(lattice[:3]) / 5)
        r.sanitise_phase()
        r = r.unique(use_symmetry=True)
        r = r[r.allowed]
        r.calculate_structure_factor()
        f = np.abs(r.structure_factor)
        r = r[np.argsort(f)[::-1]][:n_families]
        r.calculate_theta(voltage_kV * 1e3)
        r = r.symmetrise()
    return r


def phase_key(phase) -> tuple:
    st = phase.structure
    lat = st.lattice
    sites = tuple((str(a.element), tuple(float(v) for v in a.xyz), float(a.occupancy)) for a in st)
    return int(phase.space_group.number), (lat.a, lat.b, lat.c, lat.alpha, lat.beta, lat.gamma), sites


def band_segments(phase, detector, quaternion, voltage_kV: float = 20.0, n_families: int = 6) -> np.ndarray:
    """(n, 2, 2) array of band centre-line segments [[x0, y0], [x1, y1]] in pixel coordinates."""
    import kikuchipy as kp
    from orix.quaternion import Rotation

    sg, lat, sites = phase_key(phase)
    refl = _reflectors(sg, lat, sites, float(voltage_kV), int(n_families))
    sim = kp.simulations.KikuchiPatternSimulator(refl)
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        geo = sim.on_detector(detector, Rotation(np.asarray(quaternion, dtype=float).reshape(1, 4)))
        coll = geo.as_collections(0)
    if not coll:
        return np.zeros((0, 2, 2))
    segs = [np.asarray(s, dtype=float) for s in coll[0].get_segments() if len(s) == 2]
    return np.stack(segs) if segs else np.zeros((0, 2, 2))


def fit_score(loaded_master, detector, quaternion, measured: np.ndarray, preprocessor=None) -> float:
    """NCC between a measured (preprocessed) pattern and the dynamical simulation at this geometry."""
    from orix.quaternion import Rotation

    from .indexing.dictionary import DictionaryProjector
    from .indexing.matching import normalize
    from .indexing.preprocessing import Preprocessor

    pre = preprocessor or Preprocessor([], tuple(detector.shape))
    proj = DictionaryProjector(loaded_master.signal, detector, pre)
    sim = proj.project(Rotation(np.asarray(quaternion, dtype=float).reshape(1, 4)), normalise=True)
    exp = normalize(np.asarray(measured, dtype=np.float32)[None], pre.mask())
    return float((sim @ exp.T).ravel()[0])
