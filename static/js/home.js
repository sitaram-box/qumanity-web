/**
 * home.js — homepage behaviour: sticky-nav state + scroll-spy, mobile menu,
 * tabs, count-up numbers, scroll reveals, cursor spotlight on glass cards and
 * the interactive zodiac wheel (highlights the current Sun sign).
 * The globe and live statistics are handled by earth.js.
 */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- Sticky nav + scroll-spy ----
  var nav = document.getElementById("hm-nav");
  var links = Array.prototype.slice.call(document.querySelectorAll("#hm-links a[href^='#']"));
  var spySections = links.map(function (a) { return document.getElementById(a.getAttribute("href").slice(1)); });

  function onScroll() {
    nav.classList.toggle("is-scrolled", window.scrollY > 24);
    var line = window.innerHeight * 0.3, current = null;
    spySections.forEach(function (s) {
      if (!s) return;
      var b = s.getBoundingClientRect();
      if (b.top <= line && b.bottom > line) current = s;
    });
    links.forEach(function (a, i) { a.classList.toggle("is-active", spySections[i] === current); });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

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

  // ---- Cursor spotlight on glass cards ----
  Array.prototype.forEach.call(document.querySelectorAll(".hm-spot"), function (card) {
    card.addEventListener("pointermove", function (e) {
      var r = card.getBoundingClientRect();
      card.style.setProperty("--mx", (e.clientX - r.left) + "px");
      card.style.setProperty("--my", (e.clientY - r.top) + "px");
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
      ".hm-head, .hm-shift article, .hm-triune, .hm-id-grid article, .hm-timelines, .hm-wheelbox, .hm-gov-copy, " +
      ".hm-loop li, .hm-money, .hm-services article, .hm-trustgrid, .hm-road li, .hm-today, .hm-steward blockquote, .hm-final .hm-wrap, .hm-numbers .hm-wrap"
    ), function (el) {
      if (el.getBoundingClientRect().top < window.innerHeight) { Array.prototype.forEach.call(el.querySelectorAll("[data-count]"), countUp); return; }
      el.classList.add("hm-reveal");
      io.observe(el);
    });
  }

  // ---- Zodiac wheel ----
  var SIGNS = [
    { n: "Aries", g: "♈\uFE0E", e: "Fire", m: 3, d: 21 }, { n: "Taurus", g: "♉\uFE0E", e: "Earth", m: 4, d: 20 },
    { n: "Gemini", g: "♊\uFE0E", e: "Air", m: 5, d: 21 }, { n: "Cancer", g: "♋\uFE0E", e: "Water", m: 6, d: 21 },
    { n: "Leo", g: "♌\uFE0E", e: "Fire", m: 7, d: 23 }, { n: "Virgo", g: "♍\uFE0E", e: "Earth", m: 8, d: 23 },
    { n: "Libra", g: "♎\uFE0E", e: "Air", m: 9, d: 23 }, { n: "Scorpio", g: "♏\uFE0E", e: "Water", m: 10, d: 23 },
    { n: "Sagittarius", g: "♐\uFE0E", e: "Fire", m: 11, d: 22 }, { n: "Capricorn", g: "♑\uFE0E", e: "Earth", m: 12, d: 22 },
    { n: "Aquarius", g: "♒\uFE0E", e: "Air", m: 1, d: 20 }, { n: "Pisces", g: "♓\uFE0E", e: "Water", m: 2, d: 19 }
  ];
  var ELEMENT_COLOR = { Fire: "#ff6b4a", Earth: "#58d36e", Air: "#cfd8e6", Water: "#4aa8ff" };
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function currentSignIndex(d) {
    var m = d.getMonth() + 1, day = d.getDate();
    for (var i = 0; i < SIGNS.length; i++) {
      var s = SIGNS[i], nxt = SIGNS[(i + 1) % 12];
      var afterStart = m > s.m || (m === s.m && day >= s.d);
      var beforeNext = m < nxt.m || (m === nxt.m && day < nxt.d);
      if (s.m <= nxt.m ? (afterStart && beforeNext) : (afterStart || beforeNext)) return i;
    }
    return 0;
  }

  var svg = document.getElementById("hm-wheel");
  if (svg) {
    var NS = "http://www.w3.org/2000/svg", R = 150, r = 88;
    function pt(angle, rad) { var a = (angle - 90) * Math.PI / 180; return [rad * Math.cos(a), rad * Math.sin(a)]; }
    var centerSign = document.getElementById("hm-wheel-sign");
    var centerMeta = document.getElementById("hm-wheel-meta");
    var nowIdx = currentSignIndex(new Date());
    var paths = [];

    function describe(i) {
      var s = SIGNS[i], nxt = SIGNS[(i + 1) % 12];
      var end = new Date(2001, nxt.m - 1, nxt.d - 1); // day before the next sign begins
      return { title: s.g + " " + s.n, meta: s.e + " · " + MONTHS[s.m - 1] + " " + s.d + " – " + MONTHS[end.getMonth()] + " " + end.getDate() };
    }
    function show(i) {
      var d = describe(i);
      centerSign.textContent = d.title;
      centerMeta.textContent = d.meta;
      paths.forEach(function (p, j) { p.classList.toggle("is-active", j === i); });
    }

    SIGNS.forEach(function (s, i) {
      var a0 = i * 30 + 1, a1 = (i + 1) * 30 - 1;
      var p0 = pt(a0, R), p1 = pt(a1, R), q1 = pt(a1, r), q0 = pt(a0, r);
      var path = document.createElementNS(NS, "path");
      path.setAttribute("d", "M" + p0 + " A" + R + "," + R + " 0 0 1 " + p1 + " L" + q1 + " A" + r + "," + r + " 0 0 0 " + q0 + " Z");
      path.setAttribute("fill", ELEMENT_COLOR[s.e]);
      path.setAttribute("tabindex", "0");
      path.setAttribute("role", "img");
      path.setAttribute("aria-label", describe(i).title + ", " + describe(i).meta);
      path.addEventListener("mouseenter", function () { show(i); });
      path.addEventListener("focus", function () { show(i); });
      path.addEventListener("click", function () { show(i); });
      path.addEventListener("mouseleave", function () { show(nowIdx); });
      svg.appendChild(path);
      paths.push(path);

      var tp = pt(i * 30 + 15, (R + r) / 2);
      var text = document.createElementNS(NS, "text");
      text.setAttribute("x", tp[0]); text.setAttribute("y", tp[1]);
      text.textContent = s.g;
      svg.appendChild(text);
    });
    // marker ring around the current sign
    var mid = pt(nowIdx * 30 + 15, R + 9);
    var mark = document.createElementNS(NS, "circle");
    mark.setAttribute("cx", mid[0]); mark.setAttribute("cy", mid[1]); mark.setAttribute("r", 5);
    mark.setAttribute("fill", "#ffd24a");
    svg.appendChild(mark);
    show(nowIdx);
  }
})();
