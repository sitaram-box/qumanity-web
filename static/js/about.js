/**
 * about.js — About page behaviour: scroll-spy for the side navigation,
 * reveal-on-scroll for cards, and a back-to-top button. The page is fully
 * readable without JavaScript (reveal classes are added by this script only).
 */
(function () {
  "use strict";

  var links = Array.prototype.slice.call(document.querySelectorAll("#ab-toc a"));
  var sections = links.map(function (a) {
    return document.getElementById(a.getAttribute("href").slice(1));
  }).filter(Boolean);

  function setActive(id) {
    links.forEach(function (a) {
      var on = a.getAttribute("href") === "#" + id;
      a.classList.toggle("is-active", on);
      if (on && a.scrollIntoView && window.matchMedia("(max-width: 1100px)").matches) {
        a.scrollIntoView({ block: "nearest", inline: "center" });
      }
    });
  }

  // Scroll-spy: the section whose top has most recently passed the reading line.
  function onScroll() {
    var line = window.innerHeight * 0.28;
    var current = sections[0];
    sections.forEach(function (s) {
      if (s.getBoundingClientRect().top <= line) current = s;
    });
    if (current) setActive(current.id);

    var top = document.getElementById("ab-top");
    if (top) top.hidden = window.scrollY < 600;
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  onScroll();

  var topBtn = document.getElementById("ab-top");
  if (topBtn) topBtn.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: "smooth" }); });

  // ---- Contextual Help System (2026-11-16): deep-linking from a dashboard "?" icon ----
  // ?from=dashboard shows the "← Back to Dashboard" button; history.back() returns the user to
  // their exact dashboard tab/scroll position, not just a fixed /dashboard href, since the
  // dashboard is a single page whose tabs/levels are all client-side state.
  if (new URLSearchParams(window.location.search).get("from") === "dashboard") {
    var backBtn = document.getElementById("ab-back-dashboard");
    if (backBtn) {
      backBtn.hidden = false;
      backBtn.addEventListener("click", function (e) { e.preventDefault(); history.back(); });
    }
  }

  // A target landing inside a collapsed <details> (every ab-collapse starts closed) needs that
  // <details> opened before scrollIntoView() can actually show it -- walks every <details>
  // ancestor, not just the nearest one, in case a target ever ends up nested two deep.
  if (window.location.hash) {
    var target = document.getElementById(window.location.hash.slice(1));
    if (target) {
      var d = target.closest("details");
      while (d) { d.open = true; d = d.parentElement && d.parentElement.closest("details"); }
      // One frame so the newly-opened <details> has laid out before scrolling to it -- scrolling
      // in the same frame it opens in can land short, since the browser hasn't reflowed yet.
      requestAnimationFrame(function () { target.scrollIntoView({ behavior: "smooth", block: "start" }); });
    }
  }

  // Reveal-on-scroll (skipped when IntersectionObserver isn't available).
  if ("IntersectionObserver" in window) {
    var targets = document.querySelectorAll(".ab-card, .ab-tl, .ab-tri, .ab-book, .ab-status-col, .ab-road li, .ab-steps li, .ab-cosmos div, .ab-el, .ab-callout, .ab-quote");
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    Array.prototype.forEach.call(targets, function (el) {
      var r = el.getBoundingClientRect();
      if (r.top < window.innerHeight) return; // already on screen: leave visible
      el.classList.add("ab-reveal");
      io.observe(el);
    });
  }
})();
