/**
 * i18n.js — dashboard language switcher.
 *
 * A user keeps at most 3 languages: mother tongue, English, and an optional daily-use one
 * (QM_LANGS, from the server). The dot in the top bar switches the dashboard text between them.
 * Text tables live one-per-language in static/locales/<code>.json (see scripts/build_ui_locales.py)
 * -- fetched on demand, not bundled all at once -- keyed by data-i18n; a language with no file yet,
 * or a key missing from it, falls back to the page's own English text.
 *
 * The PREFERRED language (server-persisted, profile.preferred_language / QM_PREFERRED_LANG) wins
 * on first load over the old localStorage-only choice, so it follows the member across devices;
 * picking a different language here still updates localStorage for this browser immediately, and
 * saves it as the new preferred language server-side (see the Private tab's language-preference
 * picker, api/user/languages POST {preferred}).
 */
(function () {
  "use strict";

  var KEY = "qm_ui_lang";
  var langs = window.QM_LANGS || [];
  var btn = document.getElementById("ui-lang-btn"), menu = document.getElementById("ui-lang-menu"), wrap = document.getElementById("ui-lang-wrap");
  var current = "en";
  var preferred = window.QM_PREFERRED_LANG || "";
  try { current = preferred || localStorage.getItem(KEY) || "en"; } catch (e) { current = preferred || "en"; }
  if (!langs.some(function (l) { return l.code === current; })) current = "en";

  var T = {}; // current language's table, once fetched
  var cache = {};

  function tr(key, fallback) { return (T && T[key]) || fallback; }
  window.qmTr = tr;

  function applyText() {
    document.documentElement.setAttribute("lang", current);
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"), function (el) {
      if (el.__en === undefined) el.__en = el.textContent;
      el.textContent = tr(el.getAttribute("data-i18n"), el.__en);
    });
    var cur = langs.filter(function (l) { return l.code === current; })[0];
    if (btn) btn.textContent = cur ? cur.native : "English";
    if (menu) Array.prototype.forEach.call(menu.querySelectorAll("button"), function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-code") === current);
    });
    document.dispatchEvent(new CustomEvent("qm-lang", { detail: current }));
  }

  function loadAndApply() {
    if (current === "en") { T = {}; applyText(); return; }
    if (cache[current]) { T = cache[current]; applyText(); return; }
    fetch("/static/locales/" + current + ".json")
      .then(function (r) { if (!r.ok) throw new Error("no locale file"); return r.json(); })
      .then(function (data) { cache[current] = data; T = data; applyText(); })
      .catch(function () { T = {}; applyText(); });
  }

  if (langs.length) {
    langs.forEach(function (l) {
      var li = document.createElement("li"), b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("data-code", l.code); b.setAttribute("lang", l.code);
      b.innerHTML = "<span></span><i>✓</i>"; b.firstChild.textContent = l.native + (l.native !== l.name ? " · " + l.name : "");
      b.addEventListener("click", function () {
        current = l.code;
        try { localStorage.setItem(KEY, current); } catch (e) {}
        close(); loadAndApply();
        fetch("/api/user/languages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preferred: current }) }).catch(function () {});
      });
      li.appendChild(b); menu.appendChild(li);
    });
    function close() { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); }
    btn.addEventListener("click", function (e) {
      e.stopPropagation(); var open = menu.hidden; close();
      if (open) { menu.hidden = false; btn.setAttribute("aria-expanded", "true"); }
    });
    document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) close(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  }
  loadAndApply();
})();
