/*
 * monitor.js - bootstrap. Runs first (injected at document creation).
 *
 * Exposes window.__walled with:
 *   cfg            site config for the current host (or null -> everything below is a no-op)
 *   ask(kind, name, payload) -> Promise<boolean>   true = allowed, false = cancelled
 *
 * Python side (QWebChannel object "bridge"):
 *   slot   request(id, kind, name, payload)
 *   signal decision(id, allowed)
 *
 * Fail-open policy: if the bridge never becomes ready the request is allowed,
 * so a monitoring fault can never brick the web app.
 */
(function () {
  "use strict";
  if (window.__walled) return;

  var all = window.__WALLED_CONFIG__ || { sites: {}, timeoutMs: 5000, color: "#E8590C" };
  var host = location.hostname;
  var cfg = null;
  Object.keys(all.sites).forEach(function (suffix) {
    if (host === suffix || host.endsWith("." + suffix)) cfg = all.sites[suffix];
  });

  // var walled = { cfg: cfg, color: all.color, timeoutMs: all.timeoutMs, debug: !!all.debug, bridge: null };
    var walled = { cfg: cfg, color: all.color, timeoutMs: all.timeoutMs, debug: !!all.debug, marker: all.marker || "", bridge: null };
  window.__walled = walled;
  if (walled.debug && window === window.top) {
    // console.log("[walled-dlp] script loaded on " + host + (cfg ? " (monitored: " + cfg.name + ")" : " (not monitored)"));
    console.warn("[walled-dlp] script loaded on " + host + (cfg ? " (monitored: " + cfg.name + ")" : " (not monitored)"));
  }
  if (!cfg) return;

  var pending = {};
  var counter = 0;
  var readyResolve;
  walled.ready = new Promise(function (res) { readyResolve = res; });

  function connect(attempt) {
    if (typeof QWebChannel === "undefined" || typeof qt === "undefined" || !qt.webChannelTransport) {
      if (attempt < 100) setTimeout(function () { connect(attempt + 1); }, 50);
      else console.warn("[walled-dlp] web channel unavailable");
      return;
    }
    new QWebChannel(qt.webChannelTransport, function (channel) {
      walled.bridge = channel.objects.bridge;
      walled.bridge.decision.connect(function (id, allowed) {
        var done = pending[id];
        if (done) { delete pending[id]; done(allowed); }
      });
      readyResolve(true);
    });
  }
  connect(0);

  walled.ask = function (kind, name, payload) {
    return new Promise(function (resolve) {
      var timer = setTimeout(function () {
        console.warn("[walled-dlp] bridge not ready; allowing (fail-open)");
        resolve(true);
      }, walled.timeoutMs);
      walled.ready.then(function () {
        clearTimeout(timer); // dialog time must not count against the timeout
        var id = "r" + (++counter) + "_" + Date.now();
        pending[id] = resolve;
        walled.bridge.request(id, kind, name, payload);
      });
    });
  };
})();