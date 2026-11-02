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

  // Only a placeholder for the brief window before the first /api/poems/meta response arrives
  // (no network request is ever made before then, so this value is never actually sent to the
  // server) -- matches app.py's own DEFAULT_MARQUEE_RELIGION, kept in sync by convention only.
  var DEFAULT_RELIGION_FALLBACK = "hindu";

  var view = document.getElementById("pm-view");
  var track = document.getElementById("pm-track");
  var markerEl = document.getElementById("pm-marker");
  var chipEl = document.getElementById("pm-chip");
  var chipNameEl = document.getElementById("pm-name");
  // The gold chip is the ONLY religious identity element in the marquee (2026-11-XX -- the
  // standalone homepage Shivalinga/राम badge was removed; see home.html/home.css). Its text comes
  // straight from the server's own "label" field (api_poems_meta -> religious_text_core's
  // religious_traditions.default_label -- 2026-11-02, Universal Multi-Religion Marquee) rather
  // than a hardcoded client-side table: a tradition with no reviewed label (e.g. jain/other/
  // prefer_not_to_say, which have no religious_traditions row at all) comes back as "label": null
  // and the chip is hidden entirely, never a guess and never another religion's identity
  // substituted in. The TOOLTIP (chipEl.title) is the resolved collection's own "title" field for
  // the same reason -- only the server knows exactly which edition/collection is being served.
  function syncChip(label, title) {
    if (!label) { chipEl.hidden = true; return; }   // no approved mapping -- show no identity box at all
    chipEl.hidden = false;
    chipNameEl.textContent = label;
    // Arabic-range glyphs need dir="rtl" for correct shaping/ordering of the chip text itself;
    // detected from the label's own Unicode range rather than a per-religion table, so any future
    // Arabic-labeled tradition gets this for free with no code change.
    chipNameEl.dir = /[؀-ۿ]/.test(label) ? "rtl" : "ltr";
    chipEl.title = title || "";
  }
  var playBtn = document.getElementById("pm-play");
  // Play/Pause lives next to the chip; hovering (not clicking) it pops up Previous/Next above it.
  var playWrap = document.getElementById("pm-playwrap");
  var hoverPop = document.getElementById("pm-hoverpop");
  var hideBtn = document.getElementById("pm-hide");
  var restoreBtn = document.getElementById("pm-restore");
  var langMenu = document.getElementById("pm-langmenu");
  var speedMenu = document.getElementById("pm-speedmenu");
  var religionMenu = document.getElementById("pm-religionmenu");
  // The menu icon now holds Reading tradition, Speed and Language, as three accordion sections
  // (one open at a time); picking a value closes the whole menu.
  var menuBtn = document.getElementById("pm-menubtn");
  var menuWrap = document.getElementById("pm-menuwrap");
  var comboMenu = document.getElementById("pm-combomenu");
  var speedHead = document.getElementById("pm-speedhead");
  var speedVal = document.getElementById("pm-speedval");
  var langHead = document.getElementById("pm-langhead");
  var langVal = document.getElementById("pm-langval");
  var religionHead = document.getElementById("pm-religionhead");
  var religionVal = document.getElementById("pm-religionval");

  var BASE_SPEED = 100;           // pixels per second at 1×
  var SPEEDS = [1, 1.25, 1.5, 2];
  var SPEED_KEY = "qm_poem_speed2";
  // Versioned (2026-11-02, Universal Multi-Religion Marquee, replaces the old flat "qm_poem_lang"):
  // this browser's own READING preference -- {religion, lang} -- independent of, and NEVER written
  // back to, the signed-in member's own account religion (users.religion_belief). A flat
  // "last language" no longer makes sense once language choices are religion-dependent (Arabic
  // for Quran, Hindi for the Hindu collection, ...), so this single object replaces it entirely.
  // Scoped per reader (readingKeyFor() below) so switching accounts on a shared browser doesn't
  // leak one member's reading choice onto another's session -- see the meta-fetch handler's own
  // comments for exactly how the scope is learned and reconciled.
  var READING_KEY = "qumanity_marquee_reading_v1";
  // Versioned key (2026-11-02, replaces the old "qm_poem_hidden"): this browser's own
  // hide/restore choice. Independent of users.hide_marquee (the signed-in DB preference), which
  // is now used only to SEED this value on first load when no local value yet exists -- see
  // readStoredHiddenState() and the meta fetch handler below.
  var HIDE_KEY = "qumanity_marquee_hidden_v1";
  var IDX_KEY = "qm_poem_idx", T_KEY = "qm_poem_off", PLAY_KEY = "qm_poem_playing", STAMP_KEY = "qm_poem_stamp"; // per tab session

  function readingKeyFor(scope) { return READING_KEY + ":" + (scope || "anon"); }
  function loadReadingPref(scope) {
    try {
      var raw = localStorage.getItem(readingKeyFor(scope));
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      return (parsed && typeof parsed.religion === "string") ? parsed : null;
    } catch (e) { return null; }
  }
  function saveReadingPref(scope, religion, langCode) {
    try { localStorage.setItem(readingKeyFor(scope), JSON.stringify({ religion: religion, lang: langCode })); }
    catch (e) {}
  }

  // Poems autoplay from the very first load (2026-10-05) -- if the user pauses, that choice
  // carries across pages for the rest of the tab session (via PLAY_KEY in sessionStorage, read
  // further down), but never persists into a new session: a fresh tab always starts playing.
  var meta = null, lang = "hi", readingReligion = DEFAULT_RELIGION_FALLBACK, readerScope = "anon";
  var playing = true, hoverPaused = false, speedIx = 0;
  var segs = [], offset = 0, contentW = 0, nextIdx = 0, curIdx = 0, gen = 0, filling = false, lastTs = 0, shownIdx = -1;
  var cache = {};

  function store(kind, k, v) {
    try { (kind === "local" ? localStorage : sessionStorage).setItem(k, String(v)); } catch (e) {}
  }
  function load(kind, k) {
    try { return (kind === "local" ? localStorage : sessionStorage).getItem(k); } catch (e) { return null; }
  }

  // 2026-11-02: now always the entry's own real citation (e.g. "Psalm 23:1", "Surah 1:1",
  // "Dhammapada 1.1", "मौलिक पद १") straight from the server -- the old synthesized "Poem N"/
  // "पद N" counter only ever made sense for the single-source pre-multi-religion marquee and
  // would have been actively wrong for every canonical-reference-bearing collection added today.
  function fmtMarker(p) { return p.marker; }
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

  // Reading-tradition picker (2026-11-02, Universal Multi-Religion Marquee). Lists ONLY
  // traditions the server reports as actually having an approved, servable collection right now
  // (meta.available_religions) -- a tradition with no content yet (e.g. Sikh, pending rights
  // review) is never offered, so a visitor can never select a dead end (requirement 2.3's own
  // rule, mirrored here for religion the way buildLangMenu's `available` flag mirrors it for
  // language within one religion).
  function religionLabel(code) {
    var r = (meta.available_religions || []).filter(function (x) { return x.code === code; })[0];
    return r ? r.display_name : code;
  }
  function buildReligionMenu() {
    religionMenu.innerHTML = "";
    (meta.available_religions || []).forEach(function (r) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("data-religion", r.code);
      var label = document.createElement("span"); label.textContent = r.display_name;
      var tick = document.createElement("span"); tick.className = "pm-tick"; tick.textContent = "✓";
      b.appendChild(label); b.appendChild(tick);
      b.addEventListener("click", function () { setReligion(r.code); });
      li.appendChild(b); religionMenu.appendChild(li);
    });
    syncReligionUi();
  }
  function syncReligionUi() {
    religionVal.textContent = religionLabel(readingReligion);
    Array.prototype.forEach.call(religionMenu.querySelectorAll("button"), function (b) {
      var on = b.getAttribute("data-religion") === readingReligion;
      b.classList.toggle("is-active", on); b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  // The menu icon opens one small panel holding Reading tradition, Speed and Language, as three
  // accordion sections (opening one closes the others). Picking a value closes the WHOLE menu --
  // open it again to change something else.
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
    religionMenu.hidden = true; religionHead.setAttribute("aria-expanded", "false");
  }
  function toggleAccordion(head, body) {
    var open = body.hidden;
    closeAccordions();
    if (open) { body.hidden = false; head.setAttribute("aria-expanded", "true"); }
  }
  menuBtn.addEventListener("click", function (e) { e.stopPropagation(); toggleMenu(); });
  speedHead.addEventListener("click", function (e) { e.stopPropagation(); toggleAccordion(speedHead, speedMenu); });
  langHead.addEventListener("click", function (e) { e.stopPropagation(); toggleAccordion(langHead, langMenu); });
  religionHead.addEventListener("click", function (e) { e.stopPropagation(); toggleAccordion(religionHead, religionMenu); });
  document.addEventListener("click", function (e) { if (!menuWrap.contains(e.target)) closeMenu(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { closeMenu(); closeHoverPop(); } });

  function setLang(code) {
    var changed = code !== lang;
    if (changed) { lang = code; saveReadingPref(readerScope, readingReligion, code); }
    syncLangUi();
    closeMenu(); // the whole menu closes once a choice is made
    if (changed) reset(curIdx, 0);
  }

  // Switching reading tradition: re-fetches meta for the new religion (the server resolves its
  // own default language, honoring a previously-saved language for THIS religion if one exists --
  // see fetchMeta()/applyMeta() below), rebuilds the chip/language list/strip, and persists the
  // choice -- entirely client-side, never touching the signed-in member's own profile religion
  // (no route this calls ever writes users.religion_belief; see app.py's api_poems_meta()).
  function setReligion(code) {
    if (!meta || code === readingReligion) { closeMenu(); return; }
    fetchMeta({ religion: code }).then(function (m) {
      applyMeta(m);
      // m.religion/m.default are the server's own RESOLVED values (never just an echo of the
      // requested `code`), so this is exactly what gets honored on the next visit/reconciliation.
      if (!m.coming_soon) saveReadingPref(readerScope, m.religion, m.default);
      closeMenu();
    }).catch(function (err) { console.error("Poems marquee:", err); });
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

  // Current reading language's own script direction (meta.languages[].dir, set server-side from
  // text_collection_languages.script_direction -- see religious_text_core.py) -- "ltr" until the
  // first meta response arrives, same safe default the CSS/markup already assumes.
  function currentDir() {
    if (!meta) return "ltr";
    var l = meta.languages.filter(function (x) { return x.code === lang; })[0];
    return (l && l.dir) || "ltr";
  }

  function getPoem(i) {
    var key = readingReligion + ":" + lang + ":" + i;
    if (!cache[key]) {
      cache[key] = fetch("/api/poems/" + lang + "/" + i + "?religion=" + encodeURIComponent(readingReligion))
        .then(function (r) { if (!r.ok) throw new Error("poem " + r.status); return r.json(); })
        .catch(function (e) { delete cache[key]; throw e; });
    }
    return cache[key];
  }

  // One poem = one segment in a single continuous strip, so the next poem follows straight after
  // the last word. `dir` is set per-segment (never flipping the marquee's own left-to-right
  // SCROLL direction, which stays constant for every language, ticker-style) so Arabic and any
  // future RTL script's glyphs still shape and order correctly within their own segment.
  function buildSeg(p) {
    var el = document.createElement("span");
    el.className = "pm-seg"; el.setAttribute("lang", lang); el.dir = currentDir();
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
        revealReady();     // content now has at least one segment ready -- show, unless hidden by choice
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

  // A member (signed-in, via their own profile religion, or anonymous reading a tradition with
  // no content) whose current reading tradition has no verses yet (meta.coming_soon, see app.py's
  // api_poems_meta) gets a static one-line notice in the same bar instead of the scrolling strip
  // -- play/pause and speed don't apply, so they're hidden, but the Reading Tradition selector
  // (2026-11-02, Universal Multi-Religion Marquee) STAYS reachable: a member whose own tradition
  // has no content yet must never be left with zero way to read something else, only a dead end.
  // The gold chip still shows their REAL identity box, via syncChip(), if an approved label
  // exists for their tradition -- it's hidden entirely if not (e.g. jain), never a generic
  // placeholder standing in for an unverified identity (2026-11-XX).
  function showComingSoon(m) {
    view.innerHTML = "";
    var note = document.createElement("span");
    note.className = "pm-seg pm-coming-soon";
    note.textContent = "✨ Verses for your spiritual path are coming soon.";
    view.appendChild(note);
    syncChip(m.label, m.title);
    markerEl.textContent = "";
    playWrap.hidden = true;
    langHead.hidden = true;
    speedHead.hidden = true;
    revealReady();
  }

  // ---- Hide/restore (2026-11-02): the Marquee is public by default and must always stay
  // reachable once hidden -- replaces the old one-way "X" dismiss. localStorage (HIDE_KEY) is
  // the source of truth for THIS browser's current visibility; users.hide_marquee (the signed-in
  // DB preference, set via POST /api/marquee/hide -- unchanged route, unchanged schema) only
  // ever SEEDS it once, on a browser/device that has no local value yet -- see the meta handler
  // below. Transitions respect prefers-reduced-motion; `transitioning` makes a rapid repeated
  // click safe (ignored mid-transition, never queued or double-applied). ----
  var reduceMotion = (function () {
    try { return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
    catch (e) { return false; }
  })();
  var transitioning = false;

  function readStoredHiddenState() {
    var raw = load("local", HIDE_KEY);
    if (raw === "true") return true;
    if (raw === "false") return false;
    return null; // missing key, or an invalid/unrecognized value -- no explicit local preference; default visible
  }

  // The single best guess at the intended visibility, known synchronously before the meta fetch
  // even starts -- so the restore button can appear immediately if a prior "hidden" choice is on
  // record, with no network round-trip required first.
  var targetHidden = readStoredHiddenState() === true;
  restoreBtn.hidden = !targetHidden;

  // Called once real content (or the coming-soon notice) has actually been built and is ready to
  // show -- the one place that decides whether the bar becomes visible, replacing the old
  // unconditional `bar.hidden = false` at the end of every content-building path. Always
  // instant (no slide) -- this is "content finished loading," not a user-initiated toggle.
  function revealReady() {
    setHidden(targetHidden, { instant: true });
  }

  // hidden: the desired end state. opts.instant skips the slide animation (used for the initial
  // reveal/hide on page load, and automatically whenever prefers-reduced-motion is set). Returns
  // true if the state actually changed (or was already correct), false if a click arrived while
  // an animated transition was still in flight and was ignored outright, never queued. The guard
  // sits BEFORE any mutation -- targetHidden/restoreBtn are left completely untouched on a
  // rejected call, so a rapid repeated click can never leave them disagreeing with the bar's own
  // actual (mid-transition) DOM state. Callers only persist to localStorage/the server on a true
  // return, so a rejected click never desyncs saved state from what's on screen either.
  function setHidden(hidden, opts) {
    opts = opts || {};
    var instant = !!opts.instant;
    if (transitioning && !instant) return false;
    // Captured BEFORE any mutation below: setting `hidden`/`restoreBtn.hidden` on whichever
    // element currently holds keyboard focus forces an immediate, synchronous native blur to
    // <body> -- checking document.activeElement any later than this would always see that blur
    // having already happened, never the real pre-click focus.
    var focusWasInBar = bar.contains(document.activeElement);
    var focusWasOnRestore = document.activeElement === restoreBtn;
    targetHidden = hidden;
    restoreBtn.hidden = !hidden;
    if (hidden) {
      if (bar.hidden) return true; // already fully hidden -- nothing to animate
      // Hiding a bar that currently holds keyboard focus (i.e. the Hide button itself, mid-click)
      // would otherwise leave focus stranded on <body> once `hidden` is set, since the focused
      // element is removed from the accessibility tree -- move it to the restore button instead,
      // so a keyboard user lands exactly where they'd want to go next, never off the page entirely.
      if (instant || reduceMotion) {
        bar.hidden = true; document.body.classList.remove("pm-on");
        if (focusWasInBar) restoreBtn.focus();
        return true;
      }
      transitioning = true;
      bar.classList.add("pm-sliding-out");
      var finishHide = function () {
        bar.removeEventListener("transitionend", finishHide); clearTimeout(hideTimer);
        bar.hidden = true; document.body.classList.remove("pm-on"); transitioning = false;
        if (focusWasInBar) restoreBtn.focus();
      };
      var hideTimer = setTimeout(finishHide, 400); // safety net if transitionend never fires
      bar.addEventListener("transitionend", finishHide);
    } else {
      if (!bar.hidden) { bar.classList.remove("pm-sliding-out"); return true; } // already visible
      // Symmetric to the hide case above: restoreBtn.hidden was just set true (top of this
      // function), which would otherwise strand focus on <body> if the restore button itself was
      // focused -- send it to the Hide button instead, interactive again the instant `bar.hidden`
      // clears below, even while the slide-in animation is still playing.
      bar.hidden = false; document.body.classList.add("pm-on");
      if (focusWasOnRestore) hideBtn.focus();
      if (instant || reduceMotion) { bar.classList.remove("pm-sliding-out"); return true; }
      // Restoring from a genuine hide: start from the "down" position and animate up. (On a
      // fresh page load where the bar was simply never revealed yet -- not user-hidden -- this
      // branch is never reached, since revealReady() always passes instant=true.)
      transitioning = true;
      bar.classList.add("pm-sliding-out");
      void bar.offsetHeight; // force a reflow so the browser registers the starting position
      requestAnimationFrame(function () { bar.classList.remove("pm-sliding-out"); });
      var finishShow = function () {
        bar.removeEventListener("transitionend", finishShow); clearTimeout(showTimer);
        transitioning = false;
      };
      var showTimer = setTimeout(finishShow, 400);
      bar.addEventListener("transitionend", finishShow);
    }
    return true;
  }

  hideBtn.addEventListener("click", function () {
    if (!setHidden(true, { instant: false })) return; // a transition was already in flight -- ignored, nothing changed
    store("local", HIDE_KEY, "true");
    // Best-effort device-to-device sync for a signed-in member (POST /api/marquee/hide,
    // @login_required, unchanged route); for a logged-out visitor it 302s to /login and this
    // just no-ops -- localStorage above is what actually controls this browser either way.
    fetch("/api/marquee/hide", { method: "POST" }).catch(function () {});
  });
  restoreBtn.addEventListener("click", function () {
    if (!setHidden(false, { instant: false })) return;
    store("local", HIDE_KEY, "false");
    fetch("/api/marquee/show", { method: "POST" }).catch(function () {});
  });

  // fetchMeta(params): params.religion/params.lang become the ?religion=/&lang= query-string
  // overrides api_poems_meta() allowlist-checks server-side (see app.py's own docstring on that
  // route) -- omitted entirely on the very first call, so that first call always reflects the
  // member's own profile-based default (or the public Hindu default for an anonymous visitor).
  function fetchMeta(params) {
    var parts = [];
    if (params && params.religion) parts.push("religion=" + encodeURIComponent(params.religion));
    if (params && params.lang) parts.push("lang=" + encodeURIComponent(params.lang));
    var qs = parts.length ? "?" + parts.join("&") : "";
    return fetch("/api/poems/meta" + qs).then(function (r) { if (!r.ok) throw new Error("meta " + r.status); return r.json(); });
  }

  // True only until the marquee's own animation loop has been started once -- requestAnimationFrame(tick)
  // is self-perpetuating (tick() re-schedules itself every frame), so it must only ever be kicked
  // off ONCE, never again on a later reading-tradition switch (applyMeta() is called again then,
  // but must not start a second concurrent loop). Also gates whether a saved session resume
  // position (IDX_KEY/T_KEY) is honored -- those indices belong to whatever collection was
  // playing when the tab/page was last left, never to a collection the member just switched to
  // mid-session, which always starts at a fresh random poem instead.
  var marqueeStarted = false;

  // The single place a meta response (initial load OR a Reading Tradition/explicit switch) is
  // turned into the visible marquee -- builds/rebuilds the Religion Selector every time (its
  // options never change mid-session, but rebuilding is cheap and keeps this one code path simple),
  // then either shows the coming-soon notice or the real scrolling strip.
  function applyMeta(m) {
    readingReligion = m.religion;
    // The server's own hide_marquee preference seeds this browser's state ONLY when it has no
    // explicit local choice yet (e.g. a signed-in member's first visit from a new device/browser
    // after hiding it elsewhere) -- it never overrides an explicit local choice, even a stale
    // one, per this feature's own precedence rule. Only meaningful on the very first call, but
    // harmless (and correctly a no-op) on a later reading-tradition switch too.
    if (readStoredHiddenState() === null && m.hidden) {
      targetHidden = true;
      store("local", HIDE_KEY, "true");
      restoreBtn.hidden = false;
    }
    meta = m; // set before buildReligionMenu()/buildLangMenu() need it, even in the coming_soon branch
    buildReligionMenu();
    if (m.coming_soon) { showComingSoon(m); return; }
    playWrap.hidden = false; langHead.hidden = false; speedHead.hidden = false; // undo a PRIOR coming_soon, if any
    syncChip(m.label, m.title);
    var usable = m.languages.filter(function (l) { return l.available !== false; });
    var pref = loadReadingPref(readerScope);
    var savedLang = (pref && pref.religion === m.religion) ? pref.lang : null;
    lang = usable.some(function (l) { return l.code === savedLang; }) ? savedLang : m.default;
    buildLangMenu();

    buildSpeedMenu();
    var sp = SPEEDS.indexOf(parseFloat(load("local", SPEED_KEY)));
    setSpeed(sp >= 0 ? sp : 0);

    var savedPlay = load("session", PLAY_KEY);
    if (savedPlay !== null) playing = savedPlay === "1";
    setPlayingUi();

    cache = {}; // a newly-selected religion/language pairing's own entries, never mixed with a prior selection's cached responses

    var isFirstLoad = !marqueeStarted;
    var savedIdx = isFirstLoad ? parseInt(load("session", IDX_KEY), 10) : NaN;
    var resumeAt = 0, start;
    if (!isNaN(savedIdx) && savedIdx >= 0 && savedIdx < m.count) {
      start = savedIdx;                                          // same poem as the previous page
      var age = Date.now() - parseInt(load("session", STAMP_KEY) || "0", 10);
      if (age < 15000) resumeAt = parseInt(load("session", T_KEY) || "0", 10) || 0;
    } else {
      start = Math.floor(Math.random() * m.count);               // first load, or a fresh switch: a random poem
    }
    reset(start, resumeAt);
    if (isFirstLoad) { marqueeStarted = true; requestAnimationFrame(tick); }
  }

  fetchMeta(null)
    .then(function (m) {
      // Reconcile this browser's saved reading preference (if this reader -- anonymous, or this
      // specific signed-in member via reader_scope -- has one) against the profile-based default
      // this first, unscoped fetch just returned. Only re-fetches when the saved choice names a
      // tradition the server actually reports as available right now (requirement 3.5's "missing
      // collection fallback" rule: a stale/removed saved religion is silently ignored, never an
      // error) -- otherwise the first response is used as-is.
      readerScope = m.reader_scope || "anon";
      var pref = loadReadingPref(readerScope);
      var prefAvailable = pref && (m.available_religions || []).some(function (a) { return a.code === pref.religion; });
      if (prefAvailable && pref.religion !== m.religion) {
        return fetchMeta({ religion: pref.religion, lang: pref.lang }).then(applyMeta);
      }
      return applyMeta(m);
    })
    .catch(function (err) { console.error("Poems marquee:", err); });
})();
