# Controlled cubic discrimination benchmark (synthetic, kinematical)

Mode `full`, 196 points per scan, seeds {'dev': 1001, 'heldout': 2002}. Masters: kinematical (kikuchipy simulator); NOT dynamical EMsoft. Dictionary route {'max_hkl_sq': 20, 'half_size': 150}, target route {'max_hkl_sq': 40, 'half_size': 200} (model mismatch).

Frozen thresholds (from dev set): `{"min_score": 0.1, "ambiguity_margin": 0.05, "provenance": "selected on dev baseline (seed 1001, n=196); target error <= 0.01; frozen 2026-11-23T13:46:20+00:00"}`

Phase margins are ranking diagnostics, not probabilities.

| Condition | Phases | Coverage | Error among indexed | Ambiguous | Unindexed | Recall | Median misori. (°) | Median true margin | Margin < 0 | Time (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0005 | 0.46 | 1.67 |
| pc_error_0.01 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0005 | 0.43 | 7.9 |
| identical_masters | Ni vs Ni | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni_copy 0.00 | – | 0.0000 | 0.00 | 1.55 |
| mixed_50_50 | Ni vs Cu (50/50 overlap) | – | – | – | – | labels {'Ni': 0, 'Cu': 0, 'ambiguous': 196, 'unindexed/other': 0} | – | – | – | 1.44 |
| lattice_sweep_1% | Ni vs Ni+1% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+1% 0.00 | – | 0.0000 | 0.50 | 4.54 |
| matched_route | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0012 | 0.27 | 1.52 |
| matched_fine_route | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0008 | 0.30 | 7.5 |
| counts_50 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0004 | 0.44 | 1.65 |
| counts_2000 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0004 | 0.45 | 1.81 |
| pc_error_0.005 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0004 | 0.45 | 8.35 |
| pc_error_0.02 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0001 | 0.47 | 8.2 |
| binning_2 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0004 | 0.46 | 7.96 |
| step_3deg | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0002 | 0.48 | 19.72 |
| step_6deg | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0003 | 0.46 | 2.66 |
| lattice_sweep_0.5% | Ni vs Ni+0.5% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+0.5% 0.00 | – | 0.0000 | 0.47 | 4.32 |
| lattice_sweep_2% | Ni vs Ni+2% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+2% 0.00 | – | 0.0001 | 0.49 | 5.31 |
| matched_sweep_0.5% | Ni vs Ni+0.5% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+0.5% 0.00 | – | 0.0002 | 0.40 | 1.76 |
| matched_sweep_1% | Ni vs Ni+1% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+1% 0.00 | – | 0.0002 | 0.39 | 1.76 |
| matched_sweep_2% | Ni vs Ni+2% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+2% 0.00 | – | 0.0005 | 0.41 | 1.78 |
| matched_pc_error_0.005 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0011 | 0.31 | 1.73 |
| matched_pc_error_0.01 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0011 | 0.33 | 1.72 |
| matched_pc_error_0.02 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0008 | 0.36 | 1.86 |
| matched_counts_50 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0008 | 0.33 | 1.77 |
| matched_binning_2 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0010 | 0.30 | 1.62 |

Confusion matrices (rows = true phase; columns = predicted, ambiguous, unindexed/other):

- **baseline**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **pc_error_0.01**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **identical_masters**: ['Ni', 'Ni_copy', 'ambiguous', 'unindexed/other'] → [[0, 0, 196, 0], [0, 0, 0, 0]]
- **lattice_sweep_1%**: ['Ni', 'Ni+1%', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_route**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_fine_route**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **counts_50**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **counts_2000**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **pc_error_0.005**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **pc_error_0.02**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **binning_2**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **step_3deg**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **step_6deg**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **lattice_sweep_0.5%**: ['Ni', 'Ni+0.5%', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **lattice_sweep_2%**: ['Ni', 'Ni+2%', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_sweep_0.5%**: ['Ni', 'Ni+0.5%', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_sweep_1%**: ['Ni', 'Ni+1%', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_sweep_2%**: ['Ni', 'Ni+2%', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_pc_error_0.005**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_pc_error_0.01**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_pc_error_0.02**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_counts_50**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_binning_2**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]

Route note: `matched_*` conditions index targets with masters from the same generation route; all other conditions use the mismatched route (targets finer than dictionary).

Limitations: kinematical masters only; single detector geometry; random orientations; synthetic noise model (Poisson + smooth background). Not evidence for real-data discrimination.
