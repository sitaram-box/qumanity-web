/**
 * cosmic.js — Qumanity Cosmic Homepage (Phase A, 2026-11-03).
 *
 * Two independent, self-contained pieces, both guarded so a missing element is a silent no-op
 * (this script is only ever loaded on templates/home.html, but stays defensive regardless):
 *
 *  1. A lightweight Canvas 2D particle field (#qm-cosmic-canvas) -- no Three.js/WebGL, capped at
 *     150 particles, capped frame rate, capped device-pixel ratio, paused via the Page Visibility
 *     API, and replaced by a single static draw when the user has prefers-reduced-motion set.
 *  2. A small IntersectionObserver-driven reveal for the new Earth->India->Village->Individual
 *     journey sections (.qm-reveal-el) -- plain opacity/transform, no scroll-jacking, no GSAP.
 *     Reuses the same "already visible on load" / "fade in once" shape as the existing
 *     home.js reveal for the stats panel etc., so the two systems behave identically to a visitor
 *     even though they animate different elements.
 *
 * Neither piece touches an existing element's id, class list in a way that would break other
 * scripts, or intercepts a click/keyboard event meant for the real page content.
 */
(function () {
  "use strict";

  var reduceMotionQuery = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  function prefersReducedMotion() { return !!(reduceMotionQuery && reduceMotionQuery.matches); }

  /* =============================================================================================
     PARTICLE FIELD
     ============================================================================================= */
  (function particleField() {
    var canvas = document.getElementById("qm-cosmic-canvas");
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext("2d");
    if (!ctx) return;

    var MAX_DPR = 1.75;
    var MAX_PARTICLES_DESKTOP = 130;
    var MAX_PARTICLES_MOBILE = 55;
    var CONNECT_DISTANCE = 120;
    var TARGET_FPS = 28;
    var FRAME_BUDGET_MS = 1000 / TARGET_FPS;

    var COLORS = [
      "rgba(212, 175, 55, OPA)",   // gold
      "rgba(255, 153, 51, OPA)",   // saffron
      "rgba(245, 245, 220, OPA)",  // ivory
    ];

    var width = 0, height = 0, dpr = 1;
    var particles = [];
    var rafId = null;
    var lastFrameTime = 0;
    var running = false;
    var staticDrawDone = false;

    function particleCount() {
      var w = window.innerWidth || 1024;
      if (w < 640) return Math.round(MAX_PARTICLES_MOBILE * Math.min(1, w / 640));
      var span = Math.min(1, (w - 640) / 900); // scales up to the desktop cap by ~1540px wide
      return Math.round(MAX_PARTICLES_MOBILE + (MAX_PARTICLES_DESKTOP - MAX_PARTICLES_MOBILE) * span);
    }

    function makeParticle() {
      var color = COLORS[(Math.random() * COLORS.length) | 0];
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        r: 0.6 + Math.random() * 1.8,
        vx: (Math.random() - 0.5) * 0.12,
        vy: (Math.random() - 0.5) * 0.12,
        baseOpacity: 0.25 + Math.random() * 0.45,
        twinkleSpeed: 0.0006 + Math.random() * 0.0012,
        twinklePhase: Math.random() * Math.PI * 2,
        color: color,
      };
    }

    function rebuildParticles() {
      var n = particleCount();
      particles = [];
      for (var i = 0; i < n; i++) particles.push(makeParticle());
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = width + "px";
      canvas.style.height = height + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      rebuildParticles();
    }

    function drawFrame(now) {
      ctx.clearRect(0, 0, width, height);

      // Bounded delta time so a long background gap (tab hidden, slow device) never produces a
      // single huge, jarring jump in particle position on resume.
      var dt = lastFrameTime ? Math.min(now - lastFrameTime, 64) : 16;
      lastFrameTime = now;

      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        p.x += p.vx * (dt / 16);
        p.y += p.vy * (dt / 16);
        if (p.x < -10) p.x = width + 10; else if (p.x > width + 10) p.x = -10;
        if (p.y < -10) p.y = height + 10; else if (p.y > height + 10) p.y = -10;

        var twinkle = 0.75 + 0.25 * Math.sin(now * p.twinkleSpeed + p.twinklePhase);
        var opacity = p.baseOpacity * twinkle;
        ctx.beginPath();
        ctx.fillStyle = p.color.replace("OPA", opacity.toFixed(3));
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // Quantum connections: fine, low-opacity lines between nearby particles only -- a bounded
      // O(n^2) over at most 130 particles is well within the per-frame budget (far fewer pairs
      // than a naive worst case once the distance check short-circuits most of them).
      ctx.lineWidth = 0.6;
      for (var a = 0; a < particles.length; a++) {
        for (var b = a + 1; b < particles.length; b++) {
          var dx = particles[a].x - particles[b].x;
          var dy = particles[a].y - particles[b].y;
          var distSq = dx * dx + dy * dy;
          if (distSq > CONNECT_DISTANCE * CONNECT_DISTANCE) continue;
          var dist = Math.sqrt(distSq);
          var lineOpacity = (1 - dist / CONNECT_DISTANCE) * 0.12;
          ctx.strokeStyle = "rgba(212, 175, 55, " + lineOpacity.toFixed(3) + ")";
          ctx.beginPath();
          ctx.moveTo(particles[a].x, particles[a].y);
          ctx.lineTo(particles[b].x, particles[b].y);
          ctx.stroke();
        }
      }
    }

    var lastTick = 0;
    function tick(now) {
      if (!running) return;
      if (now - lastTick >= FRAME_BUDGET_MS) {
        lastTick = now;
        drawFrame(now);
      }
      rafId = window.requestAnimationFrame(tick);
    }

    function start() {
      if (running) return;
      running = true;
      lastFrameTime = 0;
      lastTick = 0;
      rafId = window.requestAnimationFrame(tick);
    }
    function stop() {
      running = false;
      if (rafId) { window.cancelAnimationFrame(rafId); rafId = null; }
    }

    function drawStaticField() {
      resize();
      // One still frame: particles placed, no motion, no connections (connections implied
      // "gently changing," which a static field should not fake) -- just the quiet field itself.
      ctx.clearRect(0, 0, width, height);
      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        ctx.beginPath();
        ctx.fillStyle = p.color.replace("OPA", p.baseOpacity.toFixed(3));
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      staticDrawDone = true;
    }

    function applyMotionPreference() {
      if (prefersReducedMotion()) {
        stop();
        drawStaticField();
      } else {
        staticDrawDone = false;
        resize();
        start();
      }
    }

    var resizeTimer = null;
    window.addEventListener("resize", function () {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(function () {
        if (prefersReducedMotion()) { drawStaticField(); } else { resize(); }
      }, 150);
    });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        stop();
      } else if (!prefersReducedMotion()) {
        start();
      }
    });

    if (reduceMotionQuery) {
      var onMotionChange = function () { applyMotionPreference(); };
      if (reduceMotionQuery.addEventListener) reduceMotionQuery.addEventListener("change", onMotionChange);
      else if (reduceMotionQuery.addListener) reduceMotionQuery.addListener(onMotionChange); // Safari <14
    }

    applyMotionPreference();
  })();

  /* =============================================================================================
     JOURNEY SCROLL-REVEAL (Earth -> India -> Village -> Individual)
     ============================================================================================= */
  (function journeyReveal() {
    var els = document.querySelectorAll(".qm-reveal-el");
    if (!els.length) return;

    if (prefersReducedMotion() || !("IntersectionObserver" in window)) {
      for (var i = 0; i < els.length; i++) els[i].classList.add("is-in");
      return;
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-in");
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });

    Array.prototype.forEach.call(els, function (el) {
      if (el.getBoundingClientRect().top < window.innerHeight * 0.9) {
        el.classList.add("is-in");
      } else {
        io.observe(el);
      }
    });
  })();
})();
