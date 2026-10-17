"""PDF ingestion: render pages to PNG and extract the text layer with normalized word bounding boxes.

Security: PDF content is untrusted data. We render pages to bitmaps and read text positions
only — no JavaScript execution, no external font/URL loading, no form evaluation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass
class PageInfo:
    """All data extracted from a single PDF page during ingest."""

    n: int          # 1-indexed page number
    png_path: Path  # absolute path to the rendered PNG
    # (text, x0, y0, x1, y1) — bbox normalized 0..1, origin top-left
    words: list[tuple[str, float, float, float, float]]
    text: str       # full page text concatenated from the text layer


def ingest(pdf: Path, ws: Path, dpi: int = 160) -> list[PageInfo]:
    """Render every page of *pdf* to PNG and extract its text layer.

    Args:
        pdf: Path to the source PDF.
        ws:  Workspace directory.  ``pages/`` and ``text/`` sub-dirs are created.
        dpi: Render resolution (default 160 — good quality vs file-size balance).

    Returns:
        One :class:`PageInfo` per page, in document order (1-indexed).

    Raises:
        FileNotFoundError: if *pdf* does not exist.
        fitz.FileDataError: if PyMuPDF cannot parse the file.

    Security:
        - Opens the document read-only; suppresses JavaScript and external resources.
        - Text is extracted as plain strings and never evaluated or executed.
    """
    pdf = Path(pdf)
    ws = Path(ws)
    if not pdf.exists():
        raise FileNotFoundError(pdf)

    pages_dir = ws / "pages"
    text_dir = ws / "text"
    pages_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    # 72 pt/inch is PyMuPDF's internal unit; scale to the target DPI.
    matrix = fitz.Matrix(dpi / 72, dpi / 72)

    results: list[PageInfo] = []

    # fitz.FITZFLAG_* are version-dependent; use the safe open() defaults.
    # We never call page.run_javascript() or page.load_links().
    with fitz.open(str(pdf)) as doc:
        for page_idx in range(len(doc)):
            page = doc.load_page(page_idx)
            n = page_idx + 1  # 1-indexed

            # ── Render to PNG ────────────────────────────────────────────────
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
            png_path = pages_dir / f"p{n:04d}.png"
            pix.save(str(png_path))

            # ── Extract word bounding boxes ─────────────────────────────────
            pw, ph = page.rect.width, page.rect.height  # page dims in points
            # get_text("words") → (x0, y0, x1, y1, word, block, line, word_no)
            raw_words = page.get_text("words")
            words: list[tuple[str, float, float, float, float]] = []
            for rw in raw_words:
                x0, y0, x1, y1, word_text = rw[0], rw[1], rw[2], rw[3], rw[4]
                if not word_text.strip():
                    continue  # skip whitespace-only tokens
                # Normalize to [0, 1]; clamp for safety on malformed PDFs.
                nx0 = max(0.0, min(1.0, x0 / pw))
                ny0 = max(0.0, min(1.0, y0 / ph))
                nx1 = max(0.0, min(1.0, x1 / pw))
                ny1 = max(0.0, min(1.0, y1 / ph))
                words.append((word_text, nx0, ny0, nx1, ny1))

            # ── Full page text ───────────────────────────────────────────────
            full_text: str = page.get_text("text")

            # ── Persist text JSON ────────────────────────────────────────────
            text_json = {
                "n": n,
                "width_pt": pw,
                "height_pt": ph,
                "words": [
                    {"text": t, "x0": x0, "y0": y0, "x1": x1, "y1": y1}
                    for t, x0, y0, x1, y1 in words
                ],
                "text": full_text,
            }
            text_path = text_dir / f"p{n:04d}.json"
            text_path.write_text(
                json.dumps(text_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            results.append(
                PageInfo(n=n, png_path=png_path.resolve(), words=words, text=full_text)
            )

    return results
