"""Single source of truth for everything that is site-specific or tunable.

Selectors and endpoints on third-party web apps change over time. When
something stops working, this is the only file that should need editing.
The ``SITES`` dict is serialised to JSON and handed to the injected
JavaScript, so Python and JS always agree.
"""

from __future__ import annotations

SENSITIVE_MARKER = "WALLED_SENSITIVE"

# Colour applied to every AI-generated response (works on light and dark themes).
RESPONSE_COLOR = "#E8590C"

# Files larger than this are not scanned in the browser->Python hand-off.
MAX_FILE_BYTES = 40 * 1024 * 1024

# OCR fallback for PDFs: render at most this many pages.
MAX_OCR_PDF_PAGES = 10

# If the bridge is not ready after this long, the page is allowed to proceed
# (fail-open) so that a monitoring fault never bricks the web app.
BRIDGE_TIMEOUT_MS = 5000

# When True, every POST made by the page is printed to the terminal as
# "[walled-dlp] POST /path (send=true|false)". Use it to find the right
# endpoint if a prompt is not being intercepted; set False when done.
DEBUG_LOG_REQUESTS = True

START_URLS = {
    "ChatGPT": "https://chatgpt.com",
    "Perplexity": "https://www.perplexity.ai",
}

SITES = {
    "chatgpt.com": {
        "name": "ChatGPT",
        # backend-api = logged-in; backend-anon / unauth-mweb = logged-out.
        # "$" keeps helper calls such as .../conversation/prepare from matching.
        "send_paths": [r"^/(backend-api|backend-anon|unauth-mweb)/(f/)?conversation$"],
        # Second gate at the text box (works even if the network call is invisible to fetch).
        "composer": {
            "input": "#prompt-textarea",
            "send": "button[data-testid='send-button']",
        },
        # CSS selectors for AI-generated response content.
        "response_selectors": [
            '[data-message-author-role="assistant"]',
            '[data-message-author-role="assistant"] *',
        ],
    },
    "perplexity.ai": {
        "name": "Perplexity",
        "send_paths": [r"^/rest/sse/perplexity_ask$"],
        "response_selectors": [
            '[id^="markdown-content-"]',
            '[id^="markdown-content-"] *',
            ".prose",
            ".prose *",
        ],
    },
}
