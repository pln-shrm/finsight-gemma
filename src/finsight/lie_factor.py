"""Tufte lie factor and baseline-truncation checks. Pure math: geometry comes from CV, semantics from the model."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

TOLERANCE = 0.05  # Tufte: LF within 1 +/- 0.05 is acceptable


@dataclass
class LieFactorResult:
    lie_factor: Optional[float]
    graphic_effect: Optional[float]
    data_effect: Optional[float]
    verdict: Literal["faithful", "distorted", "undefined"]
    severity: Literal["ok", "warn", "alert", "n/a"]


def _classify(lf: Optional[float], tol: float) -> tuple[str, str]:
    if lf is None:
        return "undefined", "n/a"
    dev = math.inf if math.isinf(lf) else abs(lf - 1.0)
    if dev <= tol:
        return "faithful", "ok"
    return "distorted", "warn" if dev <= 0.25 else "alert"


def lie_factor(h1: float, h2: float, v1: float, v2: float, tol: float = TOLERANCE) -> LieFactorResult:
    """LF = (relative change shown in graphic) / (relative change in data)."""
    if v1 == 0 or h1 == 0:
        return LieFactorResult(None, None, None, "undefined", "n/a")
    ge, de = (h2 - h1) / h1, (v2 - v1) / v1
    if de == 0:
        lf = 1.0 if ge == 0 else math.inf
    else:
        lf = ge / de
    verdict, sev = _classify(lf, tol)
    return LieFactorResult(lf, ge, de, verdict, sev)  # type: ignore[arg-type]


def lie_factor_from_axis(v1: float, v2: float, axis_min: float, tol: float = TOLERANCE) -> LieFactorResult:
    """Analytic LF when bar height is proportional to (value - axis_min). No pixel measurement required."""
    return lie_factor(v1 - axis_min, v2 - axis_min, v1, v2, tol)


def baseline_truncated(axis_min: Optional[float], values: Sequence[float]) -> bool:
    return axis_min is not None and axis_min > 0 and all(v > 0 for v in values)


def audit_bar_chart(
    labels: Sequence[str], values: Sequence[float], axis_min: Optional[float] = None,
    pixel_heights: Optional[Sequence[float]] = None, tol: float = TOLERANCE,
) -> dict:
    """Worst adjacent-pair lie factor. Prefer measured pixel heights; fall back to the analytic axis model."""
    pairs = []
    for i in range(len(values) - 1):
        if pixel_heights is not None:
            res = lie_factor(pixel_heights[i], pixel_heights[i + 1], values[i], values[i + 1], tol)
            basis = "pixels"
        elif axis_min is not None:
            res = lie_factor_from_axis(values[i], values[i + 1], axis_min, tol)
            basis = "axis_model"
        else:
            continue
        pairs.append({"from": labels[i], "to": labels[i + 1], "basis": basis, **res.__dict__})
    ranked = [p for p in pairs if p["lie_factor"] is not None]
    worst = max(ranked, key=lambda p: math.inf if math.isinf(p["lie_factor"]) else abs(p["lie_factor"] - 1.0), default=None)
    return {
        "baseline_truncated": baseline_truncated(axis_min, values),
        "axis_min": axis_min,
        "pairs": pairs,
        "worst": worst,
        "flag": bool(worst and worst["verdict"] == "distorted"),
    }
