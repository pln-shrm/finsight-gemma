"""FinSight-Gemma CLI entrypoint.

Exposes commands matching docs/architecture.md:
- finsight ingest <pdf> --workspace W
- finsight extract --workspace W [--backend auto|local|cloud] [--replay] [--confidential]
- finsight charts --workspace W
- finsight analyze --workspace W [--market-cap N]
- finsight dcf --workspace W --price P --wacc 0.10 --terminal-growth 0.03 [...]
- finsight report --workspace W --out report.html
- finsight run <pdf> --workspace W [...]
- finsight bench [--suite synth|real|all] [--backend ...]

Exit codes (docs/architecture.md):
0: success, all error-level checks passed
2: usage / missing input
3: verification errors remain after retries (outputs written, flagged unreliable)
4: backend unavailable (no Ollama / no key / replay miss)
5: schema validation failed after retries
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from .backends import ExtractionError, choose_backend
from .cache import ReplayMiss
from .charts import audit as audit_chart
from .charts import extract_chart, measure_bars_cv
from .dcf import DCFInputs, monte_carlo, sensitivity_matrix, value_per_share
from .extract import extract_financials, save_extraction_artifacts
from .forensics import run_all
from .ingest import PageInfo
from .ingest import ingest as run_ingest
from .report import render_report
from .schemas import Financials
from .triage import load_triage, save_triage, score_pages, selected_pages

app = typer.Typer(
    name="finsight",
    help="FinSight-Gemma: Neuro-symbolic financial filing auditor.",
    no_args_is_help=True,
)


def _load_pages_from_ws(ws: Path) -> list[PageInfo]:
    """Reconstruct PageInfo objects from ws/text/ and ws/pages/."""
    text_dir = ws / "text"
    pages_dir = ws / "pages"
    if not text_dir.exists():
        raise FileNotFoundError(f"Missing workspace directory: {text_dir}. Run 'finsight ingest' first.")

    pages: list[PageInfo] = []
    # Primary: check for JSON files written by ingest.py (p0001.json, page_001.json, etc.)
    json_files = sorted(text_dir.glob("*.json"))
    if json_files:
        for jf in json_files:
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                n = int(data.get("n", 1))
                text = data.get("text", "")
                words = []
                for w in data.get("words", []):
                    if isinstance(w, dict):
                        words.append((w.get("text", ""), w.get("x0", 0.0), w.get("y0", 0.0), w.get("x1", 1.0), w.get("y1", 1.0)))
                    elif isinstance(w, (list, tuple)):
                        words.append(tuple(w))

                png_path = pages_dir / f"p{n:04d}.png"
                if not png_path.exists():
                    png_path = pages_dir / f"page_{n:03d}.png"

                pages.append(PageInfo(n=n, png_path=png_path, words=words, text=text))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    else:
        # Fallback for plain text files
        for txt_file in sorted(text_dir.glob("page_*.txt")):
            num_str = txt_file.stem.split("_")[-1]
            n = int(num_str)
            png_path = pages_dir / f"page_{n:03d}.png"
            text = txt_file.read_text(encoding="utf-8")
            pages.append(PageInfo(n=n, png_path=png_path, words=[], text=text))

    return sorted(pages, key=lambda p: p.n)


@app.command()
def ingest(
    pdf: Annotated[Path, typer.Argument(help="Path to regulatory PDF filing")],
    workspace: Annotated[Path, typer.Option("--workspace", "-w", help="Workspace directory")] = Path("workspace"),
    dpi: Annotated[int, typer.Option("--dpi", help="Render resolution DPI")] = 160,
) -> None:
    """Render PDF pages to PNG and run deterministic keyword/regex page triage."""
    if not pdf.exists():
        typer.echo(f"Error: PDF not found: {pdf}", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Ingesting {pdf} -> {workspace} (dpi={dpi})...")
    pages = run_ingest(pdf, workspace, dpi=dpi)

    typer.echo(f"Running deterministic page triage across {len(pages)} pages...")
    scores = score_pages(pages)
    save_triage(scores, workspace)

    statements = selected_pages(scores, include=("FINANCIAL_STATEMENT",))
    recons = selected_pages(scores, include=("NON_GAAP_RECON",))
    charts = selected_pages(scores, include=("CHART",))

    typer.echo(f"Triage complete: {len(statements)} statement pages, {len(recons)} recon pages, {len(charts)} charts.")
    for s in statements:
        typer.echo(f"  Statement Page {s.n}: {', '.join(s.reasons)}")


@app.command()
def extract(
    workspace: Annotated[Path, typer.Option("--workspace", "-w", help="Workspace directory")] = Path("workspace"),
    backend: Annotated[str, typer.Option("--backend", "-b", help="auto | local | cloud")] = "auto",
    replay: Annotated[bool, typer.Option("--replay", help="Fail if any unrecorded call is made")] = False,
    confidential: Annotated[bool, typer.Option("--confidential", help="Enforce local-only execution")] = False,
) -> None:
    """Extract financial statements using schema-constrained model with solver retry loop."""
    try:
        pages = _load_pages_from_ws(workspace)
        scores = load_triage(workspace)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2)

    stmt_pages = selected_pages(scores, include=("FINANCIAL_STATEMENT",))
    if not stmt_pages:
        stmt_pages = selected_pages(scores, include=("FINANCIAL_STATEMENT", "NON_GAAP_RECON"))
    top_pages = sorted(stmt_pages, key=lambda s: s.score, reverse=True)[:3]
    page_numbers = sorted([s.n for s in top_pages]) if top_pages else [p.n for p in pages[:3]]

    try:
        be = choose_backend(
            confidential=confidential,
            backend_override=backend,
            replay=replay,
            cache_dir=workspace / ".cache",
        )
    except (ValueError, KeyError, RuntimeError) as e:
        typer.echo(f"Backend routing error: {e}", err=True)
        raise typer.Exit(code=4)

    typer.echo(f"Extracting financials using {be.name} on pages {page_numbers}...")
    try:
        fin, rep, logs = extract_financials(pages, selected_page_numbers=page_numbers, backend=be)
    except ReplayMiss as e:
        typer.echo(f"Replay miss: {e}", err=True)
        raise typer.Exit(code=4)
    except ExtractionError as e:
        typer.echo(f"Extraction error: {e}", err=True)
        raise typer.Exit(code=4)
    except ValidationError as e:
        typer.echo(f"Schema validation failed: {e}", err=True)
        raise typer.Exit(code=5)

    save_extraction_artifacts(fin, rep, logs, workspace)
    typer.echo(f"Extraction finished. Verification passed: {rep.passed} (Attempts: {len(logs)})")

    if not rep.passed:
        for err in rep.errors:
            typer.echo(f"  Violation [{err.code}]: {err.message} (residual: {err.residual})")
        raise typer.Exit(code=3)


@app.command()
def charts(
    workspace: Annotated[Path, typer.Option("--workspace", "-w", help="Workspace directory")] = Path("workspace"),
    backend: Annotated[str, typer.Option("--backend", "-b", help="auto | local | cloud")] = "auto",
    replay: Annotated[bool, typer.Option("--replay", help="Replay mode")] = False,
    confidential: Annotated[bool, typer.Option("--confidential", help="Confidential mode")] = False,
) -> None:
    """Extract visual charts, measure bar geometry with OpenCV, and audit Lie Factor."""
    try:
        pages = _load_pages_from_ws(workspace)
        scores = load_triage(workspace)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2)

    chart_pages = selected_pages(scores, include=("CHART",))
    if not chart_pages:
        typer.echo("No chart pages identified during triage.")
        return

    try:
        be = choose_backend(
            confidential=confidential,
            backend_override=backend,
            replay=replay,
            cache_dir=workspace / ".cache",
        )
    except (ValueError, KeyError, RuntimeError) as e:
        typer.echo(f"Backend error: {e}", err=True)
        raise typer.Exit(code=4)

    audited_charts: list[dict] = []
    for cp in chart_pages:
        page_info = next((p for p in pages if p.n == cp.n), None)
        if not page_info:
            continue

        typer.echo(f"Extracting chart on Page {cp.n}...")
        try:
            extracted = extract_chart(page_info.png_path, backend=be)
            cv_heights = measure_bars_cv(page_info.png_path, n_bars=len(extracted.points))
            res = audit_chart(extracted, measured=cv_heights)
            res["page"] = cp.n
            audited_charts.append(res)
            if res.get("flag"):
                typer.echo(f"  FLAG: Distorted chart on p.{cp.n} (Lie Factor = {res.get('worst', {}).get('lie_factor'):.2f})")
        except (ExtractionError, ValueError, KeyError) as e:
            typer.echo(f"  Skipped chart on p.{cp.n}: {e}")

    out_file = workspace / "charts.json"
    out_file.write_text(json.dumps(audited_charts, indent=2), encoding="utf-8")
    typer.echo(f"Chart audits written to {out_file}")


@app.command()
def analyze(
    workspace: Annotated[Path, typer.Option("--workspace", "-w", help="Workspace directory")] = Path("workspace"),
    market_cap: Annotated[float | None, typer.Option("--market-cap", help="Market cap for Altman Z-score")] = None,
) -> None:
    """Run quantitative forensics: DuPont 5-factor, Altman Z'', Beneish M, Piotroski F."""
    fin_file = workspace / "financials.json"
    if not fin_file.exists():
        typer.echo(f"Missing {fin_file}. Run 'finsight extract' first.", err=True)
        raise typer.Exit(code=2)

    fin = Financials.model_validate_json(fin_file.read_text(encoding="utf-8"))
    res = run_all(fin, market_cap=market_cap)

    out_file = workspace / "forensics.json"
    out_file.write_text(json.dumps(res, indent=2), encoding="utf-8")

    typer.echo(f"Forensics complete. Written to {out_file}")
    if res.get("flags"):
        typer.echo(f"Flags detected ({len(res['flags'])}):")
        for f in res["flags"]:
            typer.echo(f"  - {f}")


@app.command()
def dcf(
    workspace: Annotated[Path, typer.Option("--workspace", "-w", help="Workspace directory")] = Path("workspace"),
    price: Annotated[float, typer.Option("--price", "-p", help="Current stock price")] = 100.0,
    wacc: Annotated[float, typer.Option("--wacc", help="Weighted average cost of capital")] = 0.10,
    terminal_growth: Annotated[float, typer.Option("--terminal-growth", "-g", help="Perpetual growth rate")] = 0.03,
    growth_start: Annotated[float | None, typer.Option("--growth", help="Year-1 revenue growth")] = None,
    margin_target: Annotated[float | None, typer.Option("--margin-target", help="Final year target margin")] = None,
) -> None:
    """Run distribution-first DCF valuation sensitivity matrix and Monte Carlo simulation."""
    fin_file = workspace / "financials.json"
    if not fin_file.exists():
        typer.echo(f"Missing {fin_file}. Run 'finsight extract' first.", err=True)
        raise typer.Exit(code=2)

    fin = Financials.model_validate_json(fin_file.read_text(encoding="utf-8"))
    rev0 = fin.val("revenue") or 1000.0
    ebit = fin.val("ebit") or (rev0 * 0.15)
    margin0 = ebit / rev0 if rev0 else 0.15
    g1 = growth_start if growth_start is not None else 0.10
    m_t = margin_target if margin_target is not None else margin0

    cash = fin.val("cash") or 0.0
    debt = fin.val("long_term_debt") or 0.0
    net_debt = debt - cash
    shares = fin.val("shares_outstanding") or 100.0

    dcf_in = DCFInputs(
        revenue0=rev0,
        growth_start=g1,
        growth_terminal=terminal_growth,
        margin_start=margin0,
        margin_target=m_t,
        tax_rate=0.25,
        sales_to_capital=2.0,
        wacc=wacc,
        net_debt=net_debt,
        shares=shares,
    )

    base_val = value_per_share(dcf_in)
    sens = sensitivity_matrix(dcf_in, waccs=[wacc - 0.02, wacc, wacc + 0.02], gs=[terminal_growth - 0.01, terminal_growth, terminal_growth + 0.01])
    mc = monte_carlo(dcf_in, n=5000, price=price)

    dcf_data = {
        "inputs": dcf_in.__dict__,
        "intrinsic_value_per_share": base_val,
        "sensitivity": sens,
        "monte_carlo": mc,
    }

    out_file = workspace / "dcf.json"
    out_file.write_text(json.dumps(dcf_data, indent=2), encoding="utf-8")
    typer.echo(f"DCF intrinsic value per share: ${base_val:.2f} (Current price: ${price:.2f})")
    if "prob_value_above_price" in mc:
        typer.echo(f"Probability intrinsic value > price: {mc['prob_value_above_price']:.1%}")


@app.command()
def report(
    workspace: Annotated[Path, typer.Option("--workspace", "-w", help="Workspace directory")] = Path("workspace"),
    out: Annotated[Path, typer.Option("--out", "-o", help="Output HTML report path")] = Path("report.html"),
) -> None:
    """Generate self-contained HTML audit report with evidence crops and quantitative breakdowns."""
    try:
        report_path = render_report(workspace, out=out)
        typer.echo(f"Audit report generated successfully: {report_path}")
    except FileNotFoundError as e:
        typer.echo(f"Report generation error: {e}", err=True)
        raise typer.Exit(code=2)


@app.command()
def run(
    pdf: Annotated[Path, typer.Argument(help="Path to PDF filing")],
    workspace: Annotated[Path, typer.Option("--workspace", "-w", help="Workspace directory")] = Path("workspace"),
    backend: Annotated[str, typer.Option("--backend", "-b", help="auto | local | cloud")] = "auto",
    replay: Annotated[bool, typer.Option("--replay", help="Replay mode")] = False,
    confidential: Annotated[bool, typer.Option("--confidential", help="Confidential mode")] = False,
    price: Annotated[float | None, typer.Option("--price", help="Share price for DCF valuation")] = None,
    market_cap: Annotated[float | None, typer.Option("--market-cap", help="Market capitalization")] = None,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output HTML report path")] = Path("report.html"),
) -> None:
    """End-to-end audit: ingest -> extract -> charts -> analyze -> dcf -> report."""
    typer.echo("=== FinSight-Gemma Filing Audit ===")
    ingest(pdf=pdf, workspace=workspace)

    exit_code = 0
    try:
        extract(workspace=workspace, backend=backend, replay=replay, confidential=confidential)
    except typer.Exit as e:
        if e.exit_code == 3:
            exit_code = 3  # verification error
        else:
            raise

    try:
        charts(workspace=workspace, backend=backend, replay=replay, confidential=confidential)
    except (ValueError, KeyError, RuntimeError) as e:
        typer.echo(f"Charts warning: {e}")

    analyze(workspace=workspace, market_cap=market_cap)

    if price is not None:
        try:
            dcf(workspace=workspace, price=price)
        except (ValueError, KeyError, RuntimeError) as e:
            typer.echo(f"DCF warning: {e}")

    report(workspace=workspace, out=out)
    typer.echo(f"\nAudit complete. Open {out} in any web browser (works offline).")
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command()
def bench(
    suite: Annotated[str, typer.Option("--suite", help="synth | real | all")] = "synth",
    limit: Annotated[int | None, typer.Option("--limit", help="Max charts to evaluate")] = None,
    synth_dir: Annotated[Path, typer.Option("--synth-dir", help="Synthetic charts directory")] = Path("bench/synth"),
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Output directory")] = Path("bench/results"),
) -> None:
    """Run FinSight benchmark on synthetic or real test suites."""
    from bench.run_bench import run_synthetic_benchmark
    run_synthetic_benchmark(synth_dir=synth_dir, out_dir=out_dir, limit=limit)


if __name__ == "__main__":
    app()
