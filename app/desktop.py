"""Desktop shell: a PyQt6 window with one embedded-Chromium tab per site.

QtWebEngine *is* Chromium, so this is a normal standalone desktop app (no
browser extension involved). Our JavaScript is injected into the page's main
world at document creation and talks to Python over QWebChannel.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, QFile, QIODevice, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget

from app.bridge import Bridge
from core import config
from core.inspection import InspectionService
from ui.confirmation_dialog import confirm_sensitive

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
BROWSER_DIR = ROOT / "browser"
# Order matters: bootstrap first, then the feature modules.
JS_MODULES = ["monitor.js", "prompt_monitor.js", "composer_monitor.js", "file_monitor.js", "response_styler.js"]


def _read_qwebchannel_js() -> str:
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if not f.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError("qwebchannel.js not found in Qt resources")
    try:
        return bytes(f.readAll()).decode("utf-8")
    finally:
        f.close()


def build_injected_source() -> str:
    """qwebchannel.js + config + our modules, as one script (shared scope-free IIFEs)."""
    cfg = {
        "sites": config.SITES,
        "timeoutMs": config.BRIDGE_TIMEOUT_MS,
        "color": config.RESPONSE_COLOR,
        "debug": config.DEBUG_LOG_REQUESTS, 
        "marker": config.SENSITIVE_MARKER,
    }
    parts = [
        # Wrapped so qwebchannel's top-level names never leak into the page.
        "(function(){" + _read_qwebchannel_js() + "\nwindow.QWebChannel = QWebChannel;})();",
        "window.__WALLED_CONFIG__ = " + json.dumps(cfg) + ";",
    ]
    parts += [(BROWSER_DIR / name).read_text(encoding="utf-8") for name in JS_MODULES]
    return "\n;\n".join(parts)


def make_profile(parent) -> QWebEngineProfile:
    """Persistent profile (logins survive restarts) with our script injected."""
    profile = QWebEngineProfile("walled-dlp", parent)
    # Present as plain Chrome; the default UA advertises "QtWebEngine/x.y".
    profile.setHttpUserAgent(re.sub(r"\s*QtWebEngine/\S+", "", profile.httpUserAgent()))

    script = QWebEngineScript()
    script.setName("walled-dlp")
    script.setSourceCode(build_injected_source())
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)  # needed to wrap page fetch
    script.setRunsOnSubFrames(False)
    profile.scripts().insert(script)
    return profile


class SitePage(QWebEnginePage):
    """Page wired to the bridge; opens window.open() popups (e.g. SSO) in a child window."""

    def __init__(self, profile, bridge: Bridge, parent=None):
        super().__init__(profile, parent)
        self._bridge = bridge
        self._popups: list[QWebEngineView] = []
        channel = QWebChannel(self)
        channel.registerObject("bridge", bridge)
        self.setWebChannel(channel, QWebEngineScript.ScriptWorldId.MainWorld)

    def createWindow(self, _type):  # noqa: N802 (Qt naming)
        view = QWebEngineView()
        page = SitePage(self.profile(), self._bridge, view)
        view.setPage(page)
        view.resize(520, 700)
        view.show()
        self._popups.append(view)
        page.windowCloseRequested.connect(view.close)
        return page


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Walled DLP - ChatGPT & Perplexity")
        self.resize(1280, 860)
        icon = ROOT / "assets" / "icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        service = InspectionService(lambda kind, name: confirm_sensitive(kind, name, self))
        self._bridge = Bridge(service, self)
        self._profile = make_profile(self)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        self._views: list[QWebEngineView] = []
        for title, url in config.START_URLS.items():
            view = QWebEngineView()
            view.setPage(SitePage(self._profile, self._bridge, view))
            view.load(QUrl(url))
            tabs.addTab(view, title)
            self._views.append(view)

    def closeEvent(self, event):  # noqa: N802 (Qt naming)
        # Pages must be destroyed before their profile, or Qt warns on exit.
        for view in self._views:
            view.page().deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        super().closeEvent(event)


def run() -> int:
    # Chromium needs a real argv[0]; an empty list aborts at startup.
    app = QApplication.instance() or QApplication(sys.argv or ["walled-dlp"])
    app.setApplicationName("walled-dlp")
    window = MainWindow()
    window.show()
    return app.exec()
