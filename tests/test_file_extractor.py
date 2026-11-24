import pytest

from core.inspection import scan_file
from tests.conftest import MARKER, make_png, make_scanned_pdf, make_text_pdf


def test_text_file_with_marker():
    assert scan_file("a.txt", f"line1\n{MARKER}\n".encode()).found


def test_text_file_csv_marker():
    assert scan_file("b.csv", f"id,note\n1,{MARKER}\n".encode()).found


def test_clean_text_file():
    assert not scan_file("a.txt", b"hello").found


def test_text_pdf_with_marker():
    assert scan_file("doc.pdf", make_text_pdf(f"Report {MARKER} end")).found


def test_clean_text_pdf():
    assert not scan_file("doc.pdf", make_text_pdf("Quarterly report, nothing secret")).found


def test_scanned_pdf_with_marker_needs_ocr():
    assert scan_file("scan.pdf", make_scanned_pdf(MARKER)).found


def test_image_with_marker():
    assert scan_file("shot.png", make_png(MARKER)).found


def test_clean_image():
    assert not scan_file("shot.png", make_png("HELLO WORLD")).found


def test_image_detected_by_content_not_extension():
    assert scan_file("renamed.dat", make_png(MARKER)).found
