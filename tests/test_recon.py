"""Unit tests for recon.py: Non-GAAP reconciliation extraction, footing checks, and bloat auditing."""
from __future__ import annotations

from finsight.backends import StubBackend
from finsight.recon import audit_reconciliations, extract_recon_tables
from finsight.schemas import (
    Adjustment,
    FilingMeta,
    Financials,
    NonGaapReconciliation,
    Provenance,
    Sourced,
)
from finsight.solver import verify


def _make_reconciliation(
    gaap: float = 100.0,
    adjustments: list[tuple[str, float]] | None = None,
    reported: float = 150.0,
    page: int = 15,
    metric: str = "Adjusted EBITDA",
) -> NonGaapReconciliation:
    if adjustments is None:
        adjustments = [("Stock-based compensation", 30.0), ("Restructuring", 20.0)]

    return NonGaapReconciliation(
        metric=metric,
        gaap_value=Sourced(
            value=gaap,
            prov=Provenance(page=page, modality="text_table", verbatim=f"Net Income {gaap:,.0f}"),
        ),
        adjustments=[
            Adjustment(
                label=lbl,
                amount=Sourced(
                    value=val,
                    prov=Provenance(page=page, modality="text_table", verbatim=f"{lbl} {val:,.0f}"),
                ),
            )
            for lbl, val in adjustments
        ],
        reported_non_gaap=Sourced(
            value=reported,
            prov=Provenance(page=page, modality="text_table", verbatim=f"{metric} {reported:,.0f}"),
        ),
    )


def test_extract_recon_tables_with_stub():
    rec_json = {
        "reconciliations": [
            {
                "metric": "Adjusted EBITDA",
                "gaap_value": {
                    "value": 100.0,
                    "prov": {"page": 12, "modality": "text_table", "verbatim": "GAAP Net Income 100"},
                },
                "adjustments": [
                    {
                        "label": "Stock comp",
                        "amount": {
                            "value": 25.0,
                            "prov": {"page": 12, "modality": "text_table", "verbatim": "Stock comp 25"},
                        },
                    }
                ],
                "reported_non_gaap": {
                    "value": 125.0,
                    "prov": {"page": 12, "modality": "text_table", "verbatim": "Adjusted EBITDA 125"},
                },
            }
        ]
    }
    stub = StubBackend(responses=[rec_json])
    tables = extract_recon_tables([b"dummy_png"], backend=stub)

    assert len(tables) == 1
    assert tables[0].metric == "Adjusted EBITDA"
    assert tables[0].gaap_value.value == 100.0
    assert tables[0].reported_non_gaap.value == 125.0
    assert len(tables[0].adjustments) == 1


def test_audit_reconciliations_footing_pass_and_bloat():
    # GAAP 100 + (30 + 20) = 150 reported -> footing passes
    # Bloat: (150 - 100)/100 = 50% > 25% flag
    rec = _make_reconciliation(gaap=100.0, reported=150.0, page=14)
    audit_res = audit_reconciliations([rec])

    assert audit_res["all_footing_passed"] is True
    assert len(audit_res["tables"]) == 1
    t = audit_res["tables"][0]
    assert t["footing_passed"] is True
    assert t["residual"] == 0.0
    assert t["bloat"] == 0.5
    assert t["bloat_flag"] is True

    # Bloat flag cited with page number
    assert any("p.14" in f and "NON_GAAP_BLOAT" in f for f in audit_res["flags"])


def test_footing_violation_reported_with_page():
    # GAAP 100 + 20 = 120, but reported is 160 (residual -40)
    rec = _make_reconciliation(
        gaap=100.0,
        adjustments=[("Depreciation add-back", 20.0)],
        reported=160.0,
        page=28,
        metric="Free Cash Flow",
    )
    audit_res = audit_reconciliations([rec])

    assert audit_res["all_footing_passed"] is False
    t = audit_res["tables"][0]
    assert t["footing_passed"] is False
    assert t["residual"] == -40.0
    assert t["page"] == 28

    # Footing violation must be reported with the exact page number
    fail_flags = [f for f in audit_res["flags"] if "RECONCILIATION_FOOTING_FAIL" in f]
    assert len(fail_flags) == 1
    assert "p.28" in fail_flags[0]
    assert "Free Cash Flow" in fail_flags[0]


def test_solver_verify_catches_reconciliation_footing():
    # Verify integration with solver.py
    rec = _make_reconciliation(
        gaap=100.0,
        adjustments=[("SBC", 10.0)],
        reported=200.0,  # 100 + 10 != 200
        page=42,
        metric="Adjusted Net Income",
    )
    fs = Financials(
        meta=FilingMeta(
            company="TestCo",
            currency="USD",
            unit_scale="millions",
            period_end="2024-12-31",
        ),
        reconciliations=[rec],
    )
    report = verify(fs)

    assert not report.passed
    viol = [v for v in report.violations if v.code == "RECONCILIATION_FOOTING"]
    assert len(viol) == 1
    assert 42 in viol[0].pages
    assert viol[0].residual == -90.0
