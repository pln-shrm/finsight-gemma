"""Provenance resolver: resolve extracted verbatim strings to PDF text-layer bboxes.

Hard rules (AGENTS.md):
- Every extracted number carries Provenance (page, modality, verbatim, bbox).
- Resolve bboxes from the PDF text layer first (bbox_source="text_layer").
- Model bboxes are fallback only (bbox_source="model").
- bbox is [x0, y0, x1, y1] normalized 0..1, origin top-left.
- from_model_box is the single adapter that converts model-native formats.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Literal

from PIL import Image

from .ingest import PageInfo
from .schemas import Provenance

BboxSource = Literal["text_layer", "model", "none"]


def _clean_token(tok: str) -> str:
    """Normalize a token by stripping whitespace, currency symbols, and commas."""
    tok = re.sub(r"[₹\$€£,\s]", "", tok)
    # Remove surrounding brackets/quotes
    return tok.strip("()[]\"'")


def _tokens_match(a: str, b: str) -> bool:
    """Check if two tokens match, tolerating currency symbols and number formatting."""
    if a.lower() == b.lower():
        return True
    ca = _clean_token(a)
    cb = _clean_token(b)
    return bool(ca and cb and ca.lower() == cb.lower())


def resolve_bbox(
    page: PageInfo,
    verbatim: str,
) -> tuple[list[float] | None, Literal["text_layer", "none"]]:
    """Find the verbatim text in the page's word boxes and return a union bbox in 0..1.

    Args:
        page: PageInfo containing words [(text, x0, y0, x1, y1), ...]
        verbatim: Source string to locate on the page.

    Returns:
        ([x0, y0, x1, y1], "text_layer") if found, else (None, "none").
    """
    if not verbatim or not page.words:
        return None, "none"

    target_tokens = verbatim.split()
    if not target_tokens:
        return None, "none"

    n_target = len(target_tokens)
    n_words = len(page.words)

    # 1. Exact multi-token contiguous sliding-window match
    for i in range(n_words - n_target + 1):
        candidate = page.words[i : i + n_target]
        matched = True
        for (w_text, *_), t_tok in zip(candidate, target_tokens, strict=False):
            if not _tokens_match(w_text, t_tok):
                matched = False
                break

        if matched:
            x0 = max(0.0, min(w[1] for w in candidate))
            y0 = max(0.0, min(w[2] for w in candidate))
            x1 = min(1.0, max(w[3] for w in candidate))
            y1 = min(1.0, max(w[4] for w in candidate))
            if x0 < x1 and y0 < y1:
                return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)], "text_layer"

    # 2. If multi-token match failed, but verbatim contains a distinct number token, search for that number
    # E.g. verbatim: "Revenue $1,234" -> search for "1,234"
    cleaned_targets = [_clean_token(t) for t in target_tokens if _clean_token(t)]
    # Look for numeric tokens first
    num_targets = [t for t in cleaned_targets if re.search(r"\d", t)]
    search_toks = num_targets if num_targets else cleaned_targets

    for st in search_toks:
        for w_text, x0, y0, x1, y1 in page.words:
            if _clean_token(w_text).lower() == st.lower():
                x0_c = max(0.0, x0)
                y0_c = max(0.0, y0)
                x1_c = min(1.0, x1)
                y1_c = min(1.0, y1)
                if x0_c < x1_c and y0_c < y1_c:
                    return [round(x0_c, 4), round(y0_c, 4), round(x1_c, 4), round(y1_c, 4)], "text_layer"

    return None, "none"


def from_model_box(raw: list[float] | list[int] | tuple, fmt: str = "ymin_xmin_ymax_xmax_1000") -> list[float]:
    """Convert model-native bounding box formats into standard [x0, y0, x1, y1] in 0..1.

    Supported formats:
    - 'ymin_xmin_ymax_xmax_1000': Gemini 0..1000 scale [ymin, xmin, ymax, xmax]
    - 'ymin_xmin_ymax_xmax_norm': Normalized 0..1 scale [ymin, xmin, ymax, xmax]
    - 'xyxy_norm': Standard [x0, y0, x1, y1] normalized 0..1
    - 'xyxy_1000': [x0, y0, x1, y1] on 0..1000 scale
    - 'xywh_norm': [x, y, w, h] normalized 0..1
    """
    if len(raw) != 4:
        raise ValueError(f"Expected 4 coordinates, got {len(raw)}: {raw}")

    vals = [float(v) for v in raw]

    if fmt == "ymin_xmin_ymax_xmax_1000":
        ymin, xmin, ymax, xmax = vals
        x0, y0, x1, y1 = xmin / 1000.0, ymin / 1000.0, xmax / 1000.0, ymax / 1000.0
    elif fmt == "ymin_xmin_ymax_xmax_norm":
        ymin, xmin, ymax, xmax = vals
        x0, y0, x1, y1 = xmin, ymin, xmax, ymax
    elif fmt == "xyxy_norm":
        x0, y0, x1, y1 = vals
    elif fmt == "xyxy_1000":
        x0, y0, x1, y1 = (v / 1000.0 for v in vals)
    elif fmt == "xywh_norm":
        x, y, w, h = vals
        x0, y0, x1, y1 = x, y, x + w, y + h
    else:
        raise ValueError(f"Unknown model box format: {fmt}")

    # Clamp to [0, 1]
    x0 = max(0.0, min(1.0, x0))
    y0 = max(0.0, min(1.0, y0))
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))

    # Ensure strictly x0 < x1 and y0 < y1
    if x1 <= x0:
        x1 = min(1.0, x0 + 0.001)
    if y1 <= y0:
        y1 = min(1.0, y0 + 0.001)

    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]


def resolve_provenance(
    page: PageInfo,
    verbatim: str,
    *,
    modality: Literal["text_table", "visual_table", "visual_chart", "footnote_prose"] = "text_table",
    model_box: list[float] | list[int] | None = None,
    model_box_fmt: str = "ymin_xmin_ymax_xmax_1000",
) -> Provenance:
    """Resolve full Provenance object, prioritizing the text layer with model bbox fallback."""
    bbox, source = resolve_bbox(page, verbatim)

    if bbox is None and model_box is not None:
        try:
            bbox = from_model_box(model_box, fmt=model_box_fmt)
            source = "model"
        except (ValueError, TypeError):
            bbox = None
            source = "none"

    return Provenance(
        page=page.n,
        modality=modality,
        verbatim=verbatim,
        bbox=bbox,
        bbox_source=source,
    )


def crop(
    page_png: Path | bytes | str,
    bbox: list[float],
    pad: float = 0.01,
) -> bytes:
    """Crop the region defined by *bbox* from *page_png*, with padding *pad*.

    Args:
        page_png: Path to PNG or raw image bytes.
        bbox: [x0, y0, x1, y1] normalized 0..1.
        pad: Extra padding fraction (default 1%).

    Returns:
        PNG image bytes of the cropped snippet.
    """
    if isinstance(page_png, (str, Path)):
        img = Image.open(page_png)
    else:
        img = Image.open(io.BytesIO(page_png))

    width, height = img.size

    x0, y0, x1, y1 = bbox
    px0 = max(0, int((x0 - pad) * width))
    py0 = max(0, int((y0 - pad) * height))
    px1 = min(width, int((x1 + pad) * width))
    py1 = min(height, int((y1 + pad) * height))

    if px1 <= px0:
        px1 = min(width, px0 + 1)
    if py1 <= py0:
        py1 = min(height, py0 + 1)

    cropped = img.crop((px0, py0, px1, py1))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()
