/**
 * founders_message_i18n.js — language switcher for the Founder's Message page.
 *
 * Unlike home_i18n.js (which swaps small [data-i18n] strings client-side), this page's whole
 * letter is server-rendered from founder_core.get_message(conn, lang) -- see /founders-message's
 * ?lang= query param -- so switching language here means a real navigation, not a text swap.
 * Shares the SAME localStorage key (qm_home_lang) the homepage picker uses, so a language picked
 * on either page carries over to the other.
 */
(function () {
  "use strict";

  var KEY = "qm_home_lang";
  var btn = document.getElementById("home-lang-btn"), menu = document.getElementById("home-lang-menu"), wrap = document.getElementById("home-lang-wrap");
  if (!btn || !menu || !wrap) return;

  var params = new URLSearchParams(window.location.search);
  var current = params.get("lang") || "en";

  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  // No explicit ?lang= on this visit, but a language was already picked elsewhere (e.g. the
  // homepage) -- follow it once, so a returning reader doesn't have to repick it here.
  if (!params.get("lang") && saved && saved !== "en") {
    window.location.replace("?lang=" + encodeURIComponent(saved));
    return;
  }

  function close() { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); }

  function goTo(code) {
    try { localStorage.setItem(KEY, code); } catch (e) {}
    var url = new URL(window.location.href);
    if (code === "en") url.searchParams.delete("lang"); else url.searchParams.set("lang", code);
    window.location.href = url.toString();
  }

  fetch("/static/data/languages.json")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var all = ["common", "indian", "subcontinent"].reduce(function (acc, g) { return acc.concat(data[g] || []); }, []);
      all.forEach(function (l) {
        var li = document.createElement("li"), b = document.createElement("button");
        b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("data-code", l.code); b.setAttribute("lang", l.code);
        b.innerHTML = "<span></span><i>✓</i>"; b.firstChild.textContent = l.native + (l.native !== l.name ? " · " + l.name : "");
        if (l.code === current) b.classList.add("is-active");
        b.addEventListener("click", function () { close(); goTo(l.code); });
        li.appendChild(b); menu.appendChild(li);
      });
    });

  btn.addEventListener("click", function (e) {
    e.stopPropagation(); var open = menu.hidden; close();
    if (open) { menu.hidden = false; btn.setAttribute("aria-expanded", "true"); }
  });
  document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) close(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
})();
