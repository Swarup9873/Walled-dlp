"""Turn files into searchable text.

Supported: plain text, PDF (text layer, with OCR fallback), images (OCR).
The heavy libraries are imported lazily so the app starts fast and so that a
missing optional dependency only affects the file type that needs it.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

from core import config

log = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}


@dataclass
class Extracted:
    text: str
    ocr_used: bool = False  # OCR text is noisy, so it is matched fuzzily


def detect_kind(name: str, data: bytes) -> str:
    """Return 'pdf', 'image' or 'text' using magic bytes first, then extension."""
    head = data[:12]
    if head.startswith(b"%PDF"):
        return "pdf"
    if (
        head.startswith(b"\x89PNG")
        or head.startswith(b"\xff\xd8\xff")
        or head[:6] in (b"GIF87a", b"GIF89a")
        or head.startswith(b"BM")
        or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
        or head[:4] in (b"II*\x00", b"MM\x00*")
    ):
        return "image"
    lower = name.lower()
    if any(lower.endswith(e) for e in PDF_EXTS):
        return "pdf"
    if any(lower.endswith(e) for e in IMAGE_EXTS):
        return "image"
    return "text"


# --------------------------------------------------------------------------- OCR
_ocr_engine = None


def _get_ocr():
    """Return a callable (numpy image) -> list[str]. Lazy: loads ONNX models once.

    Prefers the current ``rapidocr`` package (Python 3.10-3.14); falls back to the
    legacy ``rapidocr_onnxruntime`` (Python <= 3.12) if that is what is installed.
    """
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr import RapidOCR

            engine = RapidOCR()

            def run(img):
                out = engine(img)
                return list(out.txts or [])

        except ImportError:
            from rapidocr_onnxruntime import RapidOCR  # legacy API

            engine = RapidOCR()

            def run(img):
                result, _ = engine(img)
                return [line[1] for line in (result or [])]

        _ocr_engine = run
    return _ocr_engine


def ocr_image_bytes(data: bytes) -> str:
    """Run OCR on encoded image bytes and return all recognised text."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    # Flatten transparency / palettes to RGB so the OCR model sees real pixels.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")

    return "\n".join(_get_ocr()(np.array(img)))


# --------------------------------------------------------------------------- PDF
def _pdf_text_layer(data: bytes) -> tuple[str, bool]:
    """Return (text, has_images) from the PDF text layer."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:  # noqa: BLE001
            return "", False
    parts, has_images = [], False
    for page in reader.pages:
        parts.append(page.extract_text() or "")
        if not has_images:
            try:
                has_images = len(page.images) > 0
            except Exception:  # noqa: BLE001
                pass
    # Also look at document metadata (title/subject etc.).
    meta = reader.metadata
    if meta:
        parts.extend(str(v) for v in meta.values())
    return "\n".join(parts), has_images


def _pdf_ocr(data: bytes) -> str:
    """Rasterise pages with pdfium and OCR them (for scanned PDFs)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    texts = []
    for i in range(min(len(pdf), config.MAX_OCR_PDF_PAGES)):
        pil = pdf[i].render(scale=2.0).to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        texts.append(ocr_image_bytes(buf.getvalue()))
    return "\n".join(texts)


def extract_pdf_progressive(data: bytes):
    """Yield Extracted chunks cheapest-first so callers can stop at a hit."""
    text, has_images = _pdf_text_layer(data)
    yield Extracted(text)
    # No usable text layer, or pages carry images: the marker may live in pixels.
    if len(text.strip()) < 20 or has_images:
        yield Extracted(_pdf_ocr(data), ocr_used=True)


# ------------------------------------------------------------------------- public
def extract(name: str, data: bytes):
    """Yield Extracted chunks for any supported file (cheapest first)."""
    kind = detect_kind(name, data)
    if kind == "pdf":
        yield from extract_pdf_progressive(data)
    elif kind == "image":
        yield Extracted(ocr_image_bytes(data), ocr_used=True)
    else:
        yield Extracted(data.decode("utf-8", errors="ignore"))
