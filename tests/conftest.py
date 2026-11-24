import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MARKER = "WALLED_SENSITIVE"


def make_png(text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=56)
    except TypeError:  # very old Pillow
        font = ImageFont.load_default()
    draw.text((30, 60), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_text_pdf(text: str) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 750, text)
    c.save()
    return buf.getvalue()


def make_scanned_pdf(text: str) -> bytes:
    """Image-only PDF (no text layer), like a scan."""
    from PIL import Image

    img = Image.open(io.BytesIO(make_png(text))).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


@pytest.fixture
def marker():
    return MARKER
