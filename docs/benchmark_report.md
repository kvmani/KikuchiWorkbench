# Benchmark report — controlled cubic discrimination (synthetic, kinematical)

Status: **interim**, produced in a Linux CPU container on 2026-11-23. Masters are **kinematical** (kikuchipy
simulator), not dynamical EMsoft masters, so these numbers describe the method's sensitivity to model mismatch
and orientation error, not the discriminability of real Ni and Cu.

Reproduce:

```bash
python benchmarks/run_cubic_discrimination.py --mode full
```

```bash
python benchmarks/run_cubic_discrimination.py --mode full --refine
```

Raw outputs: [`benchmarks/results/full_2026-11-23/`](../benchmarks/results/full_2026-11-23/report.md) (dictionary
only) and [`benchmarks/results/full_refined_2026-11-23/`](../benchmarks/results/full_refined_2026-11-23/report.md)
(equal-budget refinement).

## Setup

* Phases: Ni (a = 3.524 Å) vs Cu (a = 3.615 Å), FCC Fm-3m; same-chemistry sweep Ni vs Ni·(1+δ), δ = 0.5, 1, 2 %.
* Reflectors: identical hkl families for every phase (h²+k²+l² ≤ 20 for dictionaries, ≤ 40 for the finer target
  route). A fixed d-spacing cutoff is **not** used (see artifact below).
* Scans: 14 × 14 points, random off-grid orientations, PC (0.421, 0.217, 0.502), 60 × 60 px, Poisson noise
  (400 counts unless stated), smooth background; dev seed 1001, held-out seed 2002.
* Dictionary: cubochoric 4° grid (3° and 6° in the step conditions), NCC on background-corrected patterns.
* Refinement (second run): Nelder-Mead, trust region ±4° per Euler angle, rtol 1e-4, ≤ 300 evaluations, one
  start per phase — identical for both phases, fixed shared PC.
* Thresholds: ambiguity margin chosen on the dev baseline as the smallest margin with error ≤ 1 % and ≥ 10
  indexed points; frozen to `thresholds.json` before the held-out runs.

## Results (held-out)

Error among indexed pixels at **zero** ambiguity margin (i.e. forced choice, from the coverage-vs-error CSVs) and
median true-phase NCC margin:

| Condition | Routes | Forced-choice error, grid only | Forced-choice error, refined | Median true margin (refined) |
| --- | --- | --- | --- | --- |
| Ni vs Cu, matched fine route | target / target | 0.30 | **0.07** | 0.0029 |
| Ni vs Cu, matched coarse route | dict / dict | 0.27 | 0.12 | 0.0018 |
| Ni vs Cu, + PC error 0.01 (matched) | dict / dict | 0.33* | 0.17 | 0.0017 |
| Ni vs Cu, 50 counts (matched) | dict / dict | 0.33 | 0.24 | 0.0016 |
| Ni vs Ni+2 % (matched) | dict / dict | 0.41* | 0.22 | 0.0011 |
| Ni vs Ni+1 % (matched) | dict / dict | 0.39* | 0.31 | 0.0003 |
| Ni vs Ni+0.5 % (matched) | dict / dict | 0.40* | 0.28 | 0.0002 |
| Ni vs Cu, mismatched routes (baseline) | target / dict | 0.46 | 0.37 | 0.0010 |
| Ni vs Cu, mismatched + PC error 0.01 | target / dict | 0.43* | 0.39 | 0.0008 |
| identical masters | – | all ambiguous (exact ties) | all ambiguous | 0 |
| 50/50 mixed patterns | target / dict | 196/196 ambiguous | 196/196 ambiguous | – |

\* fraction of pixels whose true phase scored lower ("Margin < 0" column of the report), equivalent to the
forced-choice error.

With the frozen dev threshold (0.05; the 1 % error target was **not** met on the dev set) every held-out pixel
of the two-phase conditions is reported **ambiguous**, and **no condition produced confidently wrong phase labels**
except isolated points (≤ 2 of 196) in `pc_error_0.01` and `step_3deg`.

## Findings

1. **Reflector-cutoff artifact (fixed).** With a fixed d-spacing cutoff, {420} entered the Cu (and Ni+2 %) master
   but not the Ni master, producing perfect but spurious Ni/Cu separation. Competing kinematical masters must use
   identical reflector families; the pipeline now warns otherwise. The same risk should be checked for dynamical
   masters (EMsoft `dmin`) before any phase-comparison claim.
2. **Phase signal is ~10⁻³ NCC.** Same-structure phases with a 2.6 % lattice difference change the best NCC by
   about 0.001–0.003, far below the NCC change caused by a 2° orientation error. Equal-budget refinement is
   therefore necessary; it raises forced-choice accuracy from ~70 % to ~93 % in the cleanest (matched) case.
3. **Model mismatch dominates.** When target patterns come from a different master route than the dictionary,
   forced-choice accuracy falls to 54–63 % even with refinement. Real data will have larger mismatch than this, so
   Ni/Cu-like pairs should not be expected to separate with NCC dictionary matching unless the simulation matches
   the experiment closely (dynamical masters, energy weighting, calibrated geometry).
4. Smallest lattice contrast resolved (forced choice ≥ 90 % correct): **none** under matched coarse routes; only the
   Ni/Cu pair (2.6 % plus chemistry) under matched fine routes with refinement (93 %). No condition met the frozen
   1 %-error threshold.

## Limitations

Kinematical masters only; one detector geometry; 196 points per scan (statistical uncertainty of a few percent);
synthetic noise model; refinement uses kikuchipy's projection at the binned resolution; compute times are from a
4-core container (≈ 6–9 s per refined condition). Not evidence about real Ni/Cu or the lab's phases.

# Real-data interoperability — public Oxford Al–10Si `.ebsp` (interim)

Data: Zenodo 20290635 (scan, Oxford Symmetry S2, 75,551 patterns of 88 × 156 px, 20 nm step), EMsoft dynamical
masters Al (Zenodo 7628365, EMsoft 4.1) and Si (Zenodo 7498729, EMsoft 5.0), 20 keV slice; all CC-BY-4.0.
Reproduce: `python benchmarks/fetch_public_data.py al_si al_master si_master` then
`python benchmarks/real_al_si.py --roi 90 140 90 150 --resolution 2.5`.

Workflow: `.ebsp` has no calibration → starting PC from the dataset authors' notebook (Bruker (0.50, 0.15, 1.25),
detector tilt 5°) → shared calibration on 9 Al points → Al and Si dictionaries at the same 2.5° sampling on 2×-binned
patterns → NCC → equal-budget refinement → decision (provisional thresholds).

| ROI (rows, cols) | Points | Indexed | Ambiguous | Al / Si of indexed | Calibrated PC (Bruker) | Median NCC | Time (4 CPU) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100–120, 100–125 (3° grid) | 500 | 493 | 7 | 0.62 / 0.38 | (0.510, 0.137, 1.248) | 0.27 | 89 s |
| 90–140, 90–150 (2.5° grid) | 3000 | 2974 | 26 | 0.73 / 0.27 | (0.501, 0.147, 1.252) | 0.38 | 205 s |

Maps (phase, IPF-Z, score, margin) are regenerated by the script above into the job folder; they are kept
outside the repository (no binary files in Git).

Observations: rounded Si particles with one orientation each in an Al matrix; ambiguous pixels lie on phase
boundaries (overlapping patterns); Al/Si phase margins are up to ~0.2 NCC, about 100× the synthetic Ni/Cu margins.

Limitations: no independent reference (EDS or vendor phase map) for this ROI, so phase-label accuracy is **not
measured**; the comparison with published results asked for by the scope is pending (the authors' notebook stores
no numeric outputs, and Oxford's own indexing is not in the record). PC calibration from 9 points differed by up to
0.01 between ROIs — use more points or a plane fit before quantitative work. Thresholds are provisional.
