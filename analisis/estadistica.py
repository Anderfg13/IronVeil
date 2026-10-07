"""Estadistica basica compartida por los scripts de analisis (solo stdlib)."""

from __future__ import annotations

import math

Z_95 = 1.96


def intervalo_wilson(exitos: int, total: int) -> tuple[float, float]:
    """Intervalo de confianza de Wilson al 95 % para una proporcion (0-1)."""
    if total <= 0:
        return (float("nan"), float("nan"))
    p = exitos / total
    z2 = Z_95**2
    centro = (p + z2 / (2 * total)) / (1 + z2 / total)
    margen = (
        Z_95 * math.sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / (1 + z2 / total)
    )
    return (max(0.0, centro - margen), min(1.0, centro + margen))
