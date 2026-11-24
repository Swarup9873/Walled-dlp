/*
 * composer_monitor.js - gate prompts at the text box (second layer).
 *
 * Some sites send prompts in a way window.fetch cannot see (e.g. from a worker).
 * This layer does not care how the request travels: when the user presses Enter
 * in the composer or clicks the send button AND the text contains the marker,
 * the action is held while Python shows the dialog.
 *   Cancel   -> nothing happens, the text stays in the box (edit and retry).
 *   Continue -> the send button is clicked again with a pass flag, so the site
 *               receives a completely normal send.
 * Clean prompts are never touched: no marker means the event is not intercepted.
 *
 * Only active for sites whose config has a "composer" entry.
 */
(function () {
  "use strict";
  var w = window.__walled;
  if (!w || !w.cfg || !w.cfg.composer || !w.marker) return;

  var inputSel = w.cfg.composer.input;
  var sendSel = w.cfg.composer.send;
  var passing = false;   // true while we replay an approved send
  var busy = false;      // true while the dialog is open

  function textOf(el) {
    if (typeof el.value === "string" && el.value) return el.value;
    return el.innerText || el.textContent || "";
  }

  function composerFor(target) {
    if (!target || !target.closest) return null;
    return target.closest(inputSel) ||
      target.closest('[role="textbox"][contenteditable="true"], textarea');
  }

  function activeComposer() {
    return document.querySelector(inputSel) ||
      document.querySelector('[role="textbox"][contenteditable="true"], textarea');
  }

  function swallow(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
  }

  // Returns true if the event was intercepted.
  function gate(e, composer, resume) {
    var text = textOf(composer);
    if (text.indexOf(w.marker) === -1) return false;   // clean: native behaviour
    swallow(e);
    if (busy) return true;
    busy = true;
    if (w.debug) console.warn("[walled-dlp] composer: marker found, asking user");
    w.ask("prompt", "", text).then(function (ok) {
      busy = false;
      if (!ok) return;                                  // Cancel: text stays in the box
      w.approvedAt = Date.now();                        // tells the fetch gate not to ask twice
      passing = true;
      try { resume(); } finally { passing = false; }
    });
    return true;
  }

  document.addEventListener("keydown", function (e) {
    if (passing || e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    var composer = composerFor(e.target);
    if (!composer) return;
    gate(e, composer, function () {
      var btn = document.querySelector(sendSel);
      if (btn) { btn.click(); return; }
      composer.dispatchEvent(new KeyboardEvent("keydown", {
        key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true
      }));
    });
  }, true);

  document.addEventListener("click", function (e) {
    if (passing) return;
    var btn = e.target && e.target.closest ? e.target.closest(sendSel) : null;
    if (!btn) return;
    var composer = activeComposer();
    if (!composer) return;
    gate(e, composer, function () { btn.click(); });
  }, true);
})();