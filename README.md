# Walled DLP

A standalone desktop app (Python + PyQt6/QtWebEngine) that acts as a lightweight
Data Loss Prevention layer for **ChatGPT** (chatgpt.com) and **Perplexity**
(perplexity.ai). It scans outgoing prompts and file uploads for the marker
`WALLED_SENSITIVE`, asks for confirmation through a **native desktop dialog**, and
recolours all AI responses.

It is **not** a browser extension: the app embeds its own Chromium (QtWebEngine),
injects scripts into the pages it hosts, and talks to Python over QWebChannel.

## Run

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Two tabs open (ChatGPT, Perplexity). Log in once; the profile is persistent.
Python 3.10+.

## How it works

| Requirement | Mechanism |
|---|---|
| Prompt inspection | `browser/prompt_monitor.js` wraps `window.fetch`. POSTs to the site's send endpoint are held while Python inspects the body. **Continue** forwards the original request untouched; **Cancel** aborts it. |
| File inspection | `browser/file_monitor.js` captures `<input type=file>` changes (incl. off-DOM inputs), drag-and-drop and paste *before the site sees the file*, sends the bytes to Python, then re-dispatches an equivalent event carrying the original `File` objects (Continue / clean) or drops it (Cancel). |
| Text / PDF / image | `core/file_extractor.py`: UTF-8 text; PDF text layer via `pypdf`, with OCR fallback (pdfium render + OCR) for scanned PDFs or PDFs containing images; images via RapidOCR (ONNX, models bundled, no external binary; works on Python 3.10-3.14). File type is sniffed from magic bytes, not just the extension. |
| Native dialog | `ui/confirmation_dialog.py`: `QMessageBox` with **Continue** / **Cancel** buttons. States *prompt* vs *file* and shows the prompt snippet or file name. Cancel is the default/Esc button. |
| Response colour | `browser/response_styler.js` injects a `<style>` using per-site selectors from `core/config.py`. |
| No marker | No dialog, no extra interaction. |

```
main.py                    entry point
app/desktop.py             QApplication, window, tabs, persistent profile, script injection
app/bridge.py              QWebChannel object (JS <-> Python)
browser/*.js               injected scripts (bootstrap, prompt gate, file gate, styler)
core/config.py             marker, colour, endpoints, selectors  <-- edit here if a site changes
core/inspection.py         marker detection + scan/confirm/allow decision (Qt-free)
core/file_extractor.py     text / PDF / image -> text
ui/confirmation_dialog.py  native dialog
tests/                     unit tests + headless end-to-end test
assets/samples/            ready-made files to test with
```

## Testing

```bash
pytest                      # 17 unit tests + 7 headless Chromium end-to-end tests
```

The end-to-end test runs the real injected scripts in headless QtWebEngine against
a local stand-in server (prompt gate, Continue/Cancel/retry, file input, drop,
image OCR, response colour). Only the native dialog is stubbed there.

Manual check on the live sites, using `assets/samples/`:

| Action | Expected |
|---|---|
| Prompt without marker | Sent, no dialog |
| Prompt containing `WALLED_SENSITIVE` | Dialog "…detected in a text prompt" + snippet |
| Upload `sensitive.txt` / `sensitive.pdf` / `sensitive_scanned.pdf` / `sensitive.png` | Dialog "…detected in a file" + file name |
| Upload `clean.*` | No dialog |
| Continue | Prompt sent / file attached unchanged |
| Cancel | Prompt not sent / file not attached; can retry |
| Any AI answer on either site | Text is orange (`RESPONSE_COLOR`) |

## Design decisions and known limits

- **Fail-open.** If the bridge is unavailable, a file cannot be parsed, or a file
  exceeds 40 MB, the action is allowed (and logged) so a monitoring fault never
  breaks the web app. Flip this in `core/inspection.py` / `monitor.js` if you
  prefer fail-closed.
- **Cancel on prompts.** The gate sits on the network request, which is the one
  place that covers Enter, the send button and every other path. On Cancel the
  request is aborted; the site's own UI then handles an aborted send (the typed
  text may remain in the thread rather than the composer; use the site's
  retry/edit). A DOM-level pre-submit guard would keep the composer intact but is
  far more fragile against UI changes.
- **Selectors and endpoints change.** All site-specific values live in
  `core/config.py`. The ChatGPT endpoint (`/backend-api/(f/)?conversation`) and
  selectors (`data-message-author-role="assistant"`) and the Perplexity ones
  (`/rest/sse/perplexity_ask`, `markdown-content-*`, `.prose`) could not be
  verified against the live, login-gated sites while building, so confirm them
  once on the real sites (the `INFO` log shows every dialog that fires) and adjust.
- **Google/Apple SSO** is often refused by embedded browsers. Use email login.
  The UA is set to plain Chrome and popups open in a child window to help.
- **OCR is probabilistic.** Image/scanned-PDF matching is fuzzy (case,
  separators and `l/I/1/0/O` confusions are tolerated) but a very small or noisy
  image can still be missed. Prompts and text files use exact, case-sensitive
  matching.
- Only `fetch` is wrapped for prompts (both sites use it today); `XMLHttpRequest`
  and WebSocket sends are not intercepted.
- Only the PDF's first 10 pages are OCR'd in the fallback (`MAX_OCR_PDF_PAGES`).
