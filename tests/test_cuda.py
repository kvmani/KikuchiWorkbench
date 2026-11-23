import numpy as np
import pytest

from kikuchiworkbench.indexing.matching import CPUBackend, cuda_available, normalize

pytestmark = pytest.mark.cuda


@pytest.mark.skipif(not cuda_available(), reason="PyTorch CUDA not available")
def test_cuda_scores_match_cpu():
    from kikuchiworkbench.indexing.matching import TorchCUDABackend

    rng = np.random.default_rng(0)
    e = normalize(rng.random((257, 900)))
    d = normalize(rng.random((1001, 900)))
    c = CPUBackend().scores(e, d)
    g = TorchCUDABackend().scores(e, d)
    assert np.max(np.abs(c - g)) < 1e-5
