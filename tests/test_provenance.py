"""Unit tests for provenance.py: text-layer resolution, model box adapters, cropping."""
from __future__ import annotations

import io
from pathlib import Path

import fitz
import pytest
from PIL import Image

from finsight.ingest import ingest
from finsight.provenance import (
    crop,
    from_model_box,
    resolve_bbox,
    resolve_provenance,
)


def _make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Draw at known coordinates
    page.insert_text((100, 200), text, fontsize=14)
    doc.save(str(path))
    doc.close()


def test_resolve_bbox_exact_match(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf, "Total Assets $5,432")
    pages = ingest(pdf, tmp_path / "ws")
    page = pages[0]

    bbox, source = resolve_bbox(page, "Total Assets $5,432")
    assert source == "text_layer"
    assert bbox is not None
    assert len(bbox) == 4
    x0, y0, x1, y1 = bbox
    assert 0.0 <= x0 < x1 <= 1.0
    assert 0.0 <= y0 < y1 <= 1.0


def test_resolve_bbox_numeric_token_match(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf, "Revenues 1,234")
    pages = ingest(pdf, tmp_path / "ws")
    page = pages[0]

    # Model returned verbatim with currency symbol "$1,234" but page had "1,234"
    bbox, source = resolve_bbox(page, "$1,234")
    assert source == "text_layer"
    assert bbox is not None


def test_resolve_bbox_not_found(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf, "Operating Profit 500")
    pages = ingest(pdf, tmp_path / "ws")
    page = pages[0]

    bbox, source = resolve_bbox(page, "Completely Missing Text 9999")
    assert source == "none"
    assert bbox is None


def test_from_model_box_gemini_format():
    # Gemini format: [ymin, xmin, ymax, xmax] on 0..1000 scale
    raw = [200, 100, 400, 300]
    std = from_model_box(raw, fmt="ymin_xmin_ymax_xmax_1000")
    # Standard format: [x0, y0, x1, y1] on 0..1 scale
    assert std == [0.1, 0.2, 0.3, 0.4]


def test_from_model_box_xywh_norm():
    raw = [0.1, 0.2, 0.3, 0.4]
    std = from_model_box(raw, fmt="xywh_norm")
    # x0=0.1, y0=0.2, x1=0.1+0.3=0.4, y1=0.2+0.4=0.6
    assert std == [0.1, 0.2, 0.4, 0.6]


def test_from_model_box_clamps_and_validates():
    # Degenerate box where xmin == xmax
    raw = [100, 100, 200, 100]
    std = from_model_box(raw, fmt="ymin_xmin_ymax_xmax_1000")
    assert std[0] < std[2]
    assert std[1] < std[3]

    with pytest.raises(ValueError, match="Expected 4 coordinates"):
        from_model_box([1, 2, 3])

    with pytest.raises(ValueError, match="Unknown model box format"):
        from_model_box([1, 2, 3, 4], fmt="unknown_format")


def test_resolve_provenance_priority(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf, "Cash and equivalents 800")
    pages = ingest(pdf, tmp_path / "ws")
    page = pages[0]

    # 1. Text layer exists -> text_layer takes precedence over model box
    prov1 = resolve_provenance(
        page,
        verbatim="Cash and equivalents 800",
        model_box=[500, 500, 600, 600],
    )
    assert prov1.bbox_source == "text_layer"

    # 2. Text layer missing -> fallback to model box
    prov2 = resolve_provenance(
        page,
        verbatim="Unreadable Item",
        model_box=[200, 100, 300, 200],
    )
    assert prov2.bbox_source == "model"
    assert prov2.bbox == [0.1, 0.2, 0.2, 0.3]

    # 3. Both missing -> none
    prov3 = resolve_provenance(
        page,
        verbatim="Unreadable Item",
        model_box=None,
    )
    assert prov3.bbox_source == "none"
    assert prov3.bbox is None


def test_crop_produces_valid_image(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf, "Net Income 250")
    pages = ingest(pdf, tmp_path / "ws")
    page = pages[0]

    bbox = [0.1, 0.1, 0.4, 0.3]
    cropped_bytes = crop(page.png_path, bbox)
    assert len(cropped_bytes) > 0

    img = Image.open(io.BytesIO(cropped_bytes))
    assert img.format == "PNG"
    assert img.size[0] > 0 and img.size[1] > 0
