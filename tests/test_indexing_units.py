import numpy as np
import pytest

from kikuchiworkbench.indexing.decision import (
    LABEL_AMBIGUOUS,
    LABEL_INDEXED,
    LABEL_LOW_SIGNAL,
    LABEL_MISSING,
    LABEL_UNINDEXED,
    DecisionPolicy,
    decide,
)
from kikuchiworkbench.indexing.matching import CPUBackend, Matcher, TopK, normalize, select_backend
from kikuchiworkbench.indexing.preprocessing import Preprocessor, signal_metric, validate_pipeline


def test_normalize():
    x = np.random.default_rng(0).random((5, 4, 4))
    y = normalize(x)
    np.testing.assert_allclose(y.mean(axis=1), 0, atol=1e-6)
    np.testing.assert_allclose(np.linalg.norm(y, axis=1), 1, atol=1e-6)
    m = np.zeros((4, 4), bool)
    m[1:3, 1:3] = True
    assert normalize(x, m).shape == (5, 4)
    assert np.all(normalize(np.ones((2, 3, 3))) == 0)  # constant pattern -> zero vector


@pytest.mark.parametrize("chunk", [1, 3, 17, 64])
def test_topk_chunk_invariant_with_ties(chunk):
    rng = np.random.default_rng(1)
    s = rng.integers(0, 10, (20, 64)).astype(np.float32)
    ref = np.argsort(-s, axis=1, kind="stable")[:, :4]
    t = TopK(20, 4)
    for c0 in range(0, 64, chunk):
        t.update(0, s[:, c0:c0 + chunk], c0)
    np.testing.assert_array_equal(t.index, ref)


def test_topk_fewer_candidates_than_k():
    t = TopK(2, 5)
    t.update(0, np.array([[0.5, 0.2], [0.1, 0.9]], np.float32), 0)
    assert list(t.valid_index()[0]) == [0, 1, -1, -1, -1]


class _OOMBackend:
    name = "fakegpu"

    def __init__(self, fail_above):
        self.fail_above = fail_above
        self.calls = 0

    def scores(self, e, d):
        self.calls += 1
        if e.shape[0] > self.fail_above:
            raise RuntimeError("CUDA out of memory (simulated)")
        return e @ d.T


def test_matcher_shrinks_batch_and_falls_back():
    rng = np.random.default_rng(2)
    e = normalize(rng.random((40, 10)))
    d = normalize(rng.random((30, 10)))
    events = []
    m = Matcher(_OOMBackend(fail_above=10), pattern_chunk=40, min_chunk=4,
                on_event=lambda k, msg, data: events.append(k))
    t = TopK(40, 3)
    m.match_block(e, d, t, 0, 0)
    assert "batch_size_change" in events and m.pattern_chunk <= 10 and m.backend.name == "fakegpu"
    ref = TopK(40, 3)
    ref.update(0, e @ d.T, 0)
    np.testing.assert_array_equal(t.index, ref.index)
    events.clear()
    m2 = Matcher(_OOMBackend(fail_above=0), pattern_chunk=8, min_chunk=4,
                 on_event=lambda k, msg, data: events.append(k))
    t2 = TopK(40, 3)
    m2.match_block(e, d, t2, 0, 0)
    assert "fallback" in events and m2.backend.name == "cpu"
    np.testing.assert_array_equal(t2.index, ref.index)


def test_select_backend():
    assert select_backend("cpu").name == "cpu"
    ev = []
    b = select_backend("auto", on_event=lambda k, m, d: ev.append(k))
    assert b.name in ("cpu", "cuda")
    with pytest.raises(ValueError):
        select_backend("tpu")
    assert isinstance(CPUBackend().scores(np.ones((1, 2), np.float32), np.ones((3, 2), np.float32)), np.ndarray)


def test_decision_labels_distinct():
    s = np.array([
        [0.60, 0.40],  # indexed phase 0
        [0.50, 0.50],  # exact tie -> ambiguous
        [0.50, 0.498],  # margin below threshold -> ambiguous
        [0.05, 0.03],  # unindexed (low score)
        [0.70, 0.20],  # low signal flag
        [0.70, 0.20],  # missing
        [0.30, 0.45],  # indexed phase 1
    ])
    sig = np.array([2, 2, 2, 2, 0.1, 2, 2])
    valid = np.array([1, 1, 1, 1, 1, 0, 1], bool)
    d = decide(s, DecisionPolicy(min_score=0.1, ambiguity_margin=0.005, min_signal=0.5), sig, valid)
    assert list(d.label) == [LABEL_INDEXED, LABEL_AMBIGUOUS, LABEL_AMBIGUOUS, LABEL_UNINDEXED,
                             LABEL_LOW_SIGNAL, LABEL_MISSING, LABEL_INDEXED]
    assert list(d.phase) == [0, -1, -1, -1, -1, -1, 1]
    assert d.tie[1] and not d.tie[2]
    assert d.margin[0] == pytest.approx(0.2)
    assert d.best_phase_any[1] == 0  # deterministic tie-break for display only
    assert d.counts()["ambiguous"] == 2


def test_decision_single_phase():
    d = decide(np.array([[0.5], [0.01]]), DecisionPolicy())
    assert list(d.label) == [LABEL_INDEXED, LABEL_UNINDEXED]
    assert np.isnan(d.margin).all()


def test_preprocessing_does_not_modify_input():
    rng = np.random.default_rng(3)
    raw = rng.integers(0, 1000, (4, 20, 24)).astype(np.uint16)
    raw.flags.writeable = False
    pre = Preprocessor([{"op": "static_background", "source": "scan_mean"},
                        {"op": "dynamic_background", "sigma_frac": 0.125},
                        {"op": "bin", "factor": 2}, {"op": "mask", "radius_frac": 0.5}], (20, 24))
    pre.static_background = raw.mean(axis=0).astype(np.float32)
    out = pre.apply_experimental(raw)
    assert out.shape == (4, 10, 12) and pre.output_shape == (10, 12)
    assert pre.mask().sum() < 120
    assert pre.apply_simulated(np.ones((2, 20, 24))).shape == (2, 10, 12)
    d = pre.describe()
    assert d["pattern_shape_out"] == [10, 12] and d["static_background_sha256"]
    assert pre.key() != Preprocessor([], (20, 24)).key()
    with pytest.raises(ValueError):
        validate_pipeline([{"op": "sharpen"}])


def test_signal_metric_separates_noise():
    rng = np.random.default_rng(4)
    yy, xx = np.mgrid[:40, :40]
    bands = np.sin(xx / 3.0)[None] * 50 + 100
    struct = rng.poisson(np.repeat(bands, 5, 0)).astype(float)
    noise = rng.poisson(np.full((5, 40, 40), 100.0)).astype(float)
    assert signal_metric(struct).min() > 2 * signal_metric(noise).max()
