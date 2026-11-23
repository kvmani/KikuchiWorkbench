"""numpy -> QImage/QPixmap helpers."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap


def to_qimage(arr: np.ndarray, vmin=None, vmax=None) -> QImage:
    a = np.asarray(arr)
    if a.ndim == 2:
        a = a.astype(np.float64)
        finite = np.isfinite(a)
        lo = np.nanmin(a[finite]) if vmin is None and finite.any() else (vmin or 0.0)
        hi = np.nanmax(a[finite]) if vmax is None and finite.any() else (vmax or 1.0)
        g = np.zeros_like(a)
        if hi > lo:
            g = (a - lo) / (hi - lo)
        g = np.where(finite, g, 1.0)
        u8 = np.ascontiguousarray((np.clip(g, 0, 1) * 255).astype(np.uint8))
        h, w = u8.shape
        return QImage(u8.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    if a.ndim == 3 and a.shape[2] == 3:
        rgb = a.astype(np.float64)
        if rgb.max() > 1.0:
            rgb = rgb / 255.0
        u8 = np.ascontiguousarray((np.clip(np.nan_to_num(rgb, nan=1.0), 0, 1) * 255).astype(np.uint8))
        h, w, _ = u8.shape
        return QImage(u8.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    raise ValueError(f"Cannot display array of shape {a.shape}")


def to_pixmap(arr: np.ndarray, size: int = 240, **kw) -> QPixmap:
    from PySide6.QtCore import Qt

    img = to_qimage(arr, **kw)
    return QPixmap.fromImage(img).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.FastTransformation)
