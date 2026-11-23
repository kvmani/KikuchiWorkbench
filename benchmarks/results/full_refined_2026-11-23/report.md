# Controlled cubic discrimination benchmark (synthetic, kinematical)

Mode `full`, refinement: equal-budget Nelder-Mead, trust region = grid step, maxeval 300, 196 points per scan, seeds {'dev': 1001, 'heldout': 2002}. Masters: kinematical (kikuchipy simulator); NOT dynamical EMsoft. Dictionary route {'max_hkl_sq': 20, 'half_size': 150}, target route {'max_hkl_sq': 40, 'half_size': 200} (model mismatch).

Frozen thresholds (from dev set): `{"min_score": 0.1, "ambiguity_margin": 0.05, "provenance": "selected on dev baseline (seed 1001, n=196); target error <= 0.01; frozen 2026-11-23T13:50:15+00:00"}`

Phase margins are ranking diagnostics, not probabilities.

| Condition | Phases | Coverage | Error among indexed | Ambiguous | Unindexed | Recall | Median misori. (°) | Median true margin | Margin < 0 | Time (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0010 | 0.37 | 7.02 |
| pc_error_0.01 | Ni vs Cu | 0.01 | 1.000 | 0.99 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0008 | 0.39 | 6.81 |
| identical_masters | Ni vs Ni | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni_copy 0.00 | – | 0.0000 | 0.00 | 6.87 |
| mixed_50_50 | Ni vs Cu (50/50 overlap) | – | – | – | – | labels {'Ni': 1, 'Cu': 1, 'ambiguous': 194, 'unindexed/other': 0} | – | – | – | 6.74 |
| lattice_sweep_1% | Ni vs Ni+1% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+1% 0.00 | – | 0.0000 | 0.47 | 6.72 |
| matched_route | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0018 | 0.12 | 6.38 |
| matched_fine_route | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0029 | 0.07 | 6.08 |
| counts_50 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0004 | 0.42 | 7.23 |
| counts_2000 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0010 | 0.36 | 6.63 |
| pc_error_0.005 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0011 | 0.38 | 6.43 |
| pc_error_0.02 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0006 | 0.42 | 6.7 |
| binning_2 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0004 | 0.45 | 6.74 |
| step_3deg | Ni vs Cu | 0.01 | 0.000 | 0.99 | 0.00 | Ni 0.00, Cu 0.01 | 0.05 | 0.0010 | 0.36 | 8.53 |
| step_6deg | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0010 | 0.37 | 5.79 |
| lattice_sweep_0.5% | Ni vs Ni+0.5% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+0.5% 0.00 | – | 0.0001 | 0.45 | 6.55 |
| lattice_sweep_2% | Ni vs Ni+2% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+2% 0.00 | – | 0.0004 | 0.41 | 6.3 |
| matched_sweep_0.5% | Ni vs Ni+0.5% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+0.5% 0.00 | – | 0.0002 | 0.28 | 7.02 |
| matched_sweep_1% | Ni vs Ni+1% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+1% 0.00 | – | 0.0003 | 0.31 | 6.17 |
| matched_sweep_2% | Ni vs Ni+2% | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Ni+2% 0.00 | – | 0.0011 | 0.22 | 6.25 |
| matched_pc_error_0.005 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0017 | 0.14 | 6.62 |
| matched_pc_error_0.01 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0017 | 0.17 | 6.97 |
| matched_pc_error_0.02 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0014 | 0.20 | 7.17 |
| matched_counts_50 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0016 | 0.24 | 6.56 |
| matched_binning_2 | Ni vs Cu | 0.00 | 0.000 | 1.00 | 0.00 | Ni 0.00, Cu 0.00 | – | 0.0011 | 0.23 | 6.24 |

Confusion matrices (rows = true phase; columns = predicted, ambiguous, unindexed/other):

- **baseline**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **pc_error_0.01**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 1, 95, 0], [0, 0, 100, 0]]
- **identical_masters**: ['Ni', 'Ni_copy', 'ambiguous', 'unindexed/other'] → [[0, 0, 196, 0], [0, 0, 0, 0]]
- **lattice_sweep_1%**: ['Ni', 'Ni+1%', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_route**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **matched_fine_route**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **counts_50**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **counts_2000**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **pc_error_0.005**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **pc_error_0.02**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **binning_2**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 0, 100, 0]]
- **step_3deg**: ['Ni', 'Cu', 'ambiguous', 'unindexed/other'] → [[0, 0, 96, 0], [0, 1, 99, 0]]
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
