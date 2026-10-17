/**
 * home.js — homepage behaviour: mobile menu, tabs, count-up numbers, scroll reveals.
 * The globe and live statistics are handled by earth.js.
 */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- Mobile menu ----
  var burger = document.getElementById("hm-burger");
  var menu = document.getElementById("hm-links");
  burger.addEventListener("click", function () {
    var open = menu.classList.toggle("is-open");
    burger.setAttribute("aria-expanded", open ? "true" : "false");
  });
  menu.addEventListener("click", function (e) {
    if (e.target.tagName === "A") { menu.classList.remove("is-open"); burger.setAttribute("aria-expanded", "false"); }
  });

  // ---- Tabs (every [data-tabs] group) ----
  Array.prototype.forEach.call(document.querySelectorAll("[data-tabs]"), function (group) {
    var buttons = Array.prototype.slice.call(group.querySelectorAll(".hm-tabbtn"));
    var panels = Array.prototype.slice.call(group.querySelectorAll(".hm-tabpanel"));
    function select(name) {
      buttons.forEach(function (b) {
        var on = b.getAttribute("data-tab") === name;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.forEach(function (p) {
        var on = p.getAttribute("data-panel") === name;
        p.hidden = !on;
        p.classList.toggle("is-active", on);
      });
    }
    buttons.forEach(function (b, i) {
      b.addEventListener("click", function () { select(b.getAttribute("data-tab")); });
      b.addEventListener("keydown", function (e) {
        var dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (!dir) return;
        var next = buttons[(i + dir + buttons.length) % buttons.length];
        next.focus(); select(next.getAttribute("data-tab"));
      });
    });
  });

  // ---- Count-up numbers + scroll reveals ----
  function fmt(n) { return n.toLocaleString("en-US"); }
  function countUp(el) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    var suffix = el.getAttribute("data-suffix") || "";
    if (reduceMotion || !target) { el.textContent = fmt(target) + suffix; return; }
    var start = null, dur = 1400;
    function step(ts) {
      if (start === null) start = ts;
      var t = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = fmt(Math.round(target * eased)) + (t === 1 ? suffix : "");
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("is-in");
        Array.prototype.forEach.call(e.target.querySelectorAll("[data-count]"), countUp);
        io.unobserve(e.target);
      });
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.08 });

    Array.prototype.forEach.call(document.querySelectorAll(
      ".hm-problem-line, .hm-globe-wrap, .hm-stats-panel, .hm-sb-wrap, .hm-founder-panel, .hm-final .hm-wrap"
    ), function (el) {
      if (el.getBoundingClientRect().top < window.innerHeight) { Array.prototype.forEach.call(el.querySelectorAll("[data-count]"), countUp); return; }
      el.classList.add("hm-reveal");
      io.observe(el);
    });
  }
})();
