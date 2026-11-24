/*
 * response_styler.js - recolour all AI-generated response text.
 *
 * A single <style> element with the site's response selectors is injected and
 * kept alive (both sites are SPAs that re-render heavily). CSS applies to
 * responses that are added later, so no per-message DOM work is needed.
 *
 * This runs at document creation, when <html> and <head> may not exist yet,
 * so every step tolerates missing parents and retries as the DOM appears.
 */
(function () {
  "use strict";
  var w = window.__walled;
  if (!w || !w.cfg) return;

  var ID = "walled-dlp-response-style";
  var css = w.cfg.response_selectors
    .map(function (sel) { return sel + " { color: " + w.color + " !important; }"; })
    .join("\n");
  
  // Preferred: a constructable stylesheet. Unlike a <style> element it is not
  // subject to the page's Content-Security-Policy (style-src).
  var adopted = false;
  try {
    var sheet = new CSSStyleSheet();
    sheet.replaceSync(css);
    document.adoptedStyleSheets = document.adoptedStyleSheets.concat([sheet]);
    adopted = true;
  } catch (e) { /* unsupported: fall back to a <style> element below */ }

  function ensure() {
    if (adopted) return;
    var parent = document.head || document.documentElement;
    if (!parent || document.getElementById(ID)) return;
    var el = document.createElement("style");
    el.id = ID;
    el.textContent = css;
    parent.appendChild(el);
  }

  // Cheap guards: watch only direct children of <document>/<html>/<head>
  // (never the whole subtree), so streaming responses cost nothing.
  var watched = [];
  function watch(node) {
    if (!node || watched.indexOf(node) !== -1) return;
    watched.push(node);
    mo.observe(node, { childList: true });
  }
  var mo = new MutationObserver(function () {
    ensure();
    watch(document.documentElement);
    watch(document.head);
  });

  ensure();
  watch(document);
  watch(document.documentElement);
  watch(document.head);
  document.addEventListener("DOMContentLoaded", function () {
    ensure();
    watch(document.documentElement);
    watch(document.head);
  });
})();
