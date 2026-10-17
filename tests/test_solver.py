from finsight.schemas import Adjustment, NonGaapReconciliation, SegmentTable
from finsight.solver import scale_hint, verify


def test_balanced_passes(make_fs):
    fs = make_fs(total_assets=1000, total_liabilities=600, total_equity=400, current_assets=300, cash=100)
    r = verify(fs)
    assert r.passed and "balance_sheet_identity" in r.checks_run


def test_identity_violation_has_residual_and_page(make_fs, S_):
    fs = make_fs(total_assets=S_(1000, page=42), total_liabilities=600, total_equity=385)
    r = verify(fs)
    assert not r.passed
    v = r.errors[0]
    assert v.code == "BALANCE_SHEET_IDENTITY" and round(v.residual) == 15 and 42 in v.pages
    assert "Residual = +15.00" in r.retry_prompt()


def test_uses_total_liabilities_and_equity_when_no_total_liabilities(make_fs):
    fs = make_fs(total_assets=1000, total_liabilities_and_equity=1000)
    r = verify(fs)
    assert r.passed and "balance_sheet_identity" in r.checks_run


def test_missing_inputs_are_skipped_not_failed(make_fs):
    r = verify(make_fs(total_assets=1000))
    assert r.passed and "balance_sheet_identity" in r.checks_skipped


def test_lakh_crore_scale_hint(make_fs):
    fs = make_fs(total_assets=100_000, total_liabilities=600, total_equity=400)
    v = verify(fs).errors[0]
    assert "100x" in v.hint or "lakhs vs crores" in v.hint
    assert scale_hint(1000, 1) is not None


def test_component_exceeds_total(make_fs):
    r = verify(make_fs(total_assets=100, current_assets=500))
    assert any(v.code == "COMPONENT_EXCEEDS_TOTAL" for v in r.errors)


def test_cash_bridge_warning_only(make_fs, S_):
    fs = make_fs(cash=S_(150, prior=100), cfo=80, cfi=-20, cff=-10)  # implied 150 -> ok
    assert not verify(fs).violations
    fs2 = make_fs(cash=S_(150, prior=100), cfo=80, cfi=-20, cff=-50)  # implied 110 vs 150
    r = verify(fs2)
    assert r.passed and any(v.code == "CASH_BRIDGE" and v.severity == "warning" for v in r.violations)


def test_reconciliation_footing(make_fs, S_):
    good = NonGaapReconciliation(metric="Adj. EBITDA", gaap_value=S_(100),
                                 adjustments=[Adjustment(label="SBC", amount=S_(30)), Adjustment(label="Restructuring", amount=S_(10))],
                                 reported_non_gaap=S_(140))
    bad = good.model_copy(update={"reported_non_gaap": S_(155)})
    assert verify(make_fs(reconciliations=[good])).passed
    r = verify(make_fs(reconciliations=[bad]))
    assert r.errors[0].code == "RECONCILIATION_FOOTING" and round(r.errors[0].residual) == -15


def test_segment_sum_with_eliminations(make_fs, S_):
    t = SegmentTable(metric="Revenue", segments={"A": S_(600), "B": S_(450)}, eliminations=S_(-50), consolidated=S_(1000))
    assert verify(make_fs(segment_tables=[t])).passed
    t_bad = t.model_copy(update={"eliminations": None})
    assert not verify(make_fs(segment_tables=[t_bad])).passed
