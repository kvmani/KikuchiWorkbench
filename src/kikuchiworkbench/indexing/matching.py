"""Normalised cross-correlation matching with bounded batches.

Backends: NumPy/BLAS (CPU reference) and optional PyTorch CUDA. ``auto``
selects CUDA when available and falls back to smaller chunks and then CPU on
recoverable device/memory errors; every change is reported through
``on_event`` so it can be recorded in the run manifest.

Tie policy (deterministic): candidates are ranked by descending score, then by
ascending dictionary index. Scores are float32 dot products of zero-mean,
unit-norm patterns (NCC in [-1, 1]).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


def normalize(patterns: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Flatten to (n, p) over unmasked pixels, zero mean, unit L2 norm (float32)."""
    x = np.asarray(patterns, dtype=np.float32).reshape(patterns.shape[0], -1)
    if mask is not None:
        x = x[:, np.asarray(mask, dtype=bool).ravel()]
    x = x - x.mean(axis=1, keepdims=True)
    nrm = np.linalg.norm(x, axis=1, keepdims=True)
    return np.divide(x, nrm, out=np.zeros_like(x), where=nrm > 0)


class TopK:
    """Running top-k (score, dictionary index) per experimental pattern.

    Ranking is by descending score, then ascending dictionary index, so results
    are independent of chunk sizes and backend ordering.
    """

    def __init__(self, n: int, k: int):
        self.k = k
        self.scores = np.full((n, k), -np.inf, dtype=np.float32)
        self.index = np.full((n, k), np.iinfo(np.int64).max, dtype=np.int64)

    def update(self, row0: int, block: np.ndarray, col0: int) -> None:
        block = np.asarray(block, dtype=np.float32)
        m, d = block.shape
        k = min(self.k, d)
        if d > k:
            cand = np.argpartition(-block, k - 1, axis=1)[:, :k]
            cand_s = np.take_along_axis(block, cand, axis=1)
            # rows where values equal to the k-th score were left out need a full stable sort
            kth = cand_s.min(axis=1, keepdims=True)
            boundary_ties = np.count_nonzero(block >= kth, axis=1) > k
            if boundary_ties.any():
                rows = np.nonzero(boundary_ties)[0]
                full = np.argsort(-block[rows], axis=1, kind="stable")[:, :k]
                cand[rows] = full
                cand_s[rows] = np.take_along_axis(block[rows], full, axis=1)
        else:
            cand = np.broadcast_to(np.arange(d), (m, d)).copy()
            cand_s = block.copy()
        sl = slice(row0, row0 + m)
        all_s = np.concatenate([self.scores[sl], cand_s], axis=1)
        all_i = np.concatenate([self.index[sl], cand.astype(np.int64) + col0], axis=1)
        order = _lexsort_rows(all_i, -all_s)[:, : self.k]
        self.scores[sl] = np.take_along_axis(all_s, order, axis=1)
        self.index[sl] = np.take_along_axis(all_i, order, axis=1)

    def valid_index(self) -> np.ndarray:
        return np.where(np.isfinite(self.scores), self.index, -1)


def _lexsort_rows(secondary: np.ndarray, primary: np.ndarray) -> np.ndarray:
    """Row-wise lexsort: sort by ``primary`` then ``secondary`` (both ascending)."""
    # stable argsort on secondary, then stable argsort on primary
    o1 = np.argsort(secondary, axis=1, kind="stable")
    p = np.take_along_axis(primary, o1, axis=1)
    o2 = np.argsort(p, axis=1, kind="stable")
    return np.take_along_axis(o1, o2, axis=1)


@dataclass
class CPUBackend:
    name: str = "cpu"

    def scores(self, exp: np.ndarray, dic: np.ndarray) -> np.ndarray:
        return exp @ dic.T


class TorchCUDABackend:
    name = "cuda"

    def __init__(self, device: str = "cuda"):
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available to PyTorch")
        self.torch = torch
        self.device = torch.device(device)
        self.device_name = torch.cuda.get_device_name(self.device)

    def scores(self, exp: np.ndarray, dic: np.ndarray) -> np.ndarray:
        t = self.torch
        e = t.from_numpy(np.ascontiguousarray(exp)).to(self.device)
        d = t.from_numpy(np.ascontiguousarray(dic)).to(self.device)
        out = (e @ d.T).float().cpu().numpy()
        del e, d
        return out

    def peak_memory_bytes(self) -> int:
        return int(self.torch.cuda.max_memory_allocated(self.device))


def cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def select_backend(requested: str, on_event: Callable[[str, str, dict], None] | None = None):
    """Return a backend for 'cpu', 'gpu'/'cuda' or 'auto'."""
    ev = on_event or (lambda *a, **k: None)
    req = requested.lower()
    if req == "cpu":
        return CPUBackend()
    if req in ("gpu", "cuda"):
        return TorchCUDABackend()
    if req == "auto":
        if cuda_available():
            try:
                return TorchCUDABackend()
            except Exception as e:  # pragma: no cover - depends on hardware
                ev("fallback", f"CUDA backend unavailable ({e}); using CPU", {})
                return CPUBackend()
        ev("backend", "No CUDA device available; using CPU", {})
        return CPUBackend()
    raise ValueError(f"Unknown compute backend {requested!r} (auto, cpu, gpu)")


def _is_oom(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return isinstance(exc, MemoryError) or "out of memory" in msg or "cuda error" in msg


class Matcher:
    """Scores experimental blocks against dictionary blocks with recoverable fallback."""

    def __init__(self, backend, pattern_chunk: int, min_chunk: int = 16,
                 on_event: Callable[[str, str, dict], None] | None = None,
                 allow_cpu_fallback: bool = True):
        self.backend = backend
        self.pattern_chunk = pattern_chunk
        self.min_chunk = min_chunk
        self.on_event = on_event or (lambda *a, **k: None)
        self.allow_cpu_fallback = allow_cpu_fallback

    def match_block(self, exp: np.ndarray, dic: np.ndarray, topk: TopK, row0: int, col0: int) -> None:
        n = exp.shape[0]
        i0 = 0
        while i0 < n:
            i1 = min(n, i0 + self.pattern_chunk)
            try:
                s = self.backend.scores(exp[i0:i1], dic)
            except Exception as e:
                if not _is_oom(e):
                    raise
                if self.pattern_chunk > self.min_chunk:
                    old = self.pattern_chunk
                    self.pattern_chunk = max(self.min_chunk, self.pattern_chunk // 2)
                    self.on_event("batch_size_change", f"{self.backend.name}: out of memory; pattern "
                                  f"chunk {old} -> {self.pattern_chunk}",
                                  {"old": old, "new": self.pattern_chunk})
                    continue
                if self.allow_cpu_fallback and self.backend.name != "cpu":
                    self.on_event("fallback", f"{self.backend.name} failed at minimum chunk; "
                                  "falling back to CPU", {"error": str(e)})
                    self.backend = CPUBackend()
                    continue
                raise
            topk.update(row0 + i0, s, col0)
            i0 = i1
