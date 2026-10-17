"""Distribution-first DCF: sensitivity matrix + Monte Carlo. Numbers are assumption-driven, not 'intrinsic truth'."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class DCFInputs:
    revenue0: float
    growth_start: float          # year-1 revenue growth
    growth_terminal: float       # perpetual growth g; growth fades linearly to this by the final year
    margin_start: float          # year-1 EBIT margin
    margin_target: float         # EBIT margin reached in the final year
    tax_rate: float
    sales_to_capital: float      # reinvestment = delta revenue / sales_to_capital
    wacc: float
    net_debt: float
    shares: float
    years: int = 10
    terminal_roic: Optional[float] = None  # defaults to WACC (no value creation in perpetuity)


def _value_per_share(rev0, g1, g_term, m0, m_t, tax, s2c, wacc, net_debt, shares, years, terminal_roic):
    g1, g_term, m0, m_t, wacc = (np.atleast_1d(np.asarray(x, dtype=float)) for x in (g1, g_term, m0, m_t, wacc))
    n = max(len(x) for x in (g1, g_term, m0, m_t, wacc))
    g1, g_term, m0, m_t, wacc = (np.broadcast_to(x, (n,)) for x in (g1, g_term, m0, m_t, wacc))
    t = np.arange(1, years + 1)
    frac = (t - 1) / max(years - 1, 1)
    growth = g1[:, None] + (g_term[:, None] - g1[:, None]) * frac
    margin = m0[:, None] + (m_t[:, None] - m0[:, None]) * frac
    rev = rev0 * np.cumprod(1.0 + growth, axis=1)
    prev = np.concatenate([np.full((n, 1), rev0), rev[:, :-1]], axis=1)
    nopat = rev * margin * (1.0 - tax)
    fcff = nopat - (rev - prev) / s2c
    pv = (fcff / (1.0 + wacc[:, None]) ** t).sum(axis=1)
    roic = wacc if terminal_roic is None else np.full(n, terminal_roic)
    fcff_term = nopat[:, -1] * (1.0 + g_term) * (1.0 - g_term / roic)
    tv = fcff_term / (wacc - g_term)
    ev = pv + tv / (1.0 + wacc) ** years
    return (ev - net_debt) / shares


def value_per_share(i: DCFInputs) -> float:
    if i.wacc <= i.growth_terminal:
        raise ValueError("WACC must exceed terminal growth")
    return float(_value_per_share(i.revenue0, i.growth_start, i.growth_terminal, i.margin_start, i.margin_target,
                                  i.tax_rate, i.sales_to_capital, i.wacc, i.net_debt, i.shares, i.years,
                                  i.terminal_roic)[0])


def sensitivity_matrix(i: DCFInputs, waccs: Sequence[float], gs: Sequence[float]) -> dict:
    rows = []
    for w in waccs:
        row = []
        for g in gs:
            if w <= g:
                row.append(None)
                continue
            row.append(float(_value_per_share(i.revenue0, i.growth_start, g, i.margin_start, i.margin_target,
                                              i.tax_rate, i.sales_to_capital, w, i.net_debt, i.shares, i.years,
                                              i.terminal_roic)[0]))
        rows.append(row)
    return {"waccs": list(waccs), "terminal_growths": list(gs), "value_per_share": rows}


def monte_carlo(i: DCFInputs, n: int = 10_000, seed: int = 7, price: Optional[float] = None,
                growth_sigma: float = 0.03, margin_spread: float = 0.05, wacc_sigma: float = 0.01,
                g_spread: float = 0.01) -> dict:
    rng = np.random.default_rng(seed)
    g1 = np.clip(rng.normal(i.growth_start, growth_sigma, n), -0.2, 0.6)
    m_t = rng.triangular(i.margin_target - margin_spread, i.margin_target, i.margin_target + margin_spread, n)
    wacc = np.clip(rng.normal(i.wacc, wacc_sigma, n), 0.04, None)
    g = rng.triangular(i.growth_terminal - g_spread, i.growth_terminal, i.growth_terminal + g_spread, n)
    g = np.clip(g, 0.0, wacc - 0.01)  # enforce WACC > g
    v = _value_per_share(i.revenue0, g1, g, i.margin_start, m_t, i.tax_rate, i.sales_to_capital, wacc,
                         i.net_debt, i.shares, i.years, i.terminal_roic)
    v = v[np.isfinite(v)]
    p10, p50, p90 = (float(x) for x in np.percentile(v, [10, 50, 90]))
    out = {"n": int(len(v)), "seed": seed, "p10": p10, "p50": p50, "p90": p90, "mean": float(v.mean()),
           "note": "Distribution reflects assumption uncertainty only; it is not a forecast or investment advice."}
    if price is not None:
        out["prob_value_above_price"] = float((v > price).mean())
    return out
