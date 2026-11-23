"""CIF reading and validation against the EMsoft crystal representation.

EMsoft (``EMmkxtal``) describes a crystal by space-group number, setting
(origin choice for the 24 groups with two origins), lattice parameters in nm
and degrees, and the asymmetric unit with fractional coordinates, site
occupation and Debye-Waller factor (nm^2). This module converts a CIF to that
representation and rejects cases EMsoft cannot represent, with advice.

Supported: standard settings of all 230 groups; origin choices 1/2 detected
from symmetry operators or explicit ``:1``/``:2`` symbols; trigonal groups in
hexagonal axes. Rejected: rhombohedral axes, non-standard monoclinic/
orthorhombic settings, modulated/magnetic CIFs, malformed occupancies.
"""

from __future__ import annotations

import io
import math
import re
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..errors import CrystalValidationError
from ..provenance import sha256_bytes

ELEMENTS = (
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se "
    "Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy "
    "Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf"
).split()
Z_OF = {el: i + 1 for i, el in enumerate(ELEMENTS)}

# Space groups with two origin choices (all centrosymmetric); origin 2 has -1 at the origin.
TWO_ORIGIN_GROUPS = {48, 50, 59, 68, 70, 85, 86, 88, 125, 126, 129, 130, 133, 134, 137, 138,
                     141, 142, 201, 203, 222, 224, 227, 228}
RHOMBOHEDRAL_GROUPS = {146, 148, 155, 160, 161, 166, 167}

DEFAULT_B_A2 = 0.5  # Å^2, used (with a warning) when the CIF has no displacement parameter


def crystal_system_of(sg: int) -> str:
    if sg <= 2:
        return "triclinic"
    if sg <= 15:
        return "monoclinic"
    if sg <= 74:
        return "orthorhombic"
    if sg <= 142:
        return "tetragonal"
    if sg <= 167:
        return "trigonal"
    if sg <= 194:
        return "hexagonal"
    return "cubic"


# EMsoft crystal-system codes (EMmkxtal): trigonal in hexagonal axes uses the hexagonal code.
EMSOFT_XTAL_SYSTEM = {"cubic": 1, "tetragonal": 2, "orthorhombic": 3, "hexagonal": 4,
                      "trigonal": 4, "monoclinic": 6, "triclinic": 7}


@dataclass
class Site:
    label: str
    element: str
    Z: int
    x: float
    y: float
    z: float
    occupancy: float
    B_iso_A2: float


@dataclass
class CrystalModel:
    name: str
    space_group: int
    hm_symbol: str
    setting: int  # EMsoft SpaceGroupSetting (origin choice; 1 otherwise)
    crystal_system: str
    a: float  # Å
    b: float
    c: float
    alpha: float  # degrees
    beta: float
    gamma: float
    sites: list[Site]
    source: str = ""
    source_sha256: str | None = None
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    @property
    def lattice_A_deg(self) -> list[float]:
        return [self.a, self.b, self.c, self.alpha, self.beta, self.gamma]

    @property
    def lattice_nm_deg(self) -> list[float]:
        return [self.a / 10, self.b / 10, self.c / 10, self.alpha, self.beta, self.gamma]

    @property
    def elements(self) -> list[str]:
        return sorted({s.element for s in self.sites})

    def to_dict(self) -> dict:
        d = asdict(self)
        d["elements"] = self.elements
        return d

    def key_fields(self) -> dict:
        """Physics-defining fields for cache keys (independent of file formatting)."""
        return {
            "space_group": self.space_group,
            "setting": self.setting,
            "lattice_A_deg": [round(v, 6) for v in self.lattice_A_deg],
            "sites": [
                [s.Z, round(s.x, 6), round(s.y, 6), round(s.z, 6), round(s.occupancy, 6),
                 round(s.B_iso_A2, 6)]
                for s in self.sites
            ],
        }

    def to_orix_phase(self, name: str | None = None, color: str | None = None):
        from diffpy.structure import Atom, Lattice, Structure
        from orix.crystal_map import Phase

        shift = origin2_to_origin1_shift(self.space_group) if self.setting == 2 else (0.0, 0.0, 0.0)
        atoms = [
            Atom(s.element, [(s.x + shift[0]) % 1, (s.y + shift[1]) % 1, (s.z + shift[2]) % 1],
                 occupancy=s.occupancy,
                 Uisoequiv=s.B_iso_A2 / (8 * math.pi**2))
            for s in self.sites
        ]
        st = Structure(atoms=atoms, lattice=Lattice(*self.lattice_A_deg))
        kw = {"name": name or self.name, "space_group": self.space_group, "structure": st}
        if color:
            kw["color"] = color
        return Phase(**kw)

    def summary_lines(self) -> list[str]:
        lines = [
            f"{self.name}: {self.crystal_system}, space group {self.space_group} ({self.hm_symbol}), "
            f"setting {self.setting}",
            "a, b, c = {:.4f}, {:.4f}, {:.4f} Å; α, β, γ = {:.2f}, {:.2f}, {:.2f}°".format(
                *self.lattice_A_deg),
            f"elements: {', '.join(self.elements)}; {len(self.sites)} site(s) in asymmetric unit",
        ]
        for s in self.sites:
            lines.append(
                f"  {s.label:<6} {s.element:<2} ({s.x:.4f}, {s.y:.4f}, {s.z:.4f}) occ={s.occupancy:.3f} "
                f"B={s.B_iso_A2:.3f} Å²"
            )
        return lines


def origin2_to_origin1_shift(sg: int) -> tuple[float, float, float]:
    """Vector added to origin-choice-2 coordinates to express them in origin choice 1.

    orix/diffpy space-group tables use origin choice 1. Origin choice 2 sits on an
    inversion centre; the inversion operator ``-x + t`` of the origin-1 table has its
    centre at ``t / 2``. A pure translation leaves |F| and orientations unchanged.
    """
    import numpy as np
    from diffpy.structure.spacegroups import GetSpaceGroup

    g = GetSpaceGroup(sg)
    best = None
    for op in g.iter_symops():
        if np.allclose(op.R, -np.eye(3)):
            t = np.mod(op.t, 1.0)
            if best is None or np.linalg.norm(t) < np.linalg.norm(best):
                best = t
    if best is None:
        raise CrystalValidationError(f"Space group {sg} has no inversion operator.")
    c = best / 2.0
    return float(c[0]), float(c[1]), float(c[2])


def _num(v) -> float:
    """Parse a CIF number, dropping standard uncertainty in parentheses."""
    if v is None:
        raise ValueError("missing")
    s = str(v).strip()
    if s in ("?", "."):
        raise ValueError(f"undefined value {s!r}")
    s = re.sub(r"\(\d+\)$", "", s)
    return float(s)


def _raw_tags(text: str) -> dict[str, str]:
    """Collect simple ``_tag value`` pairs (first occurrence) for checks diffpy ignores."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(_[\w\-\.\[\]/]+)\s+(.+?)\s*$", line)
        if m and m.group(1).lower() not in out:
            out[m.group(1).lower()] = m.group(2).strip().strip("'\"")
    return out


def _symops(text: str) -> list[str]:
    ops: list[str] = []
    lines = text.splitlines()
    in_loop = False
    in_ops = False
    for line in lines:
        s = line.strip()
        if s.lower().startswith("loop_"):
            in_loop, in_ops = True, False
            continue
        if in_loop and s.startswith("_"):
            if re.match(r"_(symmetry_equiv_pos_as_xyz|space_group_symop_operation_xyz)", s, re.I):
                in_ops = True
            continue
        if in_ops:
            if not s or s.startswith("_") or s.lower().startswith(("loop_", "data_")):
                in_ops = False
                in_loop = False
                continue
            m = re.search(r"['\"]([^'\"]+)['\"]", s)
            op = m.group(1) if m else s.split()[-1]
            ops.append(op.replace(" ", "").lower())
    return ops


def _has_pure_inversion(ops: list[str]) -> bool:
    return any(op in ("-x,-y,-z",) for op in ops)


def _origin_setting(sg: int, hm: str, ops: list[str], tags: dict[str, str]) -> tuple[int, str]:
    if sg not in TWO_ORIGIN_GROUPS:
        return 1, "single origin choice"
    m = re.search(r":\s*([12])", hm) or re.search(
        r":\s*([12])", tags.get("_space_group_name_h-m_alt", "")
    )
    oc_tag = tags.get("_symmetry_space_group_name_h-m_origin") or tags.get("_space_group.origin_choice")
    if ops:
        setting = 2 if _has_pure_inversion(ops) else 1
        if m and int(m.group(1)) != setting:
            raise CrystalValidationError(
                f"Origin choice in symbol ({hm}) contradicts the symmetry operators.",
                "Fix the CIF so the symbol and the operator list agree.",
            )
        return setting, "origin from symmetry operators"
    if m:
        return int(m.group(1)), "origin from H-M symbol suffix"
    if oc_tag in ("1", "2"):
        return int(oc_tag), "origin from origin-choice tag"
    raise CrystalValidationError(
        f"Space group {sg} has two origin choices and the CIF does not say which is used.",
        "Add the symmetry-operator loop or write the symbol with ':1' or ':2' "
        "(e.g. 'F d -3 m :2').",
    )


def read_cif(path_or_text: str | Path, name: str | None = None) -> CrystalModel:
    """Read and validate a CIF. Raises :class:`CrystalValidationError` on unsupported input."""
    from diffpy.structure.parsers.p_cif import P_cif

    if isinstance(path_or_text, Path) or (
        isinstance(path_or_text, str) and "\n" not in path_or_text and Path(path_or_text).exists()
    ):
        p = Path(path_or_text)
        text = p.read_text(errors="replace")
        source = str(p)
        default_name = p.stem
    else:
        text = str(path_or_text)
        source = "<text>"
        default_name = "crystal"
    tags = _raw_tags(text)
    warns: list[str] = []
    checks: list[str] = []

    # --- unsupported representations
    for t in tags:
        if t.startswith(("_cell_modulation", "_space_group_ssg", "_cell_wave_vector")):
            raise CrystalValidationError(
                "Modulated / superspace-group CIF is not supported by EMsoft.",
                "Use an average (commensurate) structure CIF.",
            )
        if t.startswith(("_space_group_magn", "_atom_site_moment", "_parent_space_group")):
            raise CrystalValidationError(
                "Magnetic CIF (mCIF) is not supported.",
                "Use the nuclear (crystallographic) structure CIF.",
            )
    for key in ("_cell_length_a", "_cell_length_b", "_cell_length_c"):
        if key not in tags:
            raise CrystalValidationError(f"CIF is missing {key}.", "Provide a complete unit cell.")

    # --- occupancy sanity before diffpy (which silently accepts some malformed values)
    occ_raw = _loop_column(text, "_atom_site_occupancy")
    for lab, v in occ_raw:
        try:
            o = _num(v)
        except ValueError as e:
            raise CrystalValidationError(
                f"Site {lab}: malformed occupancy {v!r}.",
                "Occupancies must be numbers in (0, 1].",
            ) from e
        if not (0 < o <= 1.0 + 1e-6):
            raise CrystalValidationError(
                f"Site {lab}: occupancy {o} is outside (0, 1].", "Fix the site occupancy."
            )

    parser = P_cif()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parser.parse(text)
    except Exception as e:  # diffpy raises StructureFormatError and others
        raise CrystalValidationError(f"CIF could not be parsed: {e}", "Check the CIF syntax.") from e
    sgo = parser.spacegroup
    if sgo is None:
        raise CrystalValidationError("CIF has no space group.", "Add _space_group_IT_number.")
    sg = int(sgo.number)
    it_tag = tags.get("_space_group_it_number") or tags.get("_symmetry_int_tables_number")
    if it_tag is not None and int(_num(it_tag)) != sg:
        raise CrystalValidationError(
            f"Space group number {it_tag} disagrees with the parsed symbol ({sgo.short_name}, {sg}).",
            "Fix the space-group number or symbol.",
        )
    hm = (tags.get("_symmetry_space_group_name_h-m") or tags.get("_space_group_name_h-m_alt")
          or sgo.short_name)
    ops = _symops(text)

    lat = parser.stru.lattice
    a, b, c, al, be, ga = (float(v) for v in (lat.a, lat.b, lat.c, lat.alpha, lat.beta, lat.gamma))
    if min(a, b, c) <= 0:
        raise CrystalValidationError("Cell lengths must be positive.")
    if max(a, b, c) < 1.0:
        raise CrystalValidationError(
            f"Cell lengths ({a}, {b}, {c}) look like nm; CIF cell lengths must be in Å.",
            "Multiply cell lengths by 10.",
        )
    if max(a, b, c) > 100:
        warns.append(f"Very large cell ({max(a, b, c)} Å); master simulation will be slow.")
    for ang in (al, be, ga):
        if not 0 < ang < 180:
            raise CrystalValidationError(f"Cell angle {ang} outside (0, 180) degrees.")
    checks.append("cell lengths in Å, angles in degrees")

    system = crystal_system_of(sg)
    _check_metric(system, sg, a, b, c, al, be, ga)
    checks.append(f"metric consistent with {system} setting used by EMsoft")

    setting, how = _origin_setting(sg, hm, ops, tags)
    checks.append(f"origin choice {setting} ({how})")
    if ops:
        _check_ops_match(ops, sgo, setting, sg)
        checks.append(f"{len(ops)} symmetry operators consistent with space group {sg}")

    sites: list[Site] = []
    for i, atom in enumerate(parser.asymmetric_unit):
        sym = re.sub(r"[^A-Za-z]", "", str(atom.element))
        sym = sym[:1].upper() + sym[1:2].lower() if sym else sym
        if sym in ("D", "T"):
            raise CrystalValidationError("Isotope labels (D, T) are not supported.",
                                         "Use the element symbol H.")
        if sym not in Z_OF:
            raise CrystalValidationError(f"Unknown element {atom.element!r} at site {i}.",
                                         "Use a standard element symbol in _atom_site_type_symbol.")
        labels = {v: k for k, v in (parser.labelindex or {}).items()}
        label = labels.get(i, f"{sym}{i + 1}")
        occ = float(atom.occupancy)
        u = float(atom.Uisoequiv)
        if u <= 0:
            B = DEFAULT_B_A2
            warns.append(f"Site {label}: no displacement parameter; using B = {B} Å².")
        else:
            B = 8 * math.pi**2 * u
        xyz = [float(v) % 1.0 for v in atom.xyz]
        sites.append(Site(label, sym, Z_OF[sym], *xyz, occupancy=occ, B_iso_A2=B))
    if not sites:
        raise CrystalValidationError("CIF has no atom sites.", "Add an _atom_site_ loop.")

    # total occupancy per crystallographic position
    pos: dict[tuple, float] = {}
    for s in sites:
        k = (round(s.x, 4), round(s.y, 4), round(s.z, 4))
        pos[k] = pos.get(k, 0.0) + s.occupancy
    for k, tot in pos.items():
        if tot > 1.0 + 1e-3:
            raise CrystalValidationError(
                f"Total occupancy {tot:.3f} > 1 at position {k}.",
                "Mixed sites must sum to at most 1.",
            )
        if tot < 1.0 - 1e-3:
            warns.append(f"Position {k} is partially occupied (total {tot:.3f}).")
    checks.append(f"{len(sites)} asymmetric-unit sites, occupancies in (0, 1]")

    return CrystalModel(
        name=name or (parser.stru.title or default_name).strip() or default_name,
        space_group=sg,
        hm_symbol=str(hm),
        setting=setting,
        crystal_system=system,
        a=a, b=b, c=c, alpha=al, beta=be, gamma=ga,
        sites=sites,
        source=source,
        source_sha256=sha256_bytes(text.encode()),
        warnings=warns,
        checks=checks,
    )


def _loop_column(text: str, tag: str) -> list[tuple[str, str]]:
    """Return (label, value) pairs of ``tag`` in the atom-site loop (simple tokeniser)."""
    lines = text.splitlines()
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().lower().startswith("loop_"):
            hdr = []
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("_"):
                hdr.append(lines[j].strip().split()[0].lower())
                j += 1
            if tag.lower() in hdr:
                col = hdr.index(tag.lower())
                lab = hdr.index("_atom_site_label") if "_atom_site_label" in hdr else 0
                while j < len(lines):
                    s = lines[j].strip()
                    if not s or s.startswith(("_", "loop_", "data_", "#")):
                        break
                    toks = s.split()
                    if len(toks) >= len(hdr):
                        out.append((toks[lab], toks[col]))
                    j += 1
            i = j
        else:
            i += 1
    return out


def _close(x, y, tol=1e-3):
    return abs(x - y) <= tol * max(1.0, abs(y))


def _check_metric(system, sg, a, b, c, al, be, ga):
    def bad(msg, advice):
        raise CrystalValidationError(msg, advice)

    if system == "cubic" and not (_close(a, b) and _close(b, c) and all(_close(x, 90) for x in (al, be, ga))):
        bad("Cubic space group with non-cubic cell.", "Check the cell parameters.")
    if system == "tetragonal" and not (_close(a, b) and all(_close(x, 90) for x in (al, be, ga))):
        bad("Tetragonal space group requires a = b and 90° angles (c-unique setting).",
            "Transform the CIF to the standard setting.")
    if system == "orthorhombic" and not all(_close(x, 90) for x in (al, be, ga)):
        bad("Orthorhombic space group with non-90° angles.", "Check the cell parameters.")
    if system in ("hexagonal", "trigonal"):
        if sg in RHOMBOHEDRAL_GROUPS and _close(a, b) and _close(b, c) and _close(al, be) \
                and _close(be, ga) and not _close(al, 90):
            bad("Rhombohedral axes are not supported; EMsoft input here uses hexagonal axes.",
                "Convert the CIF to the hexagonal (obverse) setting, e.g. with VESTA or cctbx.")
        if not (_close(a, b) and _close(al, 90) and _close(be, 90) and _close(ga, 120)):
            bad(f"{system.capitalize()} group requires hexagonal axes (a = b, γ = 120°).",
                "Convert the CIF to hexagonal axes.")
    if system == "monoclinic" and not (_close(al, 90) and _close(ga, 90)):
        bad("Monoclinic cell is not in the standard b-unique setting (α = γ = 90°).",
            "Transform the CIF to the standard b-unique setting.")


def _check_ops_match(ops: list[str], sgo, setting: int, sg: int) -> None:
    """Check that the CIF operator count matches the space group (setting-independent)."""
    n_expected = len(sgo.symop_list)
    if len(ops) != n_expected:
        raise CrystalValidationError(
            f"CIF lists {len(ops)} symmetry operators but space group {sg} has {n_expected}.",
            "The CIF may use a non-standard setting; transform it to the standard setting.",
        )


def cif_text_for(model: CrystalModel) -> str:
    """Serialise a CrystalModel back to a minimal CIF (asymmetric unit, standard setting)."""
    buf = io.StringIO()
    buf.write(f"data_{model.name}\n")
    for k, v in zip(("a", "b", "c"), (model.a, model.b, model.c), strict=True):
        buf.write(f"_cell_length_{k} {v:.6f}\n")
    for k, v in zip(("alpha", "beta", "gamma"), (model.alpha, model.beta, model.gamma), strict=True):
        buf.write(f"_cell_angle_{k} {v:.4f}\n")
    sym = model.hm_symbol
    if model.space_group in TWO_ORIGIN_GROUPS and ":" not in sym:
        sym = f"{sym} :{model.setting}"
    buf.write(f"_symmetry_space_group_name_H-M '{sym}'\n")
    buf.write(f"_space_group_IT_number {model.space_group}\n")
    buf.write("loop_\n_atom_site_label\n_atom_site_type_symbol\n_atom_site_fract_x\n"
              "_atom_site_fract_y\n_atom_site_fract_z\n_atom_site_occupancy\n"
              "_atom_site_B_iso_or_equiv\n")
    for s in model.sites:
        buf.write(f"{s.label} {s.element} {s.x:.6f} {s.y:.6f} {s.z:.6f} {s.occupancy:.4f} "
                  f"{s.B_iso_A2:.4f}\n")
    return buf.getvalue()


def make_cubic_model(name: str, element: str, a: float, sg: int = 225,
                     B_iso_A2: float = 0.5) -> CrystalModel:
    """Convenience constructor for single-element cubic crystals (e.g. FCC Ni, Cu)."""
    text = f"""data_{name}
_cell_length_a {a}
_cell_length_b {a}
_cell_length_c {a}
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_IT_number {sg}
_symmetry_space_group_name_H-M '{ {225: 'F m -3 m', 229: 'I m -3 m', 221: 'P m -3 m'}[sg] }'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
_atom_site_B_iso_or_equiv
{element}1 {element} 0 0 0 1.0 {B_iso_A2}
"""
    return read_cif(text, name=name)

