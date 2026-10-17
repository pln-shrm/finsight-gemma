"""Tests for ingest.py — use synthetic PDFs so no external files are needed."""
from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from finsight.ingest import PageInfo, ingest

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_pdf(path: Path, pages: list[str]) -> None:
    """Create a minimal multi-page digital PDF with known text content."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page(width=595, height=842)  # A4 in points
        page.insert_text((72, 100), text, fontsize=12)
    doc.save(str(path))
    doc.close()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_returns_one_pageinfo_per_page(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Revenue 1000", "Assets 2000", "Cash Flow 500"])

    result = ingest(pdf, tmp_path / "ws")

    assert len(result) == 3
    assert all(isinstance(p, PageInfo) for p in result)
    assert [p.n for p in result] == [1, 2, 3]


def test_page_numbers_are_1_indexed(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["first", "second"])

    result = ingest(pdf, tmp_path / "ws")

    assert result[0].n == 1
    assert result[1].n == 2


def test_creates_png_files(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Page one", "Page two"])

    result = ingest(pdf, tmp_path / "ws")

    for pi in result:
        assert pi.png_path.exists(), f"Missing PNG for page {pi.n}"
        assert pi.png_path.suffix == ".png"
        assert pi.png_path.stat().st_size > 0, f"Empty PNG for page {pi.n}"


def test_creates_text_json_files(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Revenue 1000"])
    ws = tmp_path / "ws"

    ingest(pdf, ws)

    text_file = ws / "text" / "p0001.json"
    assert text_file.exists()
    data = json.loads(text_file.read_text(encoding="utf-8"))
    assert "n" in data and data["n"] == 1
    assert "words" in data
    assert "text" in data
    assert "width_pt" in data
    assert "height_pt" in data


def test_workspace_directory_structure(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["one"])
    ws = tmp_path / "ws"

    ingest(pdf, ws)

    assert (ws / "pages").is_dir()
    assert (ws / "text").is_dir()
    assert (ws / "pages" / "p0001.png").exists()
    assert (ws / "text" / "p0001.json").exists()


def test_word_boxes_normalized_0_to_1(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Revenue 1000 Total Assets 5000"])
    ws = tmp_path / "ws"

    result = ingest(pdf, ws)

    for word_text, x0, y0, x1, y1 in result[0].words:
        assert 0.0 <= x0 <= 1.0, f"x0={x0} out of [0,1] for '{word_text}'"
        assert 0.0 <= y0 <= 1.0, f"y0={y0} out of [0,1] for '{word_text}'"
        assert 0.0 <= x1 <= 1.0, f"x1={x1} out of [0,1] for '{word_text}'"
        assert 0.0 <= y1 <= 1.0, f"y1={y1} out of [0,1] for '{word_text}'"


def test_word_box_x0_lt_x1_y0_lt_y1(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Revenue 1000"])
    ws = tmp_path / "ws"

    result = ingest(pdf, ws)

    for word_text, x0, y0, x1, y1 in result[0].words:
        assert x0 < x1, f"x0 >= x1 for '{word_text}'"
        assert y0 < y1, f"y0 >= y1 for '{word_text}'"


def test_text_contains_page_content(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Revenue 1000", "Total Assets 5000"])
    ws = tmp_path / "ws"

    result = ingest(pdf, ws)

    assert "Revenue" in result[0].text
    assert "Assets" in result[1].text


def test_whitespace_only_words_excluded(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Hello World"])
    ws = tmp_path / "ws"

    result = ingest(pdf, ws)

    for word_text, *_ in result[0].words:
        assert word_text.strip() != "", f"Empty word token found: {word_text!r}"


def test_missing_pdf_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest(tmp_path / "nonexistent.pdf", tmp_path / "ws")


def test_json_words_match_pageinfo_words(tmp_path):
    """Words in PageInfo must exactly match what's written to the JSON file."""
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Net Income 250"])
    ws = tmp_path / "ws"

    result = ingest(pdf, ws)
    pi = result[0]

    data = json.loads((ws / "text" / "p0001.json").read_text(encoding="utf-8"))
    json_words = [(w["text"], w["x0"], w["y0"], w["x1"], w["y1"]) for w in data["words"]]

    assert list(pi.words) == json_words


def test_multipage_json_filenames_zero_padded(tmp_path):
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, [f"Page {i}" for i in range(1, 12)])  # 11 pages
    ws = tmp_path / "ws"

    ingest(pdf, ws)

    assert (ws / "text" / "p0001.json").exists()
    assert (ws / "text" / "p0011.json").exists()
    assert (ws / "pages" / "p0001.png").exists()
    assert (ws / "pages" / "p0011.png").exists()
