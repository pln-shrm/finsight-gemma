"""Typed contracts. Model-extracted data enters the system ONLY through these schemas.

Conventions
- Values are stored AS REPORTED, in `meta.unit_scale` units. Use `to_base_units` for cross-document work.
- `capex` and `dividends_paid` are POSITIVE magnitudes. `cfo`/`cfi`/`cff`/`fx_effect` keep reported signs.
- bbox = [x0, y0, x1, y1], normalized 0..1, origin top-left. Adapters convert model-native formats.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

UnitScale = Literal["units", "thousands", "lakhs", "millions", "crores", "billions"]
SCALE_FACTORS: dict[str, float] = {
    "units": 1.0, "thousands": 1e3, "lakhs": 1e5,
    "millions": 1e6, "crores": 1e7, "billions": 1e9,
}


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=1, description="1-indexed PDF page")
    modality: Literal["text_table", "visual_table", "visual_chart", "footnote_prose"]
    verbatim: str = Field(min_length=1, description="Exact text visible in the source")
    bbox: Optional[list[float]] = None
    bbox_source: Literal["text_layer", "model", "none"] = "none"

    @field_validator("bbox")
    @classmethod
    def _check_bbox(cls, v):
        if v is None:
            return v
        if len(v) != 4 or any(not (0.0 <= x <= 1.0) for x in v):
            raise ValueError("bbox must be 4 floats in [0,1]")
        if not (v[0] < v[2] and v[1] < v[3]):
            raise ValueError("bbox must satisfy x0<x1 and y0<y1")
        return v


class Sourced(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float
    prior: Optional[float] = None
    prov: Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class FilingMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str
    ticker: Optional[str] = None
    currency: str = Field(description="ISO code, e.g. USD, INR")
    unit_scale: UnitScale
    standard: Literal["US_GAAP", "IFRS", "IND_AS", "OTHER"] = "OTHER"
    basis: Literal["consolidated", "standalone"] = "consolidated"
    period_end: str = Field(description="YYYY-MM-DD")
    period_type: Literal["annual", "quarterly"] = "annual"
    filing_date: Optional[str] = None


class Adjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    amount: Sourced  # signed: add-backs positive, deductions negative


class NonGaapReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    gaap_value: Sourced
    adjustments: list[Adjustment]
    reported_non_gaap: Sourced


class SegmentTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    segments: dict[str, Sourced]
    eliminations: Optional[Sourced] = None  # signed as reported (usually negative)
    consolidated: Sourced


ITEM_NAMES = (
    "revenue", "cogs", "sga", "depreciation_amortization", "ebit", "interest_expense",
    "pretax_income", "tax_expense", "net_income", "sbc",
    "cash", "receivables", "current_assets", "ppe_net", "total_assets",
    "current_liabilities", "long_term_debt", "total_liabilities",
    "total_equity", "total_liabilities_and_equity", "retained_earnings",
    "shares_outstanding",
    "cfo", "cfi", "cff", "fx_effect", "capex", "dividends_paid",
)


class Financials(BaseModel):
    """One filing period. Any field the model cannot read must be null (abstain), never guessed."""
    model_config = ConfigDict(extra="forbid")
    meta: FilingMeta
    # income statement
    revenue: Optional[Sourced] = None
    cogs: Optional[Sourced] = None
    sga: Optional[Sourced] = None
    depreciation_amortization: Optional[Sourced] = None
    ebit: Optional[Sourced] = None
    interest_expense: Optional[Sourced] = None
    pretax_income: Optional[Sourced] = None
    tax_expense: Optional[Sourced] = None
    net_income: Optional[Sourced] = None
    sbc: Optional[Sourced] = None
    # balance sheet (total_equity INCLUDES non-controlling interest)
    cash: Optional[Sourced] = None
    receivables: Optional[Sourced] = None
    current_assets: Optional[Sourced] = None
    ppe_net: Optional[Sourced] = None
    total_assets: Optional[Sourced] = None
    current_liabilities: Optional[Sourced] = None
    long_term_debt: Optional[Sourced] = None
    total_liabilities: Optional[Sourced] = None  # many 10-Ks do not print this line
    total_equity: Optional[Sourced] = None
    total_liabilities_and_equity: Optional[Sourced] = None
    retained_earnings: Optional[Sourced] = None
    shares_outstanding: Optional[Sourced] = None
    # cash flow
    cfo: Optional[Sourced] = None
    cfi: Optional[Sourced] = None
    cff: Optional[Sourced] = None
    fx_effect: Optional[Sourced] = None
    capex: Optional[Sourced] = None
    dividends_paid: Optional[Sourced] = None
    # structured tables
    reconciliations: list[NonGaapReconciliation] = Field(default_factory=list)
    segment_tables: list[SegmentTable] = Field(default_factory=list)

    def item(self, name: str) -> Optional[Sourced]:
        return getattr(self, name, None)

    def val(self, name: str) -> Optional[float]:
        it = self.item(name)
        return None if it is None else it.value

    def prior(self, name: str) -> Optional[float]:
        it = self.item(name)
        return None if it is None else it.prior

    def page(self, name: str) -> Optional[int]:
        it = self.item(name)
        return None if it is None else it.prov.page

    def to_base_units(self, name: str) -> Optional[float]:
        v = self.val(name)
        return None if v is None else v * SCALE_FACTORS[self.meta.unit_scale]


class ChartPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    printed_value: Optional[float] = None   # number printed on the chart
    pixel_height: Optional[float] = None    # measured by CV, never by the model


class ChartExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chart_type: Literal["bar", "line", "waterfall", "stacked_bar", "pie", "other"]
    title: Optional[str] = None
    axis_min: Optional[float] = None
    axis_max: Optional[float] = None
    axis_scale: Literal["linear", "log"] = "linear"
    has_secondary_axis: bool = False
    points: list[ChartPoint]
    prov: Provenance
