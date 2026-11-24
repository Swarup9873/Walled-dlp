/*
 * prompt_monitor.js - gate outgoing prompts.
 *
 * Wraps window.fetch. When the site POSTs to one of its "send" endpoints,
 * the request is held while Python inspects the body. The original request is
 * passed through byte-for-byte on Continue; on Cancel it is aborted.
 */
(function () {
  "use strict";
  var w = window.__walled;
  if (!w || !w.cfg) return;

  var sendRes = w.cfg.send_paths.map(function (p) { return new RegExp(p); });
  var origFetch = window.fetch;

  function isSend(url, method) {
    if (String(method || "GET").toUpperCase() !== "POST") return false;
    try {
      var path = new URL(url, location.href).pathname;
      return sendRes.some(function (re) { return re.test(path); });
    } catch (e) { return false; }
  }

  // Pull the human-readable prompt out of the request JSON (best effort).
  function promptText(raw) {
    try {
      var j = JSON.parse(raw);
      var parts = [];
      if (Array.isArray(j.messages)) {              // ChatGPT
        j.messages.forEach(function (m) {
          var p = m && m.content && m.content.parts;
          if (Array.isArray(p)) p.forEach(function (x) { if (typeof x === "string") parts.push(x); });
        });
      }
      if (typeof j.query_str === "string") parts.push(j.query_str);   // Perplexity
      if (parts.length) return parts.join("\n");
    } catch (e) { /* not JSON: fall through */ }
    return raw;
  }

  // Read any re-readable fetch body as text. Returns null for one-shot streams.
  function bodyToText(b) {
    if (typeof b === "string") return Promise.resolve(b);
    if (typeof Blob !== "undefined" && b instanceof Blob) return b.text();
    if (b instanceof ArrayBuffer || ArrayBuffer.isView(b)) return Promise.resolve(new TextDecoder().decode(b));
    if (typeof URLSearchParams !== "undefined" && b instanceof URLSearchParams) return Promise.resolve(b.toString());
    if (typeof FormData !== "undefined" && b instanceof FormData) {
      return Promise.resolve(Array.from(b.entries())
        .map(function (e) { return typeof e[1] === "string" ? e[1] : ""; }).join("\n"));
    }
    return null;   // ReadableStream etc.: cannot be read without consuming it
  }

  // Normalise (input, init) into { url, method, bodyPromise }.
  function describe(input, init) {
    var isReq = typeof Request !== "undefined" && input instanceof Request;
    var url = isReq ? input.url : String(input);
    var method = (init && init.method) || (isReq ? input.method : "GET");
    var body;
    if (init && init.body !== undefined && init.body !== null) {
      body = bodyToText(init.body);
    } else if (isReq) {
      body = input.clone().text();   // clone so the real request body stays unread
    }
    return { url: url, method: method, body: body };
  }

  window.fetch = function (input, init) {
    var d;
    try { d = describe(input, init); } catch (e) { return origFetch.apply(this, arguments); }
    if (w.debug && String(d.method).toUpperCase() === "POST") {
      try {
        console.warn("[walled-dlp] POST " + new URL(d.url, location.href).pathname +
          " (send=" + isSend(d.url, d.method) + ")");
      } catch (e) { /* ignore */ }
    }
    if (isSend(d.url, d.method) && !d.body) {
      console.warn("[walled-dlp] send request has an unreadable body (stream?); NOT inspected");
    }
    if (!isSend(d.url, d.method) || !d.body) return origFetch.apply(this, arguments);

    // Already approved by the composer gate a moment ago: do not ask twice.
    if (w.approvedAt && Date.now() - w.approvedAt < 10000) {
      w.approvedAt = 0;
      return origFetch.apply(this, arguments);
    }
    
    var self = this, args = arguments;
    return d.body.then(function (raw) {
      return w.ask("prompt", "", promptText(raw));
    }).then(function (allowed) {
      if (!allowed) throw new DOMException("Cancelled by Walled DLP", "AbortError");
      return origFetch.apply(self, args);
    });
  };
})();