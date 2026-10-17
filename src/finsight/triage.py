"""Deterministic page triage: keyword/regex scoring with no model calls.

Each page gets a score per class; the winner (above a minimum threshold) is assigned.
Priority when tied: NON_GAAP_RECON > FINANCIAL_STATEMENT > FOOTNOTE > CHART > IGNORE.

Stage 1 (small-model refinement of ambiguous pages) is T3 / stretch — not implemented here.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .ingest import PageInfo

PageClass = Literal[
    "IGNORE", "FINANCIAL_STATEMENT", "FOOTNOTE", "CHART", "NON_GAAP_RECON"
]

# ── Keyword / regex rule tables ───────────────────────────────────────────────
# Each entry: (compiled regex, weight, short label for reasons list)
# Rules are case-insensitive; matched at most ONCE per page (boolean hit).

def _r(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_FS_RULES: list[tuple[re.Pattern[str], float, str]] = [
    # Strong signals (3 pts) — unambiguous financial statement markers
    (_r(r"total\s+assets"),                                         3.0, "TOTAL_ASSETS"),
    (_r(r"total\s+liabilit(?:y|ies)"),                             3.0, "TOTAL_LIABILITIES"),
    (_r(r"stockholders['\u2019]?\s*equity|shareholders['\u2019]?\s*equity"), 3.0, "SH_EQUITY"),
    (_r(r"statement\s+of\s+(?:financial\s+position|operations|cash\s+flows?)"), 3.0, "STMT_HEADER"),
    (_r(r"income\s+statement|balance\s+sheet"),                     3.0, "STMT_NAME"),
    (_r(r"net\s+(?:income|loss|earnings)"),                         3.0, "NET_INCOME"),
    (_r(r"operating\s+(?:income|loss|profit)"),                     3.0, "OPERATING_INCOME"),
    (_r(r"cash\s+(?:and\s+cash\s+equivalents?|flows?\s+from\s+operat)"), 3.0, "CASH_FLOW"),
    (_r(r"earnings\s+per\s+(?:share|unit)|loss\s+per\s+share"),    3.0, "EPS"),
    (_r(r"comprehensive\s+(?:income|loss)"),                        3.0, "COMPREHENSIVE"),
    # Medium signals (2 pts)
    (_r(r"gross\s+(?:profit|margin)"),                              2.0, "GROSS_PROFIT"),
    (_r(r"ebit(?:da)?(?!\w)"),                                      2.0, "EBIT"),
    (_r(r"depreciation(?:\s+and\s+amortization)?"),                 2.0, "D_A"),
    (_r(r"accounts\s+(?:receivable|payable)"),                      2.0, "AR_AP"),
    (_r(r"retained\s+earnings|accumulated\s+deficit"),              2.0, "RETAINED"),
    (_r(r"long.term\s+debt"),                                       2.0, "LT_DEBT"),
    (_r(r"in\s+(?:millions?|thousands?|billions?|crores?|lakhs?)"),  2.0, "UNIT_SCALE"),
    (_r(r"(?:\$|₹|€|£)\s*\d[\d,]*"),                              2.0, "MONETARY"),
    (_r(r"(?:total\s+)?revenues?(?:\s+from\s+contracts?)?"),        2.0, "REVENUE"),
    (_r(r"interest\s+(?:income|expense)"),                          2.0, "INTEREST"),
    (_r(r"diluted|basic\s+(?:earnings|loss)"),                      2.0, "DILUTED"),
    (_r(r"\bparticulars\b"),                                        2.0, "PARTICULARS"),  # Indian
    (_r(r"current\s+(?:assets|liabilities)"),                       2.0, "CURRENT"),
    (_r(r"property\s+(?:plant|and\s+equipment)|ppe\b"),             2.0, "PPE"),
    (_r(r"income\s+tax(?:es)?"),                                    2.0, "TAX"),
    # Weak signals (1 pt)
    (_r(r"\bassets\b"),                                             1.0, "ASSETS"),
    (_r(r"\bliabilit(?:y|ies)\b"),                                  1.0, "LIABILITIES"),
    (_r(r"\bequity\b"),                                             1.0, "EQUITY"),
    (_r(r"\b(?:revenue|income|earnings)\b"),                        1.0, "INCOME_WEAK"),
]

_RECON_RULES: list[tuple[re.Pattern[str], float, str]] = [
    # Strong (3 pts)
    (_r(r"non.gaap|non\s+gaap"),                                    3.0, "NON_GAAP"),
    (_r(r"adjusted\s+(?:ebitda|operating|net\s+income|revenue|gross)"), 3.0, "ADJUSTED"),
    (_r(r"reconcili(?:ation|es?|zation)"),                          3.0, "RECONCILIATION"),
    # Medium (2 pts)
    (_r(r"stock.based\s+compensation"),                             2.0, "SBC"),
    (_r(r"restructuring\s+(?:charges?|costs?)"),                    2.0, "RESTRUCTURING"),
    (_r(r"pro\s+forma"),                                            2.0, "PRO_FORMA"),
    (_r(r"acquisition.related"),                                    2.0, "ACQUISITION"),
    (_r(r"add.back|add\s+back"),                                    2.0, "ADDBACK"),
    (_r(r"management\s+(?:uses|believes|defines)"),                 2.0, "MGMT_USE"),
    (_r(r"impairment\s+(?:charge|loss|of\s+goodwill)"),             2.0, "IMPAIRMENT"),
]

_FOOTNOTE_RULES: list[tuple[re.Pattern[str], float, str]] = [
    # Strong (3 pts)
    (_r(r"notes?\s+to\s+(?:the\s+)?(?:consolidated\s+)?financial\s+statements?"), 3.0, "NOTES_HEADER"),
    (_r(r"significant\s+accounting\s+polic(?:y|ies)"),              3.0, "SIG_ACCT"),
    (_r(r"basis\s+of\s+(?:presentation|preparation)"),              3.0, "BASIS"),
    # Medium (2 pts)
    (_r(r"\bnote\s+\d+\b"),                                         2.0, "NOTE_N"),
    (_r(r"see\s+(?:accompanying\s+)?note|refer\s+to\s+note"),       2.0, "SEE_NOTE"),
    (_r(r"accounting\s+polic(?:y|ies)"),                            2.0, "ACCT_POLICY"),
    (_r(r"fair\s+value\s+(?:measurement|hierarch)"),                 2.0, "FAIR_VALUE"),
    (_r(r"critical\s+accounting\s+(?:estimate|judgment)"),          2.0, "CRITICAL_ACCT"),
]

_CHART_RULES: list[tuple[re.Pattern[str], float, str]] = [
    # Strong (3 pts)
    (_r(r"figure\s+\d+|exhibit\s+[a-z]?\d+"),                      3.0, "FIGURE_N"),
    # Medium (2 pts)
    (_r(r"\b(?:cagr|year.over.year|yoy)\b"),                       2.0, "GROWTH_METRIC"),
    (_r(r"(?:bar|pie|line|waterfall)\s+(?:chart|graph)"),           2.0, "CHART_TYPE"),
    (_r(r"(?:x|y).axis"),                                           2.0, "AXIS"),
]

# Minimum score to assign a class (below this → IGNORE)
_MIN_SCORE: dict[str, float] = {
    "FINANCIAL_STATEMENT": 4.0,
    "NON_GAAP_RECON":      3.0,
    "FOOTNOTE":            3.0,
    "CHART":               2.0,
}

# Pages with fewer words than this are candidates for CHART even with low text scores
_CHART_SPARSE_WORD_THRESHOLD = 25


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class PageScore:
    """Triage result for a single page."""

    n: int
    page_class: PageClass
    score: float          # winning class score
    reasons: list[str]    # labels of rules that fired for the winning class
    detected_unit: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


_UNIT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:in\s+)?(?:₹|\$|eur|usd|inr)?\s*crores?\b", re.IGNORECASE), "crores"),
    (re.compile(r"\b(?:in\s+)?(?:₹|\$|eur|usd|inr)?\s*lakhs?\b", re.IGNORECASE), "lakhs"),
    (re.compile(r"\b(?:in\s+)?(?:₹|\$|eur|usd|inr)?\s*billions?\b", re.IGNORECASE), "billions"),
    (re.compile(r"\b(?:in\s+)?(?:₹|\$|eur|usd|inr)?\s*millions?\b", re.IGNORECASE), "millions"),
    (re.compile(r"\b(?:in\s+)?(?:₹|\$|eur|usd|inr)?\s*thousands?\b", re.IGNORECASE), "thousands"),
]


def detect_unit(text: str) -> str | None:
    """Detect unit scale string from page text, e.g. 'millions', 'crores'."""
    for pattern, unit in _UNIT_PATTERNS:
        if pattern.search(text):
            return unit
    return None


# ── Core scoring ──────────────────────────────────────────────────────────────


def _score_rules(
    text: str,
    rules: list[tuple[re.Pattern[str], float, str]],
) -> tuple[float, list[str]]:
    """Return (total_score, [fired_labels]) for a set of rules against *text*.

    Each rule fires at most once per page regardless of how many times it matches.
    """
    total = 0.0
    fired: list[str] = []
    for pattern, weight, label in rules:
        if pattern.search(text):
            total += weight
            fired.append(label)
    return total, fired


def _classify(scores: dict[str, tuple[float, list[str]]], word_count: int) -> PageScore:
    """Pick the winning class from per-class (score, reasons) pairs."""
    fs_score, fs_reasons     = scores["FINANCIAL_STATEMENT"]
    recon_score, recon_reasons = scores["NON_GAAP_RECON"]
    fn_score, fn_reasons     = scores["FOOTNOTE"]
    ch_score, ch_reasons     = scores["CHART"]

    # Sparse page → chart candidate if it has some chart indicator
    if word_count < _CHART_SPARSE_WORD_THRESHOLD and ch_score > 0:
        ch_score = max(ch_score, _MIN_SCORE["CHART"])
        if "SPARSE_PAGE" not in ch_reasons:
            ch_reasons = ch_reasons + [f"SPARSE_PAGE({word_count}_words)"]

    # Priority: NON_GAAP_RECON > FINANCIAL_STATEMENT > FOOTNOTE > CHART
    candidates: list[tuple[float, str, list[str]]] = [
        (recon_score, "NON_GAAP_RECON",      recon_reasons),
        (fs_score,    "FINANCIAL_STATEMENT", fs_reasons),
        (fn_score,    "FOOTNOTE",            fn_reasons),
        (ch_score,    "CHART",               ch_reasons),
    ]

    for score, cls, reasons in candidates:
        if score >= _MIN_SCORE[cls]:
            return PageScore(n=0, page_class=cls, score=score, reasons=reasons)

    return PageScore(n=0, page_class="IGNORE", score=0.0, reasons=[])


def score_pages(pages: list[PageInfo]) -> list[PageScore]:
    """Score and classify every page in *pages* using keyword/regex rules only.

    Args:
        pages: Output of :func:`finsight.ingest.ingest`.

    Returns:
        One :class:`PageScore` per page, in the same order as *pages*.
    """
    results: list[PageScore] = []
    for pi in pages:
        text = pi.text
        word_count = len(pi.words)

        per_class = {
            "FINANCIAL_STATEMENT": _score_rules(text, _FS_RULES),
            "NON_GAAP_RECON":      _score_rules(text, _RECON_RULES),
            "FOOTNOTE":            _score_rules(text, _FOOTNOTE_RULES),
            "CHART":               _score_rules(text, _CHART_RULES),
        }

        ps = _classify(per_class, word_count)
        ps.n = pi.n
        ps.detected_unit = detect_unit(text)
        results.append(ps)

    return results


# ── Persistence ───────────────────────────────────────────────────────────────


def save_triage(scores: list[PageScore], ws: Path) -> Path:
    """Write *scores* to ``<ws>/triage.json``.  Returns the written path."""
    ws = Path(ws)
    ws.mkdir(parents=True, exist_ok=True)
    out = ws / "triage.json"
    out.write_text(
        json.dumps([s.as_dict() for s in scores], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out


def load_triage(ws: Path) -> list[PageScore]:
    """Read ``<ws>/triage.json`` back into :class:`PageScore` objects."""
    data = json.loads((Path(ws) / "triage.json").read_text(encoding="utf-8"))
    return [
        PageScore(
            n=d["n"],
            page_class=d["page_class"],
            score=d["score"],
            reasons=d["reasons"],
            detected_unit=d.get("detected_unit"),
        )
        for d in data
    ]


def selected_pages(
    scores: list[PageScore],
    include: tuple[PageClass, ...] = ("FINANCIAL_STATEMENT", "NON_GAAP_RECON"),
) -> list[PageScore]:
    """Return only the pages whose class is in *include*, sorted by page number."""
    return sorted(
        [s for s in scores if s.page_class in include],
        key=lambda s: s.n,
    )
