/**
 * home_i18n.js — language switcher for anonymous visitors (homepage, About page).
 *
 * Unlike the dashboard's switcher (static/js/i18n.js, limited to a signed-in member's own 3
 * languages), an anonymous visitor hasn't picked a mother tongue yet, so every Qumanity-supported
 * language is offered here (static/data/languages.json — all 23). Translation text comes from the
 * SAME static/locales/<code>.json files the dashboard uses; a language with no file yet, or a key
 * missing from one, falls back to the page's own English text -- this is expected for the 11
 * Sub-continent languages not yet translated (see docs/i18n_multilanguage_2026_10.md).
 */
(function () {
  "use strict";

  var KEY = "qm_home_lang";
  var btn = document.getElementById("home-lang-btn"), menu = document.getElementById("home-lang-menu"), wrap = document.getElementById("home-lang-wrap");
  if (!btn || !menu || !wrap) return;

  var current = "en";
  try { current = localStorage.getItem(KEY) || "en"; } catch (e) {}

  var T = {}, cache = {};

  function tr(key, fallback) { return (T && T[key]) || fallback; }

  function applyText() {
    document.documentElement.setAttribute("lang", current);
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"), function (el) {
      if (el.__en === undefined) el.__en = el.textContent;
      el.textContent = tr(el.getAttribute("data-i18n"), el.__en);
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

  function close() { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); }

  fetch("/static/data/languages.json")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var all = ["common", "indian", "subcontinent"].reduce(function (acc, g) { return acc.concat(data[g] || []); }, []);
      all.forEach(function (l) {
        var li = document.createElement("li"), b = document.createElement("button");
        b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("data-code", l.code); b.setAttribute("lang", l.code);
        b.innerHTML = "<span></span><i>✓</i>"; b.firstChild.textContent = l.native + (l.native !== l.name ? " · " + l.name : "");
        b.addEventListener("click", function () {
          current = l.code; try { localStorage.setItem(KEY, current); } catch (e) {}
          close(); loadAndApply();
          Array.prototype.forEach.call(menu.querySelectorAll("button"), function (x) { x.classList.toggle("is-active", x === b); });
        });
        li.appendChild(b); menu.appendChild(li);
      });
      var cur = all.filter(function (l) { return l.code === current; })[0];
      if (cur) Array.prototype.forEach.call(menu.querySelectorAll("button"), function (x) { x.classList.toggle("is-active", x.getAttribute("data-code") === current); });
      loadAndApply();
    })
    .catch(function () { loadAndApply(); });

  btn.addEventListener("click", function (e) {
    e.stopPropagation(); var open = menu.hidden; close();
    if (open) { menu.hidden = false; btn.setAttribute("aria-expanded", "true"); }
  });
  document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) close(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
})();
