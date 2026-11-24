"""Marker detection plus the scan -> confirm -> allow/deny decision flow.

This module is deliberately free of Qt so it can be unit-tested headlessly.
The ``confirm`` callable is injected (the real one shows a native dialog).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional

from core import config, file_extractor

log = logging.getLogger(__name__)

# confirm(kind, name) -> True for Continue, False for Cancel
ConfirmFn = Callable[[str, str], bool]

# OCR commonly confuses these glyphs; fold both sides before comparing.
_FOLD = str.maketrans({"0": "O", "1": "I", "L": "I", "|": "I"})


def _fold(text: str) -> str:
    """Uppercase, drop everything but letters/digits, fold OCR look-alikes."""
    return re.sub(r"[^A-Z0-9|]", "", text.upper()).translate(_FOLD)


_FOLDED_MARKER = _fold(config.SENSITIVE_MARKER)


def contains_marker(text: str, fuzzy: bool = False) -> bool:
    """Exact (case-sensitive) match, or noise-tolerant match for OCR text."""
    if config.SENSITIVE_MARKER in text:
        return True
    return fuzzy and _FOLDED_MARKER in _fold(text)


@dataclass
class ScanResult:
    found: bool
    error: Optional[str] = None


def scan_file(name: str, data: bytes) -> ScanResult:
    """Scan a file's bytes. Never raises: problems are reported in ``error``."""
    # Cheap raw-bytes check first; catches plain text and any format that stores
    # the marker uncompressed.
    if config.SENSITIVE_MARKER.encode() in data:
        return ScanResult(True)
    try:
        for chunk in file_extractor.extract(name, data):
            if contains_marker(chunk.text, fuzzy=chunk.ocr_used):
                return ScanResult(True)
    except Exception as exc:  # noqa: BLE001 - we must not crash the app on bad files
        log.exception("Could not scan %s", name)
        return ScanResult(False, error=f"{type(exc).__name__}: {exc}")
    return ScanResult(False)


def _snippet(text: str, limit: int = 160) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "…"


class InspectionService:
    """Decides whether a prompt/file may proceed. Returns True to allow."""

    def __init__(self, confirm: ConfirmFn):
        self._confirm = confirm

    def review_prompt(self, text: str) -> bool:
        if not contains_marker(text):
            return True
        log.info("Marker found in prompt")
        return self._confirm("prompt", _snippet(text))

    def review_file(self, name: str, data: bytes) -> bool:
        if len(data) > config.MAX_FILE_BYTES:
            log.warning("%s exceeds size limit; not scanned", name)
            return True
        result = scan_file(name, data)
        if result.error:
            log.warning("Scan failed for %s (%s); allowing (fail-open)", name, result.error)
            return True
        if not result.found:
            return True
        log.info("Marker found in file %s", name)
        return self._confirm("file", name)
