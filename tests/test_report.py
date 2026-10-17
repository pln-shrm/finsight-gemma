"""Unit tests for report.py: HTML audit report rendering, evidence crops, and offline self-containment."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from finsight.report import render_report
from finsight.schemas import FilingMeta, Financials, Provenance, Sourced


def _create_mock_page(path: Path) -> None:
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img.save(path)


def _sample_financials(ws: Path) -> Financials:
    prov = Provenance(page=1, modality="text_table", verbatim="Total Assets 1000", bbox=[0.1, 0.1, 0.5, 0.2], bbox_source="text_layer")
    meta = FilingMeta(
        company="Acme Corporation",
        currency="USD",
        unit_scale="millions",
        period_end="2024-12-31",
        basis="consolidated",
        standard="US_GAAP",
    )
    return Financials(
        meta=meta,
        total_assets=Sourced(value=1000.0, prov=prov),
        total_liabilities=Sourced(value=600.0, prov=prov),
        total_equity=Sourced(value=400.0, prov=prov),
        revenue=Sourced(value=1200.0, prov=prov),
        ebit=Sourced(value=240.0, prov=prov),
        net_income=Sourced(value=160.0, prov=prov),
        cfo=Sourced(value=180.0, prov=prov),
        capex=Sourced(value=50.0, prov=prov),
        cash=Sourced(value=100.0, prov=prov),
        current_assets=Sourced(value=400.0, prov=prov),
        current_liabilities=Sourced(value=250.0, prov=prov),
    )


def test_render_report_end_to_end_success(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    pages_dir = ws / "pages"
    pages_dir.mkdir()
    _create_mock_page(pages_dir / "page_001.png")

    fin = _sample_financials(ws)
    (ws / "financials.json").write_text(fin.model_dump_json(indent=2), encoding="utf-8")

    verification = {
        "passed": True,
        "errors": [],
        "residuals": {"balance_sheet_identity": 0.0},
    }
    (ws / "verification.json").write_text(json.dumps(verification), encoding="utf-8")

    forensics = {
        "dupont": {
            "roe": 0.40,
            "net_margin": 0.133,
            "asset_turnover": 1.20,
            "equity_multiplier": 2.50,
        },
        "altman_z_prime": {"score": 3.42, "zone": "safe"},
        "piotroski_f": {"score": 7},
        "flags": ["Chart on p.14 has truncated zero baseline (Lie Factor = 1.62)"],
    }
    (ws / "forensics.json").write_text(json.dumps(forensics), encoding="utf-8")

    dcf = {
        "intrinsic_value_per_share": 45.20,
        "mc_distribution": [40.0, 42.0, 45.0, 48.0, 50.0],
        "p10": 41.0,
        "p90": 49.0,
    }
    (ws / "dcf.json").write_text(json.dumps(dcf), encoding="utf-8")

    out_file = ws / "report.html"
    res = render_report(ws, out=out_file)

    assert res == out_file
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "Acme Corporation" in content
    assert "USD (millions)" in content
    assert "Accounting Verified" in content
    assert "Chart on p.14 has truncated zero baseline" in content
    assert "Altman Z''" in content
    assert "not investment advice" in content.lower()
    # Check that base64 image data is rendered
    assert "data:image/png;base64," in content


def test_render_report_failed_verification(tmp_path: Path):
    ws = tmp_path / "ws_fail"
    ws.mkdir()
    fin = _sample_financials(ws)
    (ws / "financials.json").write_text(fin.model_dump_json(indent=2), encoding="utf-8")

    verification = {
        "passed": False,
        "errors": [
            {
                "code": "BALANCE_SHEET_IDENTITY",
                "message": "Assets != Liabilities + Equity (1000 != 600 + 350)",
                "residual": 50.0,
            }
        ],
        "residuals": {"balance_sheet_identity": 50.0},
    }
    (ws / "verification.json").write_text(json.dumps(verification), encoding="utf-8")

    out_file = ws / "audit.html"
    render_report(ws, out=out_file)

    content = out_file.read_text(encoding="utf-8")
    assert "Identity Residuals Detected" in content
    assert "BALANCE_SHEET_IDENTITY" in content


def test_render_report_missing_financials_raises(tmp_path: Path):
    ws = tmp_path / "empty_ws"
    ws.mkdir()
    with pytest.raises(FileNotFoundError, match="Missing .*financials.json"):
        render_report(ws)


def test_render_report_minimal_optional_artifacts(tmp_path: Path):
    ws = tmp_path / "minimal_ws"
    ws.mkdir()
    fin = _sample_financials(ws)
    (ws / "financials.json").write_text(fin.model_dump_json(indent=2), encoding="utf-8")

    out_file = ws / "report.html"
    render_report(ws, out=out_file)
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Acme Corporation" in content
    assert "not investment advice" in content.lower()
