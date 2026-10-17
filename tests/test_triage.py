"""Tests for triage.py — deterministic page triage scoring and classification."""
from __future__ import annotations

from pathlib import Path

import fitz

from finsight.ingest import ingest
from finsight.triage import (
    PageScore,
    detect_unit,
    load_triage,
    save_triage,
    score_pages,
    selected_pages,
)


def _make_pdf(path: Path, pages: list[str]) -> None:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), text, fontsize=12)
    doc.save(str(path))
    doc.close()


def test_financial_statement_classification(tmp_path: Path):
    pdf = tmp_path / "filing.pdf"
    content = (
        "Consolidated Balance Sheet\n"
        "Total Assets: $5,000\n"
        "Total Liabilities: $2,000\n"
        "Stockholders' Equity: $3,000\n"
        "Retained Earnings: $1,500\n"
        "Cash and cash equivalents: $800"
    )
    _make_pdf(pdf, [content])
    pages = ingest(pdf, tmp_path / "ws")
    scores = score_pages(pages)

    assert len(scores) == 1
    assert scores[0].n == 1
    assert scores[0].page_class == "FINANCIAL_STATEMENT"
    assert scores[0].score >= 4.0
    assert "TOTAL_ASSETS" in scores[0].reasons


def test_income_statement_classification(tmp_path: Path):
    pdf = tmp_path / "filing.pdf"
    content = (
        "Consolidated Statement of Operations\n"
        "Total Revenues: $10,000\n"
        "Operating Income: $2,500\n"
        "Net Income: $1,800\n"
        "Earnings Per Share: $2.50"
    )
    _make_pdf(pdf, [content])
    pages = ingest(pdf, tmp_path / "ws")
    scores = score_pages(pages)

    assert scores[0].page_class == "FINANCIAL_STATEMENT"
    assert "NET_INCOME" in scores[0].reasons


def test_non_gaap_recon_classification(tmp_path: Path):
    pdf = tmp_path / "filing.pdf"
    content = (
        "Non-GAAP Financial Measures and Reconciliation\n"
        "Adjusted EBITDA reconciliation to Net Income\n"
        "Stock-based compensation add-back: $150\n"
        "Restructuring charges: $50"
    )
    _make_pdf(pdf, [content])
    pages = ingest(pdf, tmp_path / "ws")
    scores = score_pages(pages)

    assert scores[0].page_class == "NON_GAAP_RECON"
    assert "NON_GAAP" in scores[0].reasons


def test_footnote_classification(tmp_path: Path):
    pdf = tmp_path / "filing.pdf"
    content = (
        "Notes to Consolidated Financial Statements\n"
        "Note 1: Significant Accounting Policies\n"
        "Basis of presentation and preparation\n"
        "Fair value measurement hierarchy"
    )
    _make_pdf(pdf, [content])
    pages = ingest(pdf, tmp_path / "ws")
    scores = score_pages(pages)

    assert scores[0].page_class == "FOOTNOTE"
    assert "NOTES_HEADER" in scores[0].reasons


def test_sparse_chart_page(tmp_path: Path):
    pdf = tmp_path / "filing.pdf"
    # Under 25 words with chart keywords
    content = "Figure 1: Revenue CAGR by Segment\nBar chart comparison"
    _make_pdf(pdf, [content])
    pages = ingest(pdf, tmp_path / "ws")
    scores = score_pages(pages)

    assert scores[0].page_class == "CHART"
    assert any("SPARSE_PAGE" in r for r in scores[0].reasons)


def test_ignore_page(tmp_path: Path):
    pdf = tmp_path / "filing.pdf"
    content = (
        "Annual General Meeting Notice\n"
        "The meeting will be held at our headquarters.\n"
        "Please bring your identification card.\n"
        "All shareholders are cordially invited to attend."
    )
    _make_pdf(pdf, [content])
    pages = ingest(pdf, tmp_path / "ws")
    scores = score_pages(pages)

    assert scores[0].page_class == "IGNORE"
    assert scores[0].score == 0.0


def test_detect_units():
    assert detect_unit("Amounts in millions of USD") == "millions"
    assert detect_unit("(in billions, except share amounts)") == "billions"
    assert detect_unit("All values in ₹ crores") == "crores"
    assert detect_unit("Standalone figures in lakhs") == "lakhs"
    assert detect_unit("Data presented in thousands") == "thousands"
    assert detect_unit("No unit specified here") is None


def test_save_and_load_triage(tmp_path: Path):
    scores = [
        PageScore(n=1, page_class="FINANCIAL_STATEMENT", score=8.0, reasons=["STMT_NAME"], detected_unit="millions"),
        PageScore(n=2, page_class="IGNORE", score=0.0, reasons=[], detected_unit=None),
        PageScore(n=3, page_class="NON_GAAP_RECON", score=6.0, reasons=["NON_GAAP"], detected_unit="billions"),
    ]
    ws = tmp_path / "workspace"
    out = save_triage(scores, ws)
    assert out.exists()
    assert out.name == "triage.json"

    loaded = load_triage(ws)
    assert len(loaded) == 3
    assert loaded[0].n == 1
    assert loaded[0].page_class == "FINANCIAL_STATEMENT"
    assert loaded[0].detected_unit == "millions"
    assert loaded[1].page_class == "IGNORE"
    assert loaded[2].page_class == "NON_GAAP_RECON"
    assert loaded[2].detected_unit == "billions"


def test_selected_pages():
    scores = [
        PageScore(n=1, page_class="IGNORE", score=0.0, reasons=[]),
        PageScore(n=2, page_class="FINANCIAL_STATEMENT", score=8.0, reasons=[]),
        PageScore(n=3, page_class="FOOTNOTE", score=5.0, reasons=[]),
        PageScore(n=4, page_class="NON_GAAP_RECON", score=7.0, reasons=[]),
        PageScore(n=5, page_class="CHART", score=3.0, reasons=[]),
    ]
    selected = selected_pages(scores)
    assert [s.n for s in selected] == [2, 4]
