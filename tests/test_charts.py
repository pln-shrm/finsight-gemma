"""Unit tests for charts.py: CV bar measurement, Lie Factor auditing, and unscored handling."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from finsight.backends import StubBackend
from finsight.charts import audit, extract_chart, measure_bars_cv
from finsight.schemas import ChartExtraction, ChartPoint, Provenance


def _make_bar_chart_png(values: list[float], labels: list[str]) -> bytes:
    """Generate a clean synthetic bar chart as PNG bytes."""
    fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
    ax.bar(labels, values, color="#1f77b4", width=0.5)
    ax.set_ylim(bottom=0)
    # Remove margins/spines for a clean plot
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def test_measure_bars_cv_detects_synthetic_bars():
    png_bytes = _make_bar_chart_png([20.0, 50.0, 80.0], ["A", "B", "C"])
    measured = measure_bars_cv(png_bytes, n_bars=3)

    assert measured is not None
    assert len(measured) == 3
    # Heights must be strictly increasing
    assert measured[0] < measured[1] < measured[2]


def test_measure_bars_cv_returns_none_on_count_mismatch():
    png_bytes = _make_bar_chart_png([30.0, 60.0], ["A", "B"])
    # Expect 5 bars when image only has 2
    measured = measure_bars_cv(png_bytes, n_bars=5)
    assert measured is None


def test_audit_flags_truncated_bar_chart():
    chart = ChartExtraction(
        chart_type="bar",
        title="Misleading Q-o-Q Growth",
        axis_min=100.0,
        axis_max=130.0,
        axis_scale="linear",
        has_secondary_axis=False,
        points=[
            ChartPoint(label="Q1", printed_value=110.0),
            ChartPoint(label="Q2", printed_value=120.0),
        ],
        prov=Provenance(page=1, modality="visual_chart", verbatim="Q-o-Q Growth"),
    )

    # Audited using analytic axis model
    res = audit(chart, measured=None)

    assert res["status"] == "SCORED"
    assert res["baseline_truncated"] is True
    assert res["flag"] is True
    assert res["worst"]["verdict"] == "distorted"
    assert "CHART_CV_FAILED" in res["notes"]
    # Lie factor: (20 - 10)/10 / ((120 - 110)/110) = 1.0 / 0.0909 ~= 11.0
    assert res["worst"]["lie_factor"] > 5.0


def test_audit_passes_zero_baseline_faithful_chart():
    chart = ChartExtraction(
        chart_type="bar",
        title="Faithful Revenue Growth",
        axis_min=0.0,
        axis_max=250.0,
        axis_scale="linear",
        has_secondary_axis=False,
        points=[
            ChartPoint(label="2023", printed_value=100.0),
            ChartPoint(label="2024", printed_value=200.0),
        ],
        prov=Provenance(page=1, modality="visual_chart", verbatim="Revenue Growth"),
    )

    res = audit(chart, measured=None)

    assert res["status"] == "SCORED"
    assert res["baseline_truncated"] is False
    assert res["flag"] is False
    assert res["worst"]["verdict"] == "faithful"
    assert res["worst"]["lie_factor"] == 1.0


def test_audit_with_measured_pixel_heights():
    chart = ChartExtraction(
        chart_type="bar",
        title="Measured Bar Chart",
        axis_min=0.0,
        axis_max=100.0,
        points=[
            ChartPoint(label="A", printed_value=50.0),
            ChartPoint(label="B", printed_value=100.0),
        ],
        prov=Provenance(page=1, modality="visual_chart", verbatim="Chart"),
    )

    # Physical pixels double as data doubles
    res = audit(chart, measured=[100.0, 200.0])

    assert res["basis"] == "cv_pixels"
    assert res["flag"] is False
    assert res["worst"]["verdict"] == "faithful"
    assert "CHART_CV_FAILED" not in res["notes"]


def test_audit_unscored_on_secondary_axis():
    chart = ChartExtraction(
        chart_type="bar",
        title="Dual Axis Chart",
        has_secondary_axis=True,
        points=[
            ChartPoint(label="A", printed_value=10.0),
            ChartPoint(label="B", printed_value=20.0),
        ],
        prov=Provenance(page=1, modality="visual_chart", verbatim="Dual Axis"),
    )

    res = audit(chart)
    assert res["status"] == "UNSCORED"
    assert res["reason"] == "secondary_axis_unsupported"
    assert res["flag"] is False


def test_audit_unscored_on_line_chart():
    chart = ChartExtraction(
        chart_type="line",
        title="Stock Price Trend",
        points=[
            ChartPoint(label="Jan", printed_value=150.0),
            ChartPoint(label="Feb", printed_value=160.0),
        ],
        prov=Provenance(page=1, modality="visual_chart", verbatim="Trend"),
    )

    res = audit(chart)
    assert res["status"] == "UNSCORED"
    assert "line" in res["reason"]


def test_extract_chart_with_stub():
    fake_chart_json = {
        "chart_type": "bar",
        "title": "Segment Revenue",
        "axis_min": 0.0,
        "axis_max": 500.0,
        "axis_scale": "linear",
        "has_secondary_axis": False,
        "points": [
            {"label": "Cloud", "printed_value": 350.0},
            {"label": "Hardware", "printed_value": 150.0},
        ],
        "prov": {"page": 2, "modality": "visual_chart", "verbatim": "Segment Revenue"},
    }
    stub = StubBackend(responses=[fake_chart_json])
    extracted = extract_chart(b"dummy_png_bytes", backend=stub)

    assert isinstance(extracted, ChartExtraction)
    assert extracted.chart_type == "bar"
    assert extracted.title == "Segment Revenue"
    assert len(extracted.points) == 2
    assert extracted.points[0].printed_value == 350.0
