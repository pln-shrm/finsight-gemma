"""Deterministic accounting-conservation verifier. Produces targeted retry prompts for the model."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

from .schemas import Financials

Severity = Literal["error", "warning"]

_SCALE_NOTES = {
    10.0: "possible decimal shift", 100.0: "lakhs vs crores mix-up",
    1_000.0: "thousands vs millions mix-up", 100_000.0: "units vs lakhs mix-up",
    1_000_000.0: "units vs millions mix-up", 10_000_000.0: "units vs crores mix-up",
}


def scale_hint(a: float, b: float, tol: float = 0.02) -> Optional[str]:
    if not a or not b:
        return None
    r = abs(a / b)
    for f, note in _SCALE_NOTES.items():
        if math.isclose(r, f, rel_tol=tol) or math.isclose(r, 1.0 / f, rel_tol=tol):
            return f"the two sides differ by about {f:g}x ({note}); re-check the unit_scale of each statement"
    return None


def _tol(a: float, b: float, rel: float, abs_tol: float) -> float:
    return max(rel * max(abs(a), abs(b)), abs_tol)


@dataclass
class Violation:
    code: str
    severity: Severity
    message: str
    residual: Optional[float] = None
    fields: tuple[str, ...] = ()
    pages: tuple[int, ...] = ()
    hint: Optional[str] = None

    def to_prompt(self) -> str:
        pg = f" (see page(s) {', '.join(map(str, self.pages))})" if self.pages else ""
        res = f" Residual = {self.residual:+,.2f}." if self.residual is not None else ""
        hint = f" Hint: {self.hint}." if self.hint else ""
        return f"[{self.code}] {self.message}{res}{pg}{hint}"


@dataclass
class Report:
    violations: list[Violation] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    checks_skipped: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "error"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def retry_prompt(self) -> Optional[str]:
        if not self.errors:
            return None
        lines = "\n".join(f"- {v.to_prompt()}" for v in self.errors)
        return (
            "Your previous extraction violated accounting constraints:\n" + lines +
            "\nRe-inspect the cited page images. Return the FULL corrected JSON. "
            "If a figure is not clearly visible, return null for it. Do not guess or balance numbers."
        )

    def as_dict(self) -> dict:
        return {"passed": self.passed, "checks_run": self.checks_run,
                "checks_skipped": self.checks_skipped,
                "violations": [asdict(v) for v in self.violations]}


def verify(fs: Financials, rel_tol: float = 0.005, abs_tol: float = 1.0) -> Report:
    r = Report()
    _balance_identity(fs, r, rel_tol, abs_tol)
    _component_bounds(fs, r, rel_tol)
    _cash_bridge(fs, r)
    _retained_earnings(fs, r)
    _cross_statement_scale(fs, r)
    _reconciliations(fs, r, rel_tol, abs_tol)
    _segments(fs, r, rel_tol, abs_tol)
    return r


def _pages(fs: Financials, *names: str) -> tuple[int, ...]:
    return tuple(sorted({p for n in names if (p := fs.page(n)) is not None}))


def _balance_identity(fs, r, rel, abs_tol):
    name = "balance_sheet_identity"
    ta = fs.val("total_assets")
    tle = fs.val("total_liabilities_and_equity")
    tl, te = fs.val("total_liabilities"), fs.val("total_equity")
    if ta is None:
        return r.checks_skipped.append(name)
    if tle is not None:
        rhs, fields = tle, ("total_assets", "total_liabilities_and_equity")
    elif tl is not None and te is not None:
        rhs, fields = tl + te, ("total_assets", "total_liabilities", "total_equity")
    else:
        return r.checks_skipped.append(name)
    r.checks_run.append(name)
    resid = ta - rhs
    if abs(resid) > _tol(ta, rhs, rel, abs_tol):
        r.violations.append(Violation(
            "BALANCE_SHEET_IDENTITY", "error",
            f"Total assets ({ta:,.2f}) != liabilities + equity ({rhs:,.2f}).",
            resid, fields, _pages(fs, *fields),
            scale_hint(ta, rhs) or "check non-controlling interest, mezzanine equity, or a wrong column/year"))
    if tle is not None and tl is not None and te is not None:
        r.checks_run.append("balance_sheet_components_foot")
        resid2 = tle - (tl + te)
        if abs(resid2) > _tol(tle, tl + te, rel, abs_tol):
            r.violations.append(Violation(
                "BALANCE_SHEET_COMPONENTS", "error",
                f"Reported liabilities + equity ({tl + te:,.2f}) != total liabilities and equity ({tle:,.2f}).",
                resid2, ("total_liabilities", "total_equity", "total_liabilities_and_equity"),
                _pages(fs, "total_liabilities", "total_equity"),
                "equity may exclude non-controlling interest"))


def _component_bounds(fs, r, rel):
    r.checks_run.append("component_bounds")
    ta = fs.val("total_assets")
    if ta is None:
        return
    for n in ("current_assets", "ppe_net", "cash", "receivables"):
        v = fs.val(n)
        if v is not None and v > ta * (1 + rel):
            r.violations.append(Violation(
                "COMPONENT_EXCEEDS_TOTAL", "error",
                f"{n} ({v:,.2f}) exceeds total assets ({ta:,.2f}).", v - ta,
                (n, "total_assets"), _pages(fs, n, "total_assets"), "check column alignment or unit scale"))


def _cash_bridge(fs, r):
    name = "cash_flow_bridge"
    c1, c0 = fs.val("cash"), fs.prior("cash")
    cfo, cfi, cff = fs.val("cfo"), fs.val("cfi"), fs.val("cff")
    if None in (c1, c0, cfo, cfi, cff):
        return r.checks_skipped.append(name)
    r.checks_run.append(name)
    fx = fs.val("fx_effect") or 0.0
    resid = (c0 + cfo + cfi + cff + fx) - c1
    if abs(resid) > _tol(c1, c0, 0.05, 2.0):
        r.violations.append(Violation(
            "CASH_BRIDGE", "warning",
            f"Opening cash ({c0:,.2f}) + CFO + CFI + CFF + FX ({cfo + cfi + cff + fx:+,.2f}) != closing cash ({c1:,.2f}).",
            resid, ("cash", "cfo", "cfi", "cff", "fx_effect"), _pages(fs, "cash", "cfo", "cfi", "cff"),
            "look for restricted cash, FX translation, or cash held for sale"))


def _retained_earnings(fs, r):
    name = "retained_earnings_rollforward"
    re1, re0 = fs.val("retained_earnings"), fs.prior("retained_earnings")
    ni, div = fs.val("net_income"), fs.val("dividends_paid")
    if None in (re1, re0, ni, div):
        return r.checks_skipped.append(name)
    r.checks_run.append(name)
    resid = re1 - (re0 + ni - abs(div))
    if abs(resid) > _tol(re1, re0, 0.02, 2.0):
        r.violations.append(Violation(
            "RETAINED_EARNINGS", "warning",
            f"Retained earnings ({re1:,.2f}) != opening ({re0:,.2f}) + net income ({ni:,.2f}) - dividends ({abs(div):,.2f}).",
            resid, ("retained_earnings", "net_income", "dividends_paid"),
            _pages(fs, "retained_earnings", "net_income"),
            "buybacks, OCI reclasses or stock comp can explain gaps; verify the equity statement"))


def _cross_statement_scale(fs, r):
    rev, ni = fs.val("revenue"), fs.val("net_income")
    if rev is None or ni is None or rev <= 0:
        return
    r.checks_run.append("cross_statement_scale")
    if abs(ni) > 3 * rev:
        r.violations.append(Violation(
            "CROSS_STATEMENT_SCALE", "warning",
            f"|Net income| ({abs(ni):,.2f}) is more than 3x revenue ({rev:,.2f}).",
            None, ("net_income", "revenue"), _pages(fs, "net_income", "revenue"),
            scale_hint(ni, rev) or "statements may use different unit scales"))


def _reconciliations(fs, r, rel, abs_tol):
    for rec in fs.reconciliations:
        r.checks_run.append(f"reconciliation_footing:{rec.metric}")
        total = rec.gaap_value.value + sum(a.amount.value for a in rec.adjustments)
        rep = rec.reported_non_gaap.value
        resid = total - rep
        if abs(resid) > _tol(total, rep, rel, abs_tol):
            r.violations.append(Violation(
                "RECONCILIATION_FOOTING", "error",
                f"{rec.metric}: GAAP ({rec.gaap_value.value:,.2f}) + adjustments = {total:,.2f}, reported non-GAAP = {rep:,.2f}.",
                resid, (rec.metric,), (rec.reported_non_gaap.prov.page,),
                "an adjustment line is missing, mis-signed, or the wrong column was read"))


def _segments(fs, r, rel, abs_tol):
    for t in fs.segment_tables:
        r.checks_run.append(f"segment_sum:{t.metric}")
        total = sum(s.value for s in t.segments.values()) + (t.eliminations.value if t.eliminations else 0.0)
        resid = total - t.consolidated.value
        if abs(resid) > _tol(total, t.consolidated.value, rel, abs_tol):
            r.violations.append(Violation(
                "SEGMENT_SUM", "error",
                f"{t.metric}: segments + eliminations = {total:,.2f}, consolidated = {t.consolidated.value:,.2f}.",
                resid, (t.metric,), (t.consolidated.prov.page,),
                "check for a missing 'other/corporate' row or intersegment eliminations"))
