"""End-to-end test: real Chromium (QtWebEngine, headless) + injected JS + bridge.

A tiny local HTTP server stands in for ChatGPT. The site config is pointed at
127.0.0.1 so the production scripts run unchanged. Only the native dialog is
replaced by a scripted stub.
"""

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

pytest.importorskip("PyQt6.QtWebEngineWidgets")

from PyQt6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PyQt6.QtWebChannel import QWebChannel  # noqa: E402
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import desktop  # noqa: E402
from app.bridge import Bridge  # noqa: E402
from core import config  # noqa: E402
from core.inspection import InspectionService  # noqa: E402

PAGE = """<!doctype html><html><head><title>t</title></head><body>
<input type="file" id="f">
<div id="drop" style="width:100px;height:100px">drop</div>
<div id="prompt-composer" role="textbox" contenteditable="true"></div>
<button data-testid="send-button">Send</button>
<div data-message-author-role="assistant" id="ans">Hello <span id="inner">world</span></div>
<script>
window.hits = []; window.files = []; window.dropped = [];
document.querySelector('[data-testid="send-button"]').addEventListener('click', function () {
  var text = document.getElementById('prompt-composer').innerText;
  window.composerSendResult = null;
  fetch('/ui-send', {method: 'POST', body: JSON.stringify({messages: [{content: {parts: [text]}}]})})
    .then(function (r) { window.composerSendResult = 'ok:' + r.status; });
});
document.getElementById('f').addEventListener('change', function (e) {
  window.files = Array.from(e.target.files).map(function (f) { return f.name; });
});
document.getElementById('drop').addEventListener('drop', function (e) {
  e.preventDefault(); window.dropped = Array.from(e.dataTransfer.files).map(function (f) { return f.name; });
});
function send(text) {
  window.sendResult = null;
  var body = JSON.stringify({messages: [{content: {parts: [text]}}]});
  fetch('/backend-api/conversation', {method: 'POST', body: body, headers: {'content-type': 'application/json'}})
    .then(function (r) { window.sendResult = 'ok:' + r.status; })
    .catch(function (e) { window.sendResult = 'err:' + e.name; });
}
function pick(name, content) {
  window.files = [];
  var dt = new DataTransfer(); dt.items.add(new File([content], name, {type: 'text/plain'}));
  var inp = document.getElementById('f'); inp.files = dt.files;
  inp.dispatchEvent(new Event('change', {bubbles: true}));
}
function dropFile(name, content) {
  window.dropped = [];
  var dt = new DataTransfer(); dt.items.add(new File([content], name, {type: 'text/plain'}));
  document.getElementById('drop').dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE.encode())

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        Handler.hits.append(json.loads(self.rfile.read(n)))
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["walled-dlp-test"])


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


class Harness:
    def __init__(self, qapp, server, monkeypatch):
        self.answers = []   # scripted dialog answers
        self.dialogs = []   # (kind, name) shown

        def confirm(kind, name):
            self.dialogs.append((kind, name))
            return self.answers.pop(0)

        monkeypatch.setattr(
            config, "SITES",
            {"127.0.0.1": {
                "name": "Local",
                "send_paths": [r"^/backend-api/conversation$"],
                "composer": {
                    "input": "#prompt-textarea",
                    "send": "button[data-testid='send-button']",
                },
                "response_selectors": ['[data-message-author-role="assistant"]',
                                       '[data-message-author-role="assistant"] *'],
            }},
        )
        self.bridge = Bridge(InspectionService(confirm))
        self.profile = QWebEngineProfile(qapp)  # off-the-record
        from PyQt6.QtWebEngineCore import QWebEngineScript
        s = QWebEngineScript()
        s.setName("walled")
        s.setSourceCode(desktop.build_injected_source())
        s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self.profile.scripts().insert(s)
        self.page = QWebEnginePage(self.profile)
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.page.setWebChannel(self.channel, QWebEngineScript.ScriptWorldId.MainWorld)
        loop = QEventLoop()
        self.page.loadFinished.connect(lambda ok: loop.quit())
        self.page.load(QUrl(f"http://127.0.0.1:{server.server_port}/"))
        QTimer.singleShot(20000, loop.quit)
        loop.exec()

    def js(self, code, timeout=100):
        out = {}
        loop = QEventLoop()
        self.page.runJavaScript(code, lambda v: (out.setdefault("v", v), loop.quit()))
        QTimer.singleShot(timeout * 100, loop.quit)
        loop.exec()
        return out.get("v")

    def wait_for(self, expr, timeout=15):
        import time
        end = time.time() + timeout
        while time.time() < end:
            v = self.js(expr)
            if v not in (None, False, ""):
                return v
            loop = QEventLoop()
            QTimer.singleShot(50, loop.quit)
            loop.exec()
        return None


@pytest.fixture
def h(qapp, server, monkeypatch):
    Handler.hits.clear()
    hn = Harness(qapp, server, monkeypatch)
    # wait until the bridge is connected in the page
    hn.wait_for("window.__walled && window.__walled.bridge ? true : null")
    return hn


def test_bridge_connects_and_color_applied(h):
    assert h.js("!!window.__walled.bridge") is True
    h.wait_for("document.adoptedStyleSheets.length ? true : null")
    color = h.js("getComputedStyle(document.getElementById('inner')).color")
    assert color == "rgb(232, 89, 12)", color          # #E8590C on a *descendant* of the response
    assert h.js("getComputedStyle(document.getElementById('ans')).color") == "rgb(232, 89, 12)"


def test_clean_prompt_passes_without_dialog(h):
    h.js("send('what is 2+2?')")
    assert h.wait_for("window.sendResult") == "ok:200"
    assert h.dialogs == []
    assert len(Handler.hits) == 1


def test_marker_prompt_continue(h):
    h.answers = [True]
    h.js("send('here is WALLED_SENSITIVE data')")
    assert h.wait_for("window.sendResult") == "ok:200"
    assert h.dialogs[0][0] == "prompt" and "WALLED_SENSITIVE" in h.dialogs[0][1]
    assert Handler.hits[0]["messages"][0]["content"]["parts"][0] == "here is WALLED_SENSITIVE data"  # untouched


def test_marker_prompt_cancel_blocks_request(h):
    h.answers = [False]
    h.js("send('WALLED_SENSITIVE secret')")
    assert h.wait_for("window.sendResult") == "err:AbortError"
    assert Handler.hits == []
    # retry works normally
    h.answers = [True]
    h.js("send('WALLED_SENSITIVE secret')")
    assert h.wait_for("window.sendResult") == "ok:200"


def test_composer_fallback_gates_contenteditable_prompt(h):
    h.answers = [True]
    h.js("""(function () {
      document.getElementById('prompt-composer').textContent = 'WALLED_SENSITIVE from composer';
      document.querySelector('[data-testid="send-button"]').click();
    })()""")
    assert h.wait_for("window.composerSendResult") == "ok:200"
    assert h.dialogs == [("prompt", "WALLED_SENSITIVE from composer")]
    assert Handler.hits[0]["messages"][0]["content"]["parts"][0] == "WALLED_SENSITIVE from composer"


def test_file_input_clean_marker_continue_cancel(h):
    h.js("pick('clean.txt', 'nothing')")
    assert h.wait_for("window.files.length ? window.files.join() : null") == "clean.txt"
    assert h.dialogs == []

    h.answers = [True]
    h.js("pick('secret.txt', 'x WALLED_SENSITIVE y')")
    assert h.wait_for("window.files.length ? window.files.join() : null") == "secret.txt"
    assert h.dialogs == [("file", "secret.txt")]

    h.answers = [False]
    h.js("pick('secret2.txt', 'WALLED_SENSITIVE')")
    h.wait_for("document.getElementById('f').value === '' ? true : null")
    loop = QEventLoop(); QTimer.singleShot(500, loop.quit); loop.exec()
    assert h.js("window.files.length") == 0        # site never saw it
    assert h.js("document.getElementById('f').files.length") == 0


def test_drop_marker_file(h):
    h.answers = [True]
    h.js("dropFile('d.txt', 'WALLED_SENSITIVE')")
    assert h.wait_for("window.dropped.length ? window.dropped.join() : null") == "d.txt"
    h.answers = [False]
    h.js("dropFile('e.txt', 'WALLED_SENSITIVE')")
    loop = QEventLoop(); QTimer.singleShot(800, loop.quit); loop.exec()
    assert h.js("window.dropped.length") == 0


def test_image_upload_triggers_dialog(h):
    from tests.conftest import make_png
    b64 = base64.b64encode(make_png("WALLED_SENSITIVE")).decode()
    h.answers = [True]
    h.js(f"""(function(){{
      var b = Uint8Array.from(atob('{b64}'), function(c){{return c.charCodeAt(0)}});
      window.files = [];
      var dt = new DataTransfer(); dt.items.add(new File([b], 'shot.png', {{type:'image/png'}}));
      var inp = document.getElementById('f'); inp.files = dt.files;
      inp.dispatchEvent(new Event('change', {{bubbles:true}}));
    }})()""")
    assert h.wait_for("window.files.length ? window.files.join() : null", timeout=60) == "shot.png"
    assert h.dialogs == [("file", "shot.png")]
