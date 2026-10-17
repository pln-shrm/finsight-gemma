import math

from finsight.lie_factor import audit_bar_chart, baseline_truncated, lie_factor, lie_factor_from_axis


def test_faithful_chart():
    r = lie_factor(100, 120, 100, 120)
    assert r.verdict == "faithful" and math.isclose(r.lie_factor, 1.0)


def test_truncated_axis_lie_factor_is_analytic():
    r = lie_factor_from_axis(100, 105, axis_min=90)  # heights 10 -> 15: +50% shown vs +5% real
    assert math.isclose(r.lie_factor, 10.0) and r.severity == "alert"


def test_bar_at_axis_min_is_infinite_distortion():
    r = lie_factor_from_axis(100, 105, axis_min=100)
    assert r.verdict in ("distorted", "undefined")


def test_audit_flags_truncation_and_zero_baseline_passes():
    bad = audit_bar_chart(["FY23", "FY24"], [100, 105], axis_min=90)
    ok = audit_bar_chart(["FY23", "FY24"], [100, 105], axis_min=0)
    assert bad["flag"] and bad["baseline_truncated"]
    assert not ok["flag"] and not ok["baseline_truncated"]


def test_pixel_heights_override_axis_model():
    r = audit_bar_chart(["a", "b"], [100, 110], pixel_heights=[100, 110])
    assert not r["flag"] and r["pairs"][0]["basis"] == "pixels"


def test_baseline_truncated_helper():
    assert baseline_truncated(50, [60, 70]) and not baseline_truncated(0, [60, 70]) and not baseline_truncated(None, [1])
