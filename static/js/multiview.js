/**
 * multiview.js — LBE (Location Board Explorer, 2026-11-12 redesign of the 2026-10-28 Hierarchical
 * Explorer) + the persistent cross-tab dock of open location boards.
 *
 * Only ever loaded for is_admin_panel_user (dashboard.html's own gate) -- a Founder (scope
 * "global") can open any location's board anywhere real data reaches; a currently-serving village
 * council head (scope "limited") can only open sibling villages inside their own Tehsil, during
 * their own birth sign's month (GET /api/admin/viewable-locations' own access_window, re-checked
 * fresh every time the explorer opens).
 *
 * 2026-11-12: the old continent-by-continent drill-down (Earth -> Continent -> ... -> Village,
 * one click per level) is gone. LBE is now a direct Location ID / Account ID search box: type an
 * id, POST /api/admin/lbe/resolve, and the one existing openDockTab() function opens the result --
 * nothing about the dock itself changed. The Admin Queue sub-tab is untouched by this redesign.
 *
 * Opened location boards still live in a dock OUTSIDE this modal entirely -- a fixed bar at the
 * bottom of the whole page, visible on every dashboard tab (Global/Public/Personal/Private), not
 * just while this modal is open. Each tab holds its own window.QMBoard(root, {pinnedLocation})
 * instance (board.js) -- always read-only, enforced server-side by POST /api/admin/board.
 *
 * Every real board open/close now also POSTs to /api/admin/lbe/log-event (Part 6 audit logging) --
 * once per actual open (never on reactivating an already-open tab) and once per explicit close
 * (never fabricated if the tab/page just goes away).
 */
(function () {
  "use strict";

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function api(url, body) {
    var opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }

  var fab = document.getElementById("qm-explorer-fab");
  if (!fab) return; // not is_admin_panel_user -- none of this markup exists on this page at all

  var modal = document.getElementById("qm-explorer-modal");
  var subtabBtns = Array.prototype.slice.call(document.querySelectorAll(".qm-explorer-subtab"));
  var paneLocations = document.getElementById("qm-explorer-pane-locations");
  var paneQueue = document.getElementById("qm-explorer-pane-queue");
  var lbeInstructions = document.getElementById("lbe-instructions");
  var lbeInput = document.getElementById("lbe-search-input");
  var lbeBtn = document.getElementById("lbe-search-btn");
  var lbeStatus = document.getElementById("lbe-search-status");

  var dock = document.getElementById("qm-dock");
  var dockBar = document.getElementById("qm-dock-bar");
  var dockTabsEl = document.getElementById("qm-dock-tabs");
  var dockPanel = document.getElementById("qm-dock-panel");
  var boardTemplate = document.getElementById("qm-dock-board-template");
  var mainEl = document.querySelector(".qm-dashboard-main");

  // 2026-10-28 (hardening, prior reported blank-tab bug): `fab` existing doesn't guarantee every
  // other id resolved -- a stale cached copy of this file running against a newer/older
  // dashboard.html is exactly the "missing DOM element" failure mode to guard against. Fail loud
  // to the console rather than throwing out of this IIFE and silently wiring nothing below.
  var required = { modal: modal, paneLocations: paneLocations, paneQueue: paneQueue,
    lbeInstructions: lbeInstructions, lbeInput: lbeInput, lbeBtn: lbeBtn, lbeStatus: lbeStatus,
    dock: dock, dockBar: dockBar, dockTabsEl: dockTabsEl, dockPanel: dockPanel, boardTemplate: boardTemplate, mainEl: mainEl };
  var missing = Object.keys(required).filter(function (k) { return !required[k]; });
  if (missing.length || !subtabBtns.length) {
    console.error("[lbe] expected element(s) missing -- stale cached JS/HTML? Missing:", missing, "subtabs found:", subtabBtns.length);
    return;
  }
  if (!window.QMBoard) {
    console.error("[lbe] window.QMBoard is missing -- board.js didn't load, or loaded before its own window.QMBoard export was added (stale cache).");
    return;
  }

  // ==================== FAB + modal + sub-tabs ====================
  fab.addEventListener("click", function () {
    modal.hidden = false;
    subtabBtns.forEach(function (b) { b.classList.toggle("is-active", b.getAttribute("data-sub") === "locations"); });
    paneLocations.hidden = false;
    paneQueue.hidden = true;
    loadScope();
  });
  modal.addEventListener("click", function (e) {
    if (e.target === modal || e.target.hasAttribute("data-close")) modal.hidden = true;
  });

  var queueLoaded = false;
  subtabBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      subtabBtns.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
      var sub = btn.getAttribute("data-sub");
      paneLocations.hidden = sub !== "locations";
      paneQueue.hidden = sub !== "queue";
      if (sub === "queue" && !queueLoaded) { queueLoaded = true; if (window.QMLoadAdminPanel) window.QMLoadAdminPanel(); }
    });
  });

  // ==================== Scope (still the same access gate the old drill-down used) ====================
  var scope = null;

  function loadScope() {
    setStatus("Loading…", false);
    lbeInput.disabled = true; lbeBtn.disabled = true;
    api("/api/admin/viewable-locations").then(function (s) {
      scope = s;
      if (scope.scope === "none") { renderLocked(); return; }
      lbeInput.disabled = false; lbeBtn.disabled = false;
      lbeInstructions.textContent = scope.scope === "limited"
        ? "Enter a Location ID or Account ID within your own Tehsil to open its board directly."
        : "Enter a Location ID or Account ID to open its board directly.";
      setStatus("", false);
    }).catch(function (e) {
      setStatus(e.message, true);
    });
  }

  function renderLocked() {
    lbeInput.disabled = true; lbeBtn.disabled = true;
    if (scope.reason === "training") {
      lbeInstructions.textContent = "";
      setStatus("The Explorer opens during your own zodiac month (" + scope.access_window.sign + ", " +
        scope.access_window.opens + " → " + scope.access_window.closes + "). You're training the rest of the year.", true);
    } else {
      lbeInstructions.textContent = "";
      setStatus("The Location Explorer is for Admins and currently-serving council heads.", true);
    }
  }

  function setStatus(message, isError) {
    // isError is accepted for callers' own clarity but not yet given a distinct visual treatment --
    // every existing error/empty message in this dashboard (apLoadFeed, apOpenReport, etc.) already
    // reuses the plain .qm-dash-empty look, so this one does too rather than inventing a new class.
    lbeStatus.hidden = !message;
    lbeStatus.textContent = message || "";
  }

  // ==================== Search -> resolve -> open ====================
  function doSearch() {
    var query = lbeInput.value.trim();
    if (!query) { setStatus("Enter a Location ID or Account ID.", true); return; }
    setStatus("Searching…", false);
    lbeBtn.disabled = true;
    api("/api/admin/lbe/resolve", { query: query }).then(function (result) {
      lbeBtn.disabled = false;
      setStatus("", false);
      // An Account ID string doesn't itself say which kind of id was actually typed/matched --
      // resolve() tries Location ID first, Account ID second, so "contains a letter the location
      // scheme wouldn't produce at this level" is a reasonable-effort guess for the audit log's
      // own `source` field, not a security-relevant distinction (the server already re-validated
      // scope above; this only affects how the log entry reads).
      var looksLikeLocationId = /^[A-Z0-9._/]+$/i.test(query) && query.indexOf("-") === -1;
      var source = looksLikeLocationId ? "lbe_location_id" : "lbe_account_id";
      var label = deepestName(result.chain) || query;
      openDockTab(result.level, result.chain, label, source);
      modal.hidden = true;
      lbeInput.value = "";
    }).catch(function (e) {
      lbeBtn.disabled = false;
      setStatus(e.message, true);
    });
  }
  lbeBtn.addEventListener("click", doSearch);
  lbeInput.addEventListener("keydown", function (e) { if (e.key === "Enter") doSearch(); });

  function deepestName(chain) {
    var levels = ["village", "tehsil", "district", "state", "zone", "country", "continent"];
    for (var i = 0; i < levels.length; i++) {
      if (chain[levels[i]] && chain[levels[i]].name) return chain[levels[i]].name;
    }
    return null;
  }

  // ==================== Persistent cross-tab dock (2026-11-12 full-screen redesign) ====================
  // 2026-10-28, redesigned 2026-11-12: lives outside the Explorer modal and outside <main> entirely
  // -- open boards survive switching dashboard tabs and surviving closing the search modal. The
  // dock bar is always visible once >=1 location tab is open; exactly one of <main> (the normal
  // dashboard) or one open board's full-screen panel is ever shown at a time -- "My Dashboard" is
  // always the first, permanent, non-closable tab, selected by dockActiveId === null.
  var dockTabs = []; // [{id, level, label, chain, source, root, board, loaded}] -- location tabs only; "My Dashboard" isn't stored here
  var dockActiveId = null; // null = "My Dashboard"; otherwise a dockTabs[].id
  var dockCounter = 0;

  function capFor() { return scope && scope.scope === "global" ? Infinity : 5; }

  // Sets --qm-header-h/--qm-dock-bar-h from the two elements' OWN rendered heights, so the
  // full-screen board panel (position: fixed, inset between them -- see dashboard.css) lines up
  // under the real header and above the real tab bar at any viewport width, without hardcoding a
  // pixel value that would drift the moment either one's content or the responsive breakpoint changes.
  function measureDockOffsets() {
    var header = document.querySelector(".qm-header");
    if (header) document.documentElement.style.setProperty("--qm-header-h", header.offsetHeight + "px");
    document.documentElement.style.setProperty("--qm-dock-bar-h", dockBar.offsetHeight + "px");
  }
  window.addEventListener("resize", measureDockOffsets);
  measureDockOffsets();

  function renderDockBar() {
    dock.hidden = dockTabs.length === 0;
    dockTabsEl.innerHTML = "";
    var homeBtn = el("button", "qm-dock-tab" + (dockActiveId === null ? " is-active" : ""));
    homeBtn.type = "button";
    homeBtn.appendChild(el("span", "", "🏠 My Dashboard"));
    homeBtn.addEventListener("click", function () { activateDockTab(null); });
    dockTabsEl.appendChild(homeBtn);
    dockTabs.forEach(function (t) {
      var btn = el("button", "qm-dock-tab" + (t.id === dockActiveId ? " is-active" : ""));
      btn.type = "button";
      btn.appendChild(el("span", "", "📍 " + t.label));
      var close = el("span", "qm-dock-tab-close", "✕");
      close.addEventListener("click", function (e) { e.stopPropagation(); closeDockTab(t.id); });
      btn.appendChild(close);
      btn.addEventListener("click", function () { activateDockTab(t.id); });
      dockTabsEl.appendChild(btn);
    });
  }

  // id === null -> "My Dashboard": show <main>, hide the full-screen panel. Otherwise: hide <main>,
  // show the matching board full-screen, hide every other open board. Switching tabs never reloads
  // <main> or re-fetches an already-loaded board -- board.js's own `loaded` flag below is the same
  // lazy-load-once guard the pre-redesign dock already used.
  function activateDockTab(id) {
    dockActiveId = id;
    if (mainEl) mainEl.hidden = id !== null;
    dockPanel.hidden = id === null;
    dockTabs.forEach(function (t) { t.root.hidden = t.id !== id; });
    // renderDockBar() first -- it's what clears dock.hidden the very first time a tab opens, and
    // dockBar.offsetHeight (what measureDockOffsets() below reads) is 0 for a display:none ancestor.
    // Measuring before the bar is actually visible would bake in a wrong (zero) --qm-dock-bar-h.
    renderDockBar();
    measureDockOffsets();
    var t = dockTabs.filter(function (x) { return x.id === id; })[0];
    if (t && !t.loaded) { t.loaded = true; t.board.load(); }
  }

  // Part 6 audit log: fire-and-forget, never blocks the UI action it's reporting on. A failed
  // POST here (network hiccup, session race) is logged to the console, not surfaced to the admin
  // -- the board itself already opened/closed either way; this is bookkeeping, not the action.
  function logEvent(event, t) {
    api("/api/admin/lbe/log-event", {
      event: event, location_level: t.level, location_id: (t.chain[t.level] || {}).id,
      location_name: t.label, source: t.source || null,
    }).catch(function (e) { console.error("[lbe] audit log failed:", e.message); });
  }

  function closeDockTab(id) {
    var t = dockTabs.filter(function (x) { return x.id === id; })[0];
    if (!t) return;
    t.root.remove();
    dockTabs = dockTabs.filter(function (x) { return x.id !== id; });
    // Closing the active tab: switch to the next remaining board, or "My Dashboard" if none are
    // left. Closing a BACKGROUND tab (not the active one) leaves the current view untouched.
    activateDockTab(dockActiveId === id ? (dockTabs.length ? dockTabs[dockTabs.length - 1].id : null) : dockActiveId);
    logEvent("BOARD_CLOSED", t);
  }

  // `source` ("lbe_location_id" | "lbe_account_id" | "drilldown") is informational only, for the
  // audit log's own context field -- never checked for authorization (the server already did that
  // in /api/admin/lbe/resolve or /api/admin/board/<level> before this was ever called).
  function openDockTab(level, chain, label, source) {
    var existing = dockTabs.filter(function (t) { return t.level === level && (t.chain[level] || {}).id === (chain[level] || {}).id; })[0];
    if (existing) { activateDockTab(existing.id); return; } // reactivating -- not a new open, not logged
    if (dockTabs.length >= capFor()) { alert("You can have at most " + capFor() + " locations open at once — close one first."); return; }

    dockCounter += 1;
    var id = "qm-dock-tab-" + dockCounter;
    var frag = boardTemplate.content.cloneNode(true);
    var root = frag.querySelector(".bd");
    root.id = id + "-board";
    root.setAttribute("data-level", level);
    root.hidden = true;
    dockPanel.appendChild(root);

    var board = window.QMBoard(root, { pinnedLocation: chain });
    var t = { id: id, level: level, label: label, chain: chain, source: source, root: root, board: board, loaded: false };
    dockTabs.push(t);
    activateDockTab(id);
    logEvent("BOARD_OPENED", t);
  }
})();
