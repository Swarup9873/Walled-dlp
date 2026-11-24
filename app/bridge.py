"""QWebChannel object exposed to the page as ``bridge``.

JS calls ``request(id, kind, name, payload)``; the answer comes back later via
the ``decision(id, allowed)`` signal. The work is deferred with a zero-timer so
the (modal) dialog never runs inside the channel call itself.
"""

from __future__ import annotations

import base64
import logging

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from core.inspection import InspectionService

log = logging.getLogger(__name__)


class Bridge(QObject):
    decision = pyqtSignal(str, bool)

    def __init__(self, service: InspectionService, parent=None):
        super().__init__(parent)
        self._service = service

    @pyqtSlot(str, str, str, str)
    def request(self, req_id: str, kind: str, name: str, payload: str) -> None:
        QTimer.singleShot(0, lambda: self._handle(req_id, kind, name, payload))

    def _handle(self, req_id: str, kind: str, name: str, payload: str) -> None:
        try:
            if kind == "prompt":
                allowed = self._service.review_prompt(payload)
            elif kind == "file":
                allowed = self._service.review_file(name, base64.b64decode(payload))
            else:
                log.warning("Unknown request kind %r; allowing", kind)
                allowed = True
        except Exception:  # noqa: BLE001 - never leave the page hanging
            log.exception("Inspection failed; allowing (fail-open)")
            allowed = True
        self.decision.emit(req_id, allowed)
