/*
 * file_monitor.js - gate file uploads before the site ever sees the file.
 *
 * Covers: <input type=file> (attached or created off-DOM), drag & drop, paste.
 * Strategy: capture the event first, stop it, ask Python to scan, then either
 *   - re-dispatch an equivalent event carrying the ORIGINAL File objects
 *     (Continue / clean), or
 *   - drop it (Cancel). The user can simply pick the file again.
 * Re-dispatched events carry __walledPass so they are not scanned twice.
 */
(function () {
  "use strict";
  var w = window.__walled;
  if (!w || !w.cfg) return;

  var MAX = 40 * 1024 * 1024;

  function toBase64(buf) {
    var bytes = new Uint8Array(buf), chunk = 0x8000, out = "";
    for (var i = 0; i < bytes.length; i += chunk) {
      out += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(out);
  }

  // Returns the subset of `files` the user allowed (clean ones + Continue'd ones).
  async function review(files) {
    var allowed = [];
    for (var i = 0; i < files.length; i++) {
      var f = files[i], ok = true;
      if (f.size <= MAX) {
        try {
          ok = await w.ask("file", f.name, toBase64(await f.arrayBuffer()));
        } catch (e) {
          console.warn("[walled-dlp] could not read file; allowing", e);
        }
      }
      if (ok) allowed.push(f);
    }
    return allowed;
  }

  function toFileList(files) {
    var dt = new DataTransfer();
    files.forEach(function (f) { dt.items.add(f); });
    return dt;
  }

  // ---- <input type=file> -------------------------------------------------
  function onInputChange(e) {
    if (e.__walledPass) return;
    var input = e.target;
    if (!input || input.type !== "file" || !input.files || !input.files.length) return;
    e.stopImmediatePropagation();
    var picked = Array.prototype.slice.call(input.files);
    review(picked).then(function (allowed) {
      if (!allowed.length) { input.value = ""; return; }            // Cancel: nothing selected
      if (allowed.length !== picked.length) input.files = toFileList(allowed).files;
      var ev = new Event("change", { bubbles: true });
      ev.__walledPass = true;
      input.dispatchEvent(ev);
    });
  }

  // Inputs already in the DOM (bubbling reaches document in the capture phase).
  document.addEventListener("change", onInputChange, true);

  // Inputs created off-DOM never bubble to document, so hook them when opened.
  var origClick = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function () {
    if (this.type === "file" && !this.__walledHooked) {
      this.__walledHooked = true;
      this.addEventListener("change", onInputChange, true);
    }
    return origClick.apply(this, arguments);
  };

  // ---- drag & drop -------------------------------------------------------
  document.addEventListener("drop", function (e) {
    if (e.__walledPass) return;
    var dt = e.dataTransfer;
    if (!dt || !dt.files || !dt.files.length) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    var target = e.target, init = { bubbles: true, cancelable: true, clientX: e.clientX, clientY: e.clientY };
    review(Array.prototype.slice.call(dt.files)).then(function (allowed) {
      if (!allowed.length) return;                                  // Cancel
      init.dataTransfer = toFileList(allowed);
      var ev = new DragEvent("drop", init);
      ev.__walledPass = true;
      target.dispatchEvent(ev);
    });
  }, true);

  // ---- paste (e.g. pasted screenshots) ------------------------------------
  document.addEventListener("paste", function (e) {
    if (e.__walledPass) return;
    var cd = e.clipboardData;
    if (!cd || !cd.files || !cd.files.length) return;               // plain text paste: untouched
    e.preventDefault();
    e.stopImmediatePropagation();
    var target = e.target;
    review(Array.prototype.slice.call(cd.files)).then(function (allowed) {
      if (!allowed.length) return;                                  // Cancel
      var ev = new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: toFileList(allowed) });
      ev.__walledPass = true;
      target.dispatchEvent(ev);
    });
  }, true);
})();
