# Ideas backlog and research directions

Proposals, not commitments. Items move into ROADMAP.md only when agreed. Each lists why it matters and what
exists in the code base to build on.

## A. Indexing quality and robustness

| # | Feature | Why | Builds on |
| --- | --- | --- | --- |
| A1 | **PC plane fit / per-region PC** across the scan (fit PC(x, y) from calibration points; dictionary per region or per-pixel PC in refinement) | Real scans show PC drift; 9-point calibration varied by ~0.01 between Al–Si ROIs | `indexing/calibration.py`, PC-spread warning |
| A2 | **Hough/Radon pre-indexing (PyEBSDIndex) as a fast first guess**, then refinement | 10–100× faster than full dictionaries; good start for refinement and calibration | refinement module, equal-budget logic |
| A3 | **Neighbour-pattern averaging and NLPAR denoising** (recorded in the preprocessing pipeline) | Raises NCC on noisy fast scans; affects low-signal flags | `indexing/preprocessing.py` |
| A4 | **Energy-weighted / depth-weighted master projection** (proper per-pixel MC energy weighting, not the global approximation) | Dynamical fidelity matters most for similar-phase discrimination (benchmark finding) | `masters/importer.py` energy modes |
| A5 | **Pseudo-symmetry detection and resolution** (test known pseudo-symmetric operators during refinement, flag pixels) | The Al–Si IPF map shows a band of scattered orientations; pseudo-symmetry is a common cause | kikuchipy `pseudo_symmetry_ops` |
| A6 | **Overlap/boundary model**: fit measured pattern as w·A + (1−w)·B (two phases or two grains) | Boundary pixels are currently just “ambiguous”; mixing fraction is informative | 50/50 mixed benchmark, NCC machinery |
| A7 | **Spherical-harmonic (SHT) indexing** as an alternative matcher | Orders-of-magnitude fewer comparisons; scope lists it as a later release | master import, sampling |
| A8 | **Adaptive orientation sampling** (coarse grid → refine only near candidates; per-phase equal budget) | Lower memory/time than fine global grids | sampling, dictionary cache |
| A9 | **GPU projection** (not only GPU matching) | Projection dominates the uncached run time | `indexing/dictionary.py` |
| A10 | **Score calibration study**: map margins to empirical error rates on labelled data | Needed before any “probability” claim (AGENTS.md) | benchmark dev/held-out protocol |

## B. Ease of use

| # | Feature | Why |
| --- | --- | --- |
| B1 | **Project files** (`.kwbproj` JSON): scan, phases, geometry, settings, runs — reopen and rerun from the GUI | Today each GUI session starts from scratch |
| B2 | **Interactive ROI drawing** on the map (rectangle/lasso) instead of row/col boxes | Faster, fewer mistakes |
| B3 | **Phase library** of verified masters with search by formula/space group, plus cache browser | Reuse across projects; shows provenance |
| B4 | **Geometry wizard**: overlay band geometry (kinematical lines) on the measured pattern, drag PC with live residual | Visual PC check before indexing |
| B5 | **One-click report** (Markdown/HTML) of a run: maps, counts, settings, warnings, manifest | Shareable record; matches the scope’s export needs |
| B6 | **Resource-aware presets** (“quick look”, “standard”, “phase study”) that set grid, binning, refinement and warn on RAM/time | Beginners should not tune 15 parameters |
| B7 | **Batch queue** in the GUI (several scans/ROIs, run overnight, resume after crash) | Lab workflow |
| B8 | **Comparison view**: vendor (AZtec/OIM) map vs workbench map, misorientation and phase-disagreement maps | Builds trust; real-data validation |
| B9 | **Windows installer** (offline, signed) once the native EMsoft gate passes | Release requirement |
| B10 | **Plugin interface for new readers** (Bruker, NORDIF, TKD) | Wider data coverage |

## C. Research problems with publication potential

1. **Limits of same-structure phase discrimination by full-pattern matching.** Quantify, with dynamical EMsoft
   masters, the smallest lattice-parameter and chemistry contrast resolvable as a function of PC error, noise,
   binning, energy weighting and simulation fidelity. Our kinematical interim result (margins ~10⁻³ NCC,
   accuracy collapsing under model mismatch) and the reflector-cutoff artifact are already novel, reportable
   findings. *Target: Ultramicroscopy / Acta Materialia.*
2. **Model-mismatch-aware phase decisions.** Treat simulation error explicitly (ensembles of masters with
   perturbed Debye–Waller factors, energy spectra, PC) and decide phases by robustness across the ensemble rather
   than a single NCC margin; calibrate the resulting confidence on labelled data. Addresses the main failure mode
   found in our benchmark.
3. **Calibrated phase-confidence maps.** A proper calibration study (reliability diagrams, coverage vs error) for
   NCC margins on labelled synthetic and EDS-referenced real data; deliver per-pixel error rates instead of
   ad-hoc thresholds. Little published work treats EBSD phase scores as calibrated quantities.
4. **Boundary and overlap decomposition.** Fit overlapping patterns as mixtures to recover sub-pixel phase/grain
   fractions and boundary positions; validate against simulated mixtures and high-resolution reference maps.
   Scope lists quantitative overlap decomposition as a future goal.
5. **Discriminating ordered vs disordered or closely related cubic phases** (e.g. B2/BCC, L1₂/FCC, γ/γ′ in
   superalloys, δ-ferrite/martensite) where superlattice bands are weak: measure detectability of weak
   reflections versus noise and dose; combine with EDS.
6. **Joint PC field estimation and indexing.** Estimate a smooth PC(x, y) field jointly with orientations over
   the whole scan (regularised optimisation), and show the effect on orientation precision and phase decisions
   versus per-pattern or global PC.
7. **Reproducibility benchmark for dictionary indexing.** An open, versioned benchmark (fixtures, seeds,
   frozen-threshold protocol, manifests) comparing DI, refinement, SHT and Hough indexing across vendors —
   a community resource paper (e.g. *Microscopy and Microanalysis*, *Data in Brief*, *JOSS* for the software).
8. **Learning-assisted indexing with physics checks.** Use a neural network for fast candidate generation or
   denoising, but keep the physics-based NCC/refinement decision and the calibrated ambiguity labels;
   quantify when learned components help or bias phase decisions.

Suggested first paper: **problem 1 + 3** — it reuses the existing benchmark protocol, needs the native EMsoft run
(release gate) for dynamical Ni/Cu-type masters, and turns the artifact and mismatch findings into a clear,
practically useful result.
