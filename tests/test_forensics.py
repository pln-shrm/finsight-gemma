import math

from finsight.forensics import (
    altman_z_double_prime,
    beneish_m,
    cash_conversion,
    dupont5,
    low_conversion_streak,
    non_gaap_bloat,
    piotroski_f,
    run_all,
)


def full(make_fs, S_, **over):
    base = dict(
        revenue=S_(1000, 900), cogs=S_(600, 560), sga=S_(150, 140), depreciation_amortization=S_(50, 45),
        ebit=S_(200, 160), interest_expense=S_(20, 20), pretax_income=S_(180, 140), net_income=S_(135, 105),
        receivables=S_(120, 100), current_assets=S_(500, 450), ppe_net=S_(600, 550), total_assets=S_(2000, 1800),
        current_liabilities=S_(300, 290), long_term_debt=S_(400, 420), total_liabilities=S_(900, 880),
        total_equity=S_(1100, 920), retained_earnings=S_(700, 600), cfo=S_(180, 130), shares_outstanding=S_(100, 100),
    )
    base.update(over)
    return make_fs(**base)


def test_dupont_reconstructs_roe(make_fs, S_):
    d = dupont5(full(make_fs, S_))
    assert d["available"] and d["reconciles"] and math.isclose(d["roe_reconstructed"], 135 / 1100)


def test_dupont_abstains_when_missing(make_fs):
    assert not dupont5(make_fs(revenue=1000))["available"]


def test_altman_z_double_prime_arithmetic(make_fs, S_):
    z = altman_z_double_prime(full(make_fs, S_))
    exp = 6.56 * (200 / 2000) + 3.26 * (700 / 2000) + 6.72 * (200 / 2000) + 1.05 * (1100 / 900)
    assert math.isclose(z["z"], exp) and z["zone"] == "safe"


def test_beneish_neutral_case_matches_hand_calc(make_fs, S_):
    flat = dict(revenue=S_(1000, 1000), cogs=S_(600, 600), sga=S_(150, 150), depreciation_amortization=S_(50, 50),
                receivables=S_(100, 100), current_assets=S_(500, 500), ppe_net=S_(600, 600), total_assets=S_(2000, 2000),
                current_liabilities=S_(300, 300), long_term_debt=S_(400, 400), net_income=S_(100), cfo=S_(100))
    m = beneish_m(make_fs(**flat))
    assert m["available"] and math.isclose(m["m_score"], -2.48, abs_tol=1e-9) and not m["flag"]


def test_beneish_abstains_without_priors(make_fs, S_):
    assert not beneish_m(make_fs(revenue=S_(1000), net_income=S_(1), cfo=S_(1)))["available"]


def test_piotroski_all_pass(make_fs, S_):
    p = piotroski_f(full(make_fs, S_, long_term_debt=S_(300, 420)))
    assert p["evaluable"] == 9 and p["score"] >= 8


def test_cash_conversion_and_bloat(make_fs, S_):
    assert math.isclose(cash_conversion(full(make_fs, S_)), 180 / 135)
    assert math.isclose(non_gaap_bloat(100, 140), 0.4)
    assert non_gaap_bloat(0, 10) is None


def test_low_conversion_streak():
    assert low_conversion_streak([80, 70, 60, 120], [100, 100, 100, 100])
    assert not low_conversion_streak([80, 120, 60, 70], [100, 100, 100, 100])


def test_run_all_flags_low_conversion(make_fs, S_):
    out = run_all(full(make_fs, S_, cfo=S_(50, 130)))
    assert any("LOW_CASH_CONVERSION" in f for f in out["flags"])
