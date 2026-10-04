/**
 * poems.js — the poems marquee shown along the bottom of every page.
 *
 * - Starts on a random poem, then plays in sequence (n, n+1, n+2 … wrapping to the start).
 * - Language toggle (built from /api/poems/meta, so new translations appear
 *   automatically); the same poem continues in the newly chosen language.
 * - The current poem, playback position, language and pause state are kept in
 *   the browser, so it looks the same and carries on when you move between pages.
 */
(function () {
  "use strict";

  var bar = document.getElementById("pm-bar");
  if (!bar) return;

  var view = document.getElementById("pm-view");
  var track = document.getElementById("pm-track");
  var markerEl = document.getElementById("pm-marker");
  var playBtn = document.getElementById("pm-play");
  // Play/Pause lives next to the chip; hovering (not clicking) it pops up Previous/Next above it.
  var playWrap = document.getElementById("pm-playwrap");
  var hoverPop = document.getElementById("pm-hoverpop");
  var langMenu = document.getElementById("pm-langmenu");
  var speedMenu = document.getElementById("pm-speedmenu");
  // The menu icon now holds only Speed and Language, as two accordion sections (one open at a
  // time); picking a value closes the whole menu.
  var menuBtn = document.getElementById("pm-menubtn");
  var menuWrap = document.getElementById("pm-menuwrap");
  var comboMenu = document.getElementById("pm-combomenu");
  var speedHead = document.getElementById("pm-speedhead");
  var speedVal = document.getElementById("pm-speedval");
  var langHead = document.getElementById("pm-langhead");
  var langVal = document.getElementById("pm-langval");

  var BASE_SPEED = 100;           // pixels per second at 1×
  var SPEEDS = [1, 1.25, 1.5, 2];
  var SPEED_KEY = "qm_poem_speed2";
  var LANG_KEY = "qm_poem_lang";  // remembered across visits
  var IDX_KEY = "qm_poem_idx", T_KEY = "qm_poem_off", PLAY_KEY = "qm_poem_playing", STAMP_KEY = "qm_poem_stamp"; // per tab session

  // Poems start paused (2026-09-28) -- the very first load of a browser session is always paused;
  // once the user presses play, that choice carries across pages for the rest of the tab session
  // (via PLAY_KEY in sessionStorage, read further down).
  var meta = null, lang = "hi", playing = false, hoverPaused = false, speedIx = 0;
  var segs = [], offset = 0, contentW = 0, nextIdx = 0, curIdx = 0, gen = 0, filling = false, lastTs = 0, shownIdx = -1;
  var cache = {};

  function store(kind, k, v) {
    try { (kind === "local" ? localStorage : sessionStorage).setItem(k, String(v)); } catch (e) {}
  }
  function load(kind, k) {
    try { return (kind === "local" ? localStorage : sessionStorage).getItem(k); } catch (e) { return null; }
  }

  function fmtMarker(p) { return (lang === "hi" ? "पद " : "Poem ") + p.id; }
  function norm(i) { return ((i % meta.count) + meta.count) % meta.count; }

  function langLabel(code) {
    var l = meta.languages.filter(function (x) { return x.code === code; })[0];
    return l ? l.label : code;
  }

  // One button opens a menu of every available language (more can be added on the server).
  function buildLangMenu() {
    langMenu.innerHTML = "";
    meta.languages.forEach(function (l) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("lang", l.code); b.setAttribute("data-lang", l.code);
      var label = document.createElement("span"); label.textContent = l.label;
      if (l.available === false) { b.disabled = true; var soon = document.createElement("small"); soon.textContent = "coming soon"; label.appendChild(document.createTextNode(" ")); label.appendChild(soon); }
      var tick = document.createElement("span"); tick.className = "pm-tick"; tick.textContent = "✓";
      b.appendChild(label); b.appendChild(tick);
      b.addEventListener("click", function () { setLang(l.code); });
      li.appendChild(b); langMenu.appendChild(li);
    });
    syncLangUi();
  }
  function syncLangUi() {
    langVal.textContent = langLabel(lang);
    Array.prototype.forEach.call(langMenu.querySelectorAll("button"), function (b) {
      var on = b.getAttribute("data-lang") === lang;
      b.classList.toggle("is-active", on); b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  // The menu icon opens one small panel holding just Speed and Language, as two accordion
  // sections (opening one closes the other). Picking a value closes the WHOLE menu -- open it
  // again to change something else.
  function closeMenu() {
    comboMenu.hidden = true; menuBtn.setAttribute("aria-expanded", "false");
    closeAccordions();
  }
  function toggleMenu() {
    var open = comboMenu.hidden;
    if (open) { comboMenu.hidden = false; menuBtn.setAttribute("aria-expanded", "true"); }
    else closeMenu();
  }
  function closeAccordions() {
    speedMenu.hidden = true; speedHead.setAttribute("aria-expanded", "false");
    langMenu.hidden = true; langHead.setAttribute("aria-expanded", "false");
  }
  function toggleAccordion(head, body) {
    var open = body.hidden;
    closeAccordions();
    if (open) { body.hidden = false; head.setAttribute("aria-expanded", "true"); }
  }
  menuBtn.addEventListener("click", function (e) { e.stopPropagation(); toggleMenu(); });
  speedHead.addEventListener("click", function (e) { e.stopPropagation(); toggleAccordion(speedHead, speedMenu); });
  langHead.addEventListener("click", function (e) { e.stopPropagation(); toggleAccordion(langHead, langMenu); });
  document.addEventListener("click", function (e) { if (!menuWrap.contains(e.target)) closeMenu(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { closeMenu(); closeHoverPop(); } });

  function setLang(code) {
    var changed = code !== lang;
    if (changed) { lang = code; store("local", LANG_KEY, code); }
    syncLangUi();
    closeMenu(); // the whole menu closes once a choice is made
    if (changed) reset(curIdx, 0);
  }

  // The dashboard's own language switcher (static/js/i18n.js) dispatches this whenever the
  // signed-in member's preferred UI language changes -- follow it here too, but only if a poem
  // translation actually exists for it (poems are a fixed set of translated files, not every one
  // of the 23 UI languages has one yet; see Poems/poems_<lang>.json).
  document.addEventListener("qm-lang", function (e) {
    if (!meta) return;
    var ok = meta.languages.some(function (l) { return l.code === e.detail && l.available !== false; });
    if (ok) setLang(e.detail);
  });

  function setPlayingUi() {
    bar.classList.toggle("pm-paused", !playing);
    playBtn.setAttribute("aria-label", playing ? "Pause" : "Play");
    playBtn.title = playing ? "Pause" : "Play";
  }

  // Hover (not click) on the Play/Pause button pops up Previous/Next above it. A click on an arrow
  // closes the pop-up immediately, even while the cursor is still technically over it -- it only
  // reappears on a fresh hover (mouse actually leaving and re-entering).
  function openHoverPop() { hoverPop.hidden = false; }
  function closeHoverPop() { hoverPop.hidden = true; }
  playWrap.addEventListener("mouseenter", openHoverPop);
  playWrap.addEventListener("mouseleave", closeHoverPop);
  // Touch devices have no hover: a long-press on Play/Pause opens the same pop-up.
  var touchTimer = null;
  playWrap.addEventListener("touchstart", function () { touchTimer = setTimeout(openHoverPop, 500); }, { passive: true });
  playWrap.addEventListener("touchend", function () { clearTimeout(touchTimer); });
  document.addEventListener("touchstart", function (e) { if (!hoverPop.hidden && !playWrap.contains(e.target)) closeHoverPop(); });

  function getPoem(i) {
    var key = lang + ":" + i;
    if (!cache[key]) {
      cache[key] = fetch("/api/poems/" + lang + "/" + i)
        .then(function (r) { if (!r.ok) throw new Error("poem " + r.status); return r.json(); })
        .catch(function (e) { delete cache[key]; throw e; });
    }
    return cache[key];
  }

  // One poem = one segment in a single continuous strip, so the next poem follows straight after the last word.
  function buildSeg(p) {
    var el = document.createElement("span");
    el.className = "pm-seg"; el.setAttribute("lang", lang);
    var mk = document.createElement("span"); mk.className = "pm-mk"; mk.textContent = fmtMarker(p); el.appendChild(mk);
    p.text.split(/\n+/).filter(function (l) { return l.trim(); }).forEach(function (line, n) {
      if (n) { var sep = document.createElement("span"); sep.className = "pm-sep"; sep.textContent = "❖"; el.appendChild(sep); }
      el.appendChild(document.createTextNode(line.trim()));
    });
    return el;
  }

  // Keep at least two screens of text queued to the right of what is visible.
  function fill() {
    if (filling) return;
    var g = gen; filling = true;
    (function step() {
      if (g !== gen) { filling = false; return; }
      if (segs.length && contentW - offset >= view.clientWidth * 2) { filling = false; return; }
      var i = nextIdx;
      getPoem(i).then(function (p) {
        if (g !== gen) { filling = false; return; }
        var el = buildSeg(p);
        track.appendChild(el);
        segs.push({ el: el, idx: i, w: el.offsetWidth, poem: p });
        contentW += el.offsetWidth;
        nextIdx = norm(i + 1);
        bar.hidden = false; document.body.classList.add("pm-on");
        getPoem(nextIdx).catch(function () {});     // warm the cache for the poem after
        step();
      }).catch(function (err) {
        filling = false; console.error("Poems marquee:", err); setTimeout(fill, 3000);
      });
    })();
  }

  // Start the strip at poem `i`, `off` pixels into it.
  function reset(i, off) {
    gen++; filling = false;
    track.innerHTML = ""; segs = []; contentW = 0; offset = off || 0;
    nextIdx = norm(i); curIdx = nextIdx; shownIdx = -1;
    track.style.transform = "translate3d(0,0,0)";
    fill();
  }

  function showCurrent() {
    var x = offset + view.clientWidth * 0.2, acc = 0, cur = segs[0];
    for (var k = 0; k < segs.length; k++) { acc += segs[k].w; cur = segs[k]; if (x < acc) break; }
    if (!cur || cur.idx === shownIdx) return;
    shownIdx = curIdx = cur.idx;
    markerEl.textContent = fmtMarker(cur.poem);
    bar.title = cur.poem.marker;
    store("session", IDX_KEY, curIdx);
  }

  function tick(ts) {
    var dt = lastTs ? Math.min(ts - lastTs, 100) : 0; lastTs = ts;
    if (segs.length) {
      if (playing && !hoverPaused) offset += BASE_SPEED * SPEEDS[speedIx] * dt / 1000;
      while (segs.length > 1 && offset >= segs[0].w) {     // first poem fully gone: drop it
        offset -= segs[0].w; contentW -= segs[0].w; segs[0].el.remove(); segs.shift();
      }
      if (offset > contentW - 8) offset = contentW - 8;    // never run past the end while the next poem loads
      track.style.transform = "translate3d(" + (-offset) + "px,0,0)";
      showCurrent();
      if (contentW - offset < view.clientWidth * 2) fill();
    }
    requestAnimationFrame(tick);
  }

  function togglePlay() { playing = !playing; store("session", PLAY_KEY, playing ? "1" : "0"); setPlayingUi(); }

  var SPEED_LABELS = ["1.0", "1.25", "1.5", "2.0"];
  function buildSpeedMenu() {
    SPEEDS.forEach(function (v, i) {
      var li = document.createElement("li"), b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("data-ix", i);
      b.innerHTML = "<span>" + SPEED_LABELS[i] + "×</span><span class=\"pm-tick\">✓</span>";
      b.addEventListener("click", function () { setSpeed(i); });
      li.appendChild(b); speedMenu.appendChild(li);
    });
  }
  function setSpeed(ix) {
    speedIx = Math.max(0, Math.min(SPEEDS.length - 1, ix)); store("local", SPEED_KEY, SPEEDS[speedIx]);
    speedVal.textContent = SPEED_LABELS[speedIx] + "×";
    Array.prototype.forEach.call(speedMenu.querySelectorAll("button"), function (b) {
      var on = +b.getAttribute("data-ix") === speedIx;
      b.classList.toggle("is-active", on); b.setAttribute("aria-selected", on ? "true" : "false");
    });
    closeMenu(); // the whole menu closes once a choice is made
  }

  playBtn.addEventListener("click", togglePlay);
  document.getElementById("pm-next").addEventListener("click", function (e) { e.stopPropagation(); reset(curIdx + 1, 0); closeHoverPop(); });
  document.getElementById("pm-prev").addEventListener("click", function (e) { e.stopPropagation(); reset(curIdx - 1, 0); closeHoverPop(); });
  view.addEventListener("mouseenter", function () { hoverPaused = true; });
  view.addEventListener("mouseleave", function () { hoverPaused = false; });

  // Carry the position to the next page.
  function saveProgress() {
    if (!segs.length) return;
    store("session", IDX_KEY, segs[0].idx); store("session", T_KEY, Math.round(offset)); store("session", STAMP_KEY, Date.now());
  }
  window.addEventListener("pagehide", saveProgress);
  document.addEventListener("visibilitychange", function () { if (document.hidden) saveProgress(); });

  var resizeTimer = null;
  window.addEventListener("resize", function () {          // text widths can change with the window: re-measure
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      contentW = 0; segs.forEach(function (sg) { sg.w = sg.el.offsetWidth; contentW += sg.w; });
    }, 200);
  });

  fetch("/api/poems/meta")
    .then(function (r) { if (!r.ok) throw new Error("meta " + r.status); return r.json(); })
    .then(function (m) {
      meta = m;
      var usable = m.languages.filter(function (l) { return l.available !== false; });
      var savedLang = load("local", LANG_KEY);
      // Hindi is the default for visitors; a signed-in user starts on their own language (or English) and their choice is remembered.
      lang = usable.some(function (l) { return l.code === savedLang; }) ? savedLang
           : (m.default || (usable.some(function (l) { return l.code === "hi"; }) ? "hi" : (usable[0] || {}).code));
      buildLangMenu();

      buildSpeedMenu();
      var sp = SPEEDS.indexOf(parseFloat(load("local", SPEED_KEY)));
      setSpeed(sp >= 0 ? sp : 0);

      var savedPlay = load("session", PLAY_KEY);
      if (savedPlay !== null) playing = savedPlay === "1";
      setPlayingUi();

      var savedIdx = parseInt(load("session", IDX_KEY), 10);
      var resumeAt = 0, start;
      if (!isNaN(savedIdx) && savedIdx >= 0 && savedIdx < m.count) {
        start = savedIdx;                                          // same poem as the previous page
        var age = Date.now() - parseInt(load("session", STAMP_KEY) || "0", 10);
        if (age < 15000) resumeAt = parseInt(load("session", T_KEY) || "0", 10) || 0;
      } else {
        start = Math.floor(Math.random() * m.count);               // first load: a random poem
      }
      reset(start, resumeAt);
      requestAnimationFrame(tick);
    })
    .catch(function (err) { console.error("Poems marquee:", err); });
})();
