import math

import pytest

from finsight.dcf import DCFInputs, monte_carlo, sensitivity_matrix, value_per_share


def base(**kw):
    d = dict(revenue0=1000, growth_start=0.10, growth_terminal=0.03, margin_start=0.15, margin_target=0.20,
             tax_rate=0.25, sales_to_capital=2.0, wacc=0.10, net_debt=100, shares=50)
    d.update(kw)
    return DCFInputs(**d)


def test_closed_form_perpetuity_when_no_growth():
    i = base(growth_start=0.0, growth_terminal=0.0, margin_start=0.2, margin_target=0.2)
    nopat = 1000 * 0.2 * 0.75
    assert math.isclose(value_per_share(i), (nopat / 0.10 - 100) / 50, rel_tol=1e-9)


def test_higher_wacc_lowers_value():
    assert value_per_share(base(wacc=0.12)) < value_per_share(base(wacc=0.09))


def test_wacc_must_exceed_g():
    with pytest.raises(ValueError):
        value_per_share(base(wacc=0.03, growth_terminal=0.03))


def test_sensitivity_monotonic_and_masks_invalid():
    m = sensitivity_matrix(base(), [0.08, 0.10, 0.12], [0.02, 0.03])
    col = [row[0] for row in m["value_per_share"]]
    assert col[0] > col[1] > col[2]
    assert sensitivity_matrix(base(), [0.03], [0.03])["value_per_share"][0][0] is None


def test_monte_carlo_is_ordered_and_reproducible():
    a, b = monte_carlo(base(), n=2000, seed=1, price=40), monte_carlo(base(), n=2000, seed=1, price=40)
    assert a == b and a["p10"] < a["p50"] < a["p90"] and 0 <= a["prob_value_above_price"] <= 1
