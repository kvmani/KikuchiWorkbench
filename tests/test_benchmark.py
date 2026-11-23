from kikuchiworkbench.benchmark import conditions, select_threshold


def _rows(spec):
    return [{"ambiguity_margin": m, "coverage": c, "n_indexed": n, "error_among_indexed": e}
            for m, c, n, e in spec]


def test_select_smallest_margin_meeting_target():
    rows = _rows([(0.0, 1.0, 100, 0.05), (0.01, 0.8, 80, 0.008), (0.02, 0.5, 50, 0.0)])
    s = select_threshold(rows, 0.01, min_indexed=10)
    assert s["ambiguity_margin"] == 0.01 and s["met_target"]


def test_selection_requires_enough_indexed_points():
    rows = _rows([(0.0, 1.0, 100, 0.5), (0.05, 0.03, 2, 0.0)])
    s = select_threshold(rows, 0.01, min_indexed=10)
    assert not s["met_target"] and s["ambiguity_margin"] == 0.05


def test_conditions_cover_scope():
    names = {c["name"] for c in conditions("full")}
    for required in ("baseline", "identical_masters", "mixed_50_50", "binning_2", "pc_error_0.01",
                     "counts_50", "step_6deg", "lattice_sweep_0.5%", "matched_route"):
        assert required in names
    assert len(conditions("quick")) < len(conditions("full"))
