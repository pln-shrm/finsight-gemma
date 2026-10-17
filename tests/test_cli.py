"""Unit tests for cli.py: Typer CLI runner, command invocations, and exit codes."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from finsight.cli import app
from finsight.schemas import FilingMeta, Financials, Provenance, Sourced

runner = CliRunner()


def _create_sample_workspace(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    prov = Provenance(page=1, modality="text_table", verbatim="Total Assets 1000", bbox=[0.1, 0.1, 0.5, 0.2], bbox_source="text_layer")
    meta = FilingMeta(
        company="Test Corp",
        currency="USD",
        unit_scale="millions",
        period_end="2024-12-31",
        basis="consolidated",
        standard="US_GAAP",
    )
    fin = Financials(
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
        shares_outstanding=Sourced(value=50.0, prov=prov),
    )
    (ws / "financials.json").write_text(fin.model_dump_json(indent=2), encoding="utf-8")


def test_cli_help():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    for cmd in ["ingest", "extract", "charts", "analyze", "dcf", "report", "run", "bench"]:
        assert cmd in res.stdout


def test_cli_ingest_missing_pdf_exit_2(tmp_path: Path):
    missing_pdf = tmp_path / "nonexistent.pdf"
    res = runner.invoke(app, ["ingest", str(missing_pdf)])
    assert res.exit_code == 2
    assert "not found" in res.stderr.lower() or "not found" in res.stdout.lower()


def test_cli_extract_missing_workspace_exit_2(tmp_path: Path):
    empty_ws = tmp_path / "empty_ws"
    res = runner.invoke(app, ["extract", "-w", str(empty_ws)])
    assert res.exit_code == 2


def test_cli_analyze_missing_financials_exit_2(tmp_path: Path):
    empty_ws = tmp_path / "empty_ws"
    empty_ws.mkdir()
    res = runner.invoke(app, ["analyze", "-w", str(empty_ws)])
    assert res.exit_code == 2


def test_cli_dcf_missing_financials_exit_2(tmp_path: Path):
    empty_ws = tmp_path / "empty_ws"
    empty_ws.mkdir()
    res = runner.invoke(app, ["dcf", "-w", str(empty_ws)])
    assert res.exit_code == 2


def test_cli_report_missing_financials_exit_2(tmp_path: Path):
    empty_ws = tmp_path / "empty_ws"
    empty_ws.mkdir()
    res = runner.invoke(app, ["report", "-w", str(empty_ws)])
    assert res.exit_code == 2


def test_cli_analyze_and_dcf_and_report_success(tmp_path: Path):
    ws = tmp_path / "ws"
    _create_sample_workspace(ws)

    # 1. Test analyze
    res_analyze = runner.invoke(app, ["analyze", "-w", str(ws)])
    assert res_analyze.exit_code == 0
    assert (ws / "forensics.json").exists()
    forensics = json.loads((ws / "forensics.json").read_text(encoding="utf-8"))
    assert "altman_z_double_prime" in forensics

    # 2. Test dcf
    res_dcf = runner.invoke(app, ["dcf", "-w", str(ws), "--price", "50.0", "--wacc", "0.09"])
    assert res_dcf.exit_code == 0
    assert (ws / "dcf.json").exists()
    dcf_data = json.loads((ws / "dcf.json").read_text(encoding="utf-8"))
    assert "intrinsic_value_per_share" in dcf_data
    assert dcf_data["intrinsic_value_per_share"] > 0

    # 3. Test report
    out_html = ws / "custom_report.html"
    res_report = runner.invoke(app, ["report", "-w", str(ws), "-o", str(out_html)])
    assert res_report.exit_code == 0
    assert out_html.exists()
    html_content = out_html.read_text(encoding="utf-8")
    assert "Test Corp" in html_content


def test_cli_extract_replay_miss_exit_4(tmp_path: Path):
    ws = tmp_path / "replay_ws"
    ws.mkdir()
    # Provide text dir and triage so load_pages succeeds
    (ws / "text").mkdir()
    (ws / "pages").mkdir()
    (ws / "text" / "page_001.txt").write_text("Balance Sheet", encoding="utf-8")
    triage_data = [
        {"n": 1, "page_class": "FINANCIAL_STATEMENT", "score": 10.0, "reasons": ["test"], "detected_unit": "millions"}
    ]
    (ws / "triage.json").write_text(json.dumps(triage_data), encoding="utf-8")

    # In replay mode with empty cache, choose_backend with local should fail if not cached or offline
    res = runner.invoke(app, ["extract", "-w", str(ws), "--backend", "local", "--replay"])
    assert res.exit_code == 4


def test_cli_bench_synthetic_subcommand(tmp_path: Path):
    from bench.synth_charts import generate_synthetic_charts
    synth_dir = tmp_path / "synth"
    out_dir = tmp_path / "results"
    generate_synthetic_charts(out_dir=synth_dir, n=3, seed=42)

    res = runner.invoke(app, ["bench", "--suite", "synth", "--limit", "2", "--synth-dir", str(synth_dir), "--out-dir", str(out_dir)])
    assert res.exit_code == 0
    assert (out_dir / "summary.md").exists()
    assert (out_dir / "results.json").exists()
