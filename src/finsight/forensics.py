"""Ratios and forensic screens. Screening indicators, not verdicts. Not valid for banks/insurers."""
from __future__ import annotations

from typing import Optional, Sequence

from .schemas import Financials


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _ebit(fs: Financials) -> Optional[float]:
    e = fs.val("ebit")
    if e is not None:
        return e
    pt, ie = fs.val("pretax_income"), fs.val("interest_expense")
    return None if pt is None or ie is None else pt + abs(ie)


def _total_liabilities(fs: Financials) -> Optional[float]:
    tl = fs.val("total_liabilities")
    if tl is not None:
        return tl
    ta, te = fs.val("total_assets"), fs.val("total_equity")
    return None if ta is None or te is None else ta - te


def _cite(fs: Financials, *names: str) -> list[str]:
    out = []
    for n in names:
        v, p = fs.val(n), fs.page(n)
        if v is not None and p is not None:
            out.append(f"{n}={v:,.2f} [p.{p}]")
    return out


def dupont5(fs: Financials) -> dict:
    ni, rev, ta, te = fs.val("net_income"), fs.val("revenue"), fs.val("total_assets"), fs.val("total_equity")
    ebit = _ebit(fs)
    ebt = fs.val("pretax_income")
    if ebt is None and ebit is not None and fs.val("interest_expense") is not None:
        ebt = ebit - abs(fs.val("interest_expense"))
    parts = {
        "tax_burden": _div(ni, ebt), "interest_burden": _div(ebt, ebit), "ebit_margin": _div(ebit, rev),
        "asset_turnover": _div(rev, ta), "equity_multiplier": _div(ta, te),
    }
    missing = [k for k, v in parts.items() if v is None]
    if missing:
        return {"available": False, "missing": missing}
    roe = 1.0
    for v in parts.values():
        roe *= v  # type: ignore[operator]
    direct = _div(ni, te)
    return {"available": True, **parts, "roe_reconstructed": roe, "roe_direct": direct,
            "reconciles": direct is not None and abs(roe - direct) < 1e-6,
            "citations": _cite(fs, "net_income", "pretax_income", "ebit", "revenue", "total_assets", "total_equity"),
            "note": "end-of-period balances; no averaging"}


def altman_z_double_prime(fs: Financials) -> dict:
    """Z'' (non-manufacturers / emerging markets); needs no market cap. Zones: >2.6 safe, 1.1-2.6 grey, <1.1 distress."""
    ca, cl, ta = fs.val("current_assets"), fs.val("current_liabilities"), fs.val("total_assets")
    re_, ebit, te, tl = fs.val("retained_earnings"), _ebit(fs), fs.val("total_equity"), _total_liabilities(fs)
    x = {
        "x1_working_capital_ta": _div(None if ca is None or cl is None else ca - cl, ta),
        "x2_retained_earnings_ta": _div(re_, ta), "x3_ebit_ta": _div(ebit, ta), "x4_equity_tl": _div(te, tl),
    }
    missing = [k for k, v in x.items() if v is None]
    if missing:
        return {"available": False, "missing": missing}
    z = 6.56 * x["x1_working_capital_ta"] + 3.26 * x["x2_retained_earnings_ta"] + 6.72 * x["x3_ebit_ta"] + 1.05 * x["x4_equity_tl"]  # type: ignore[operator]
    zone = "safe" if z > 2.6 else "grey" if z >= 1.1 else "distress"
    return {"available": True, **x, "z": z, "zone": zone}


def altman_z_original(fs: Financials, market_cap: float) -> dict:
    """Original Z (public manufacturers). market_cap in the SAME unit scale as the filing. Zones: >2.99, 1.81-2.99, <1.81."""
    ca, cl, ta = fs.val("current_assets"), fs.val("current_liabilities"), fs.val("total_assets")
    re_, ebit, rev, tl = fs.val("retained_earnings"), _ebit(fs), fs.val("revenue"), _total_liabilities(fs)
    x = {
        "x1": _div(None if ca is None or cl is None else ca - cl, ta), "x2": _div(re_, ta), "x3": _div(ebit, ta),
        "x4": _div(market_cap, tl), "x5": _div(rev, ta),
    }
    missing = [k for k, v in x.items() if v is None]
    if missing:
        return {"available": False, "missing": missing}
    z = 1.2 * x["x1"] + 1.4 * x["x2"] + 3.3 * x["x3"] + 0.6 * x["x4"] + 1.0 * x["x5"]  # type: ignore[operator]
    zone = "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"
    return {"available": True, **x, "z": z, "zone": zone}


BENEISH_THRESHOLD = -1.78  # 8-variable model; some practitioners use -2.22 (more sensitive)


def beneish_m(fs: Financials, threshold: float = BENEISH_THRESHOLD) -> dict:
    g = lambda n: (fs.val(n), fs.prior(n))  # noqa: E731
    (ar1, ar0), (rv1, rv0), (cg1, cg0) = g("receivables"), g("revenue"), g("cogs")
    (ca1, ca0), (pp1, pp0), (ta1, ta0) = g("current_assets"), g("ppe_net"), g("total_assets")
    (dp1, dp0), (sg1, sg0) = g("depreciation_amortization"), g("sga")
    (cl1, cl0), (lt1, lt0) = g("current_liabilities"), g("long_term_debt")
    ni, cfo = fs.val("net_income"), fs.val("cfo")

    def gm(rev, cogs):
        return None if rev in (None, 0) or cogs is None else (rev - cogs) / rev

    def aq(ca, pp, ta):
        return None if None in (ca, pp, ta) or ta == 0 else 1 - (ca + pp) / ta

    def dep_rate(dp, pp):
        return None if None in (dp, pp) or (dp + pp) == 0 else dp / (dp + pp)

    def lev(cl, lt, ta):
        return None if None in (cl, lt, ta) or ta == 0 else (cl + lt) / ta

    idx = {
        "DSRI": _div(_div(ar1, rv1), _div(ar0, rv0)),
        "GMI": _div(gm(rv0, cg0), gm(rv1, cg1)),
        "AQI": _div(aq(ca1, pp1, ta1), aq(ca0, pp0, ta0)),
        "SGI": _div(rv1, rv0),
        "DEPI": _div(dep_rate(dp0, pp0), dep_rate(dp1, pp1)),
        "SGAI": _div(_div(sg1, rv1), _div(sg0, rv0)),
        "LVGI": _div(lev(cl1, lt1, ta1), lev(cl0, lt0, ta0)),
        "TATA": None if None in (ni, cfo) else _div(ni - cfo, ta1),  # type: ignore[operator]
    }
    if idx["TATA"] is None and ni is not None and cfo is not None and ta1 == 0:
        idx["TATA"] = None
    missing = [k for k, v in idx.items() if v is None]
    if missing:
        return {"available": False, "missing": missing}
    m = (-4.84 + 0.920 * idx["DSRI"] + 0.528 * idx["GMI"] + 0.404 * idx["AQI"] + 0.892 * idx["SGI"]
         + 0.115 * idx["DEPI"] - 0.172 * idx["SGAI"] + 4.679 * idx["TATA"] - 0.327 * idx["LVGI"])  # type: ignore[operator]
    return {"available": True, **idx, "m_score": m, "threshold": threshold, "flag": m > threshold,
            "note": "AQI omits marketable securities; net income used as proxy for income from continuing ops"}


def piotroski_f(fs: Financials) -> dict:
    """Simplified 9-signal F-score on end-of-period balances. Signals that cannot be evaluated are None."""
    ni, ni0 = fs.val("net_income"), fs.prior("net_income")
    ta, ta0 = fs.val("total_assets"), fs.prior("total_assets")
    cfo = fs.val("cfo")
    roa, roa0 = _div(ni, ta), _div(ni0, ta0)
    lev, lev0 = _div(fs.val("long_term_debt"), ta), _div(fs.prior("long_term_debt"), ta0)
    cr = _div(fs.val("current_assets"), fs.val("current_liabilities"))
    cr0 = _div(fs.prior("current_assets"), fs.prior("current_liabilities"))
    sh, sh0 = fs.val("shares_outstanding"), fs.prior("shares_outstanding")

    def gmr(rev, cogs):
        return None if rev in (None, 0) or cogs is None else (rev - cogs) / rev

    gm, gm0 = gmr(fs.val("revenue"), fs.val("cogs")), gmr(fs.prior("revenue"), fs.prior("cogs"))
    at, at0 = _div(fs.val("revenue"), ta), _div(fs.prior("revenue"), ta0)

    def cmp(a, b, op):
        return None if a is None or b is None else op(a, b)

    signals = {
        "roa_positive": None if roa is None else roa > 0,
        "cfo_positive": None if cfo is None else cfo > 0,
        "roa_improving": cmp(roa, roa0, lambda a, b: a > b),
        "cfo_exceeds_net_income": cmp(cfo, ni, lambda a, b: a > b),
        "leverage_falling": cmp(lev, lev0, lambda a, b: a < b),
        "current_ratio_improving": cmp(cr, cr0, lambda a, b: a > b),
        "no_dilution": cmp(sh, sh0, lambda a, b: a <= b),
        "gross_margin_improving": cmp(gm, gm0, lambda a, b: a > b),
        "asset_turnover_improving": cmp(at, at0, lambda a, b: a > b),
    }
    ev = [v for v in signals.values() if v is not None]
    return {"signals": signals, "score": sum(1 for v in ev if v), "evaluable": len(ev), "of": 9,
            "note": "simplified: end-of-period assets used for ROA and turnover"}


def cash_conversion(fs: Financials) -> Optional[float]:
    return _div(fs.val("cfo"), fs.val("net_income"))


def accrual_ratio(fs: Financials) -> Optional[float]:
    ni, cfo = fs.val("net_income"), fs.val("cfo")
    return None if ni is None or cfo is None else _div(ni - cfo, fs.val("total_assets"))


def non_gaap_bloat(gaap: float, non_gaap: float) -> Optional[float]:
    return _div(non_gaap - gaap, abs(gaap))


def low_conversion_streak(cfo: Sequence[float], ni: Sequence[float], threshold: float = 1.0, n: int = 3) -> bool:
    """True if CFO/NI < threshold for n consecutive periods (oldest first). Skips periods with NI <= 0."""
    run = 0
    for c, i in zip(cfo, ni):
        if i is None or i <= 0 or c is None:
            run = 0
            continue
        run = run + 1 if c / i < threshold else 0
        if run >= n:
            return True
    return False


def run_all(fs: Financials, market_cap: Optional[float] = None) -> dict:
    flags = []
    cc, ar = cash_conversion(fs), accrual_ratio(fs)
    if cc is not None and cc < 0.8:
        flags.append("LOW_CASH_CONVERSION: CFO < 0.8 x net income")
    if ar is not None and ar > 0.05:
        flags.append("HIGH_ACCRUALS: (NI-CFO)/assets > 5%")
    bloats = []
    for rec in fs.reconciliations:
        b = non_gaap_bloat(rec.gaap_value.value, rec.reported_non_gaap.value)
        bloats.append({"metric": rec.metric, "bloat": b, "page": rec.reported_non_gaap.prov.page})
        if b is not None and b > 0.25:
            flags.append(f"NON_GAAP_BLOAT: {rec.metric} exceeds GAAP by {b:.0%}")
    bm = beneish_m(fs)
    if bm.get("flag"):
        flags.append(f"BENEISH_M above threshold ({bm['m_score']:.2f} > {bm['threshold']})")
    out = {
        "dupont5": dupont5(fs), "altman_z_double_prime": altman_z_double_prime(fs), "beneish_m": bm,
        "piotroski_f": piotroski_f(fs), "cash_conversion": cc, "accrual_ratio": ar, "non_gaap_bloat": bloats,
        "flags": flags, "disclaimer": "Screening indicators only; not investment advice.",
    }
    if market_cap is not None:
        out["altman_z_original"] = altman_z_original(fs, market_cap)
    return out
