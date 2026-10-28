/**
 * multiview.js — the Hierarchical Explorer (2026-10-28 redesign) + the persistent cross-tab dock
 * of open location boards.
 *
 * Only ever loaded for is_admin_panel_user (dashboard.html's own gate) -- a Founder (scope
 * "global") can drill from Earth all the way to Village anywhere real data reaches (India/Sub-
 * continent only -- elsewhere stops at Country, the same data ceiling as before); a currently-
 * serving village council head (scope "limited") starts already inside their own Tehsil and can
 * only drill into sibling villages there, during their own birth sign's month (GET /api/admin/
 * viewable-locations' own access_window, re-checked fresh every time the explorer opens).
 *
 * Replaces the old per-panel Multi-View tab and map-based location wizard: one floating action
 * button opens a modal with a generic level-by-level list (no Leaflet/india_map.js/
 * searchable_select.js/location_select.js needed any more -- this reuses the exact same location
 * data endpoints those relied on, just rendered as a plain drill-down list instead of a map, which
 * also means "Open board" is now offered at EVERY level reached, not just Earth/Continent/Country).
 *
 * The Admin Queue (citizen reports / ID recovery / queries / council queue) moved from its own
 * top-level tab into this same modal's second sub-tab -- static/js/dashboard.js's own admin-panel
 * code is unchanged, just triggered by this sub-tab opening (window.QMLoadAdminPanel) instead of
 * a tab click.
 *
 * Opened location boards live in a dock OUTSIDE this modal entirely -- a fixed bar at the bottom
 * of the whole page, visible on every dashboard tab (Global/Public/Personal/Private), not just
 * while this modal is open. Each tab holds its own window.QMBoard(root, {pinnedLocation})
 * instance (board.js) -- always read-only, enforced server-side by POST /api/admin/board.
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
  var breadcrumbEl = document.getElementById("qm-explorer-breadcrumb");
  var bodyEl = document.getElementById("qm-explorer-body");

  var dock = document.getElementById("qm-dock");
  var dockBar = document.getElementById("qm-dock-bar");
  var dockToggle = document.getElementById("qm-dock-toggle");
  var dockTabsEl = document.getElementById("qm-dock-tabs");
  var dockPanel = document.getElementById("qm-dock-panel");
  var boardTemplate = document.getElementById("qm-dock-board-template");

  // 2026-10-28 (hardening, prior reported blank-tab bug): `fab` existing doesn't guarantee every
  // other id resolved -- a stale cached copy of this file running against a newer/older
  // dashboard.html is exactly the "missing DOM element" failure mode to guard against. Fail loud
  // to the console rather than throwing out of this IIFE and silently wiring nothing below.
  var required = { modal: modal, paneLocations: paneLocations, paneQueue: paneQueue, breadcrumbEl: breadcrumbEl, bodyEl: bodyEl,
    dock: dock, dockBar: dockBar, dockToggle: dockToggle, dockTabsEl: dockTabsEl, dockPanel: dockPanel, boardTemplate: boardTemplate };
  var missing = Object.keys(required).filter(function (k) { return !required[k]; });
  if (missing.length || !subtabBtns.length) {
    console.error("[explorer] expected element(s) missing -- stale cached JS/HTML? Missing:", missing, "subtabs found:", subtabBtns.length);
    return;
  }
  if (!window.QMBoard) {
    console.error("[explorer] window.QMBoard is missing -- board.js didn't load, or loaded before its own window.QMBoard export was added (stale cache).");
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

  // ==================== Scope + drill-down ====================
  var scope = null;
  var crumbs = []; // [{level, id, name}], crumbs[0] is always scope.root
  var worldData = null, subcontinentData = null, districtsData = null; // fetched once, cached

  function loadScope() {
    breadcrumbEl.innerHTML = "";
    bodyEl.innerHTML = "";
    bodyEl.appendChild(el("p", "qm-dash-empty", "Loading…"));
    api("/api/admin/viewable-locations").then(function (s) {
      scope = s;
      if (scope.scope === "none") { renderLocked(); return; }
      crumbs = [scope.root];
      renderBreadcrumb();
      renderLevel(scope.root);
    }).catch(function (e) {
      bodyEl.innerHTML = "";
      bodyEl.appendChild(el("p", "qm-dash-empty", e.message));
    });
  }

  function renderLocked() {
    bodyEl.innerHTML = "";
    if (scope.reason === "training") {
      bodyEl.appendChild(el("p", "qm-dash-empty",
        "The Explorer opens during your own zodiac month (" + scope.access_window.sign + ", " +
        scope.access_window.opens + " → " + scope.access_window.closes + "). You're training the rest of the year."));
    } else {
      bodyEl.appendChild(el("p", "qm-dash-empty", "The Location Explorer is for Admins and currently-serving council heads."));
    }
  }

  function renderBreadcrumb() {
    breadcrumbEl.innerHTML = "";
    crumbs.forEach(function (c, i) {
      if (i > 0) breadcrumbEl.appendChild(el("span", "qm-explorer-crumb-sep", "›"));
      var btn = el("button", "qm-explorer-crumb" + (i === crumbs.length - 1 ? " is-current" : ""), c.name || c.level);
      btn.type = "button";
      btn.disabled = i === crumbs.length - 1;
      btn.addEventListener("click", function () { crumbs = crumbs.slice(0, i + 1); renderBreadcrumb(); renderLevel(c); });
      breadcrumbEl.appendChild(btn);
    });
  }

  // chainFor(): a present_location-shaped dict built from the CURRENT crumbs trail -- POST
  // /api/admin/board/<level> re-validates this server-side against a freshly recomputed scope, it
  // is never trusted blind just because the explorer itself only lets you reach places scope.root
  // allows browsing.
  function chainFor() {
    var chain = {};
    crumbs.forEach(function (c) { if (c.level !== "earth") chain[c.level] = { id: c.id, name: c.name }; });
    return chain;
  }

  function openBoardBtn(node) {
    var btn = el("button", "qm-btn qm-btn-primary qm-explorer-openbtn", "Open board →");
    btn.type = "button";
    btn.addEventListener("click", function () {
      openDockTab(node.level, chainFor(), node.name || node.level);
      modal.hidden = true;
    });
    return btn;
  }

  function renderLevel(node) {
    bodyEl.innerHTML = "";
    bodyEl.appendChild(el("p", "qm-dash-empty", "Loading…"));
    fetchChildren(node).then(function (children) {
      bodyEl.innerHTML = "";
      bodyEl.appendChild(openBoardBtn(node));
      if (children === null) return; // village: a leaf, nothing deeper to drill
      if (!children.length) { bodyEl.appendChild(el("p", "qm-dash-empty", "Nothing here yet.")); return; }
      var list = el("div", "qm-explorer-list");
      children.forEach(function (child) {
        var row = el("button", "qm-explorer-row", child.name);
        row.type = "button";
        row.addEventListener("click", function () { crumbs.push(child); renderBreadcrumb(); renderLevel(child); });
        list.appendChild(row);
      });
      bodyEl.appendChild(list);
    }).catch(function (e) {
      bodyEl.innerHTML = "";
      bodyEl.appendChild(el("p", "qm-dash-empty", e.message));
    });
  }

  // 2026-10-28: every level's children come from the SAME endpoints the old map-based Founder
  // picker already called -- no new backend tree endpoint, just reorganized into one generic
  // step instead of two separate hardcoded picker flows (Founder-full vs council-flat-list).
  function fetchChildren(node) {
    if (node.level === "village") return Promise.resolve(null);
    if (node.level === "earth" || node.level === "continent") {
      return ensureWorld().then(function (d) {
        if (node.level === "earth") return (d.continents || []).map(function (c) { return { level: "continent", id: c.id, name: c.name }; });
        var cont = (d.continents || []).filter(function (c) { return c.id === node.id; })[0];
        return (cont ? cont.countries : []).map(function (co) { return { level: "country", id: co.id, name: co.name }; });
      });
    }
    if (node.level === "country") {
      return ensureSubcontinent().then(function (d) {
        var country = (d.countries || []).filter(function (c) { return c.id === node.id; })[0];
        // Not one of the 9 Sub-continent countries -- no Zone/State/District/Tehsil/Village data
        // exists for it at all (the data ceiling from the original research); a leaf at Country.
        return country ? (country.zones || []).map(function (z) { return { level: "zone", id: z.id, name: z.name }; }) : [];
      });
    }
    if (node.level === "zone") {
      return ensureSubcontinent().then(function (d) {
        var zone = null;
        (d.countries || []).forEach(function (c) { (c.zones || []).forEach(function (z) { if (z.id === node.id) zone = z; }); });
        return zone ? zone.states.map(function (s) { return { level: "state", id: s.id, name: s.name }; }) : [];
      });
    }
    if (node.level === "state") {
      return ensureDistricts().then(function (d) {
        var entry = d.states[node.id];
        return entry ? entry.districts.map(function (ds) { return { level: "district", id: ds.id, name: ds.name }; }) : [];
      });
    }
    if (node.level === "district") {
      return ensureDistricts().then(function (d) {
        var found = null;
        Object.keys(d.states).forEach(function (sid) { (d.states[sid].districts || []).forEach(function (ds) { if (ds.id === node.id) found = ds; }); });
        return found ? (found.tehsils || []).map(function (t) { return { level: "tehsil", id: t.id, name: t.name }; }) : [];
      });
    }
    if (node.level === "tehsil") {
      return fetch("/api/india-villages/" + encodeURIComponent(node.id)).then(function (r) { return r.json(); })
        .then(function (d) { return (d.villages || []).map(function (v) { return { level: "village", id: v.id, name: v.name }; }); });
    }
    return Promise.resolve([]);
  }
  function ensureWorld() { if (worldData) return Promise.resolve(worldData); return fetch("/api/world-data").then(function (r) { return r.json(); }).then(function (d) { worldData = d; return d; }); }
  function ensureSubcontinent() { if (subcontinentData) return Promise.resolve(subcontinentData); return fetch("/api/subcontinent").then(function (r) { return r.json(); }).then(function (d) { subcontinentData = d; return d; }); }
  function ensureDistricts() { if (districtsData) return Promise.resolve(districtsData); return fetch("/api/subcontinent/districts").then(function (r) { return r.json(); }).then(function (d) { districtsData = d; return d; }); }

  // ==================== Persistent cross-tab dock ====================
  // 2026-10-28: lives outside the Explorer modal and outside every dashboard tab panel -- open
  // boards survive switching to Global/Public/Personal/Private and back, and survive closing this
  // modal. Only the dock BAR is always visible once >=1 tab is open; the board content itself
  // only renders while the dock is expanded (collapsing it doesn't close any tab).
  var dockTabs = []; // [{id, level, label, chain, root, board, loaded}]
  var dockActiveId = null;
  var dockExpanded = false;
  var dockCounter = 0;

  function capFor() { return scope && scope.scope === "global" ? Infinity : 5; }

  function renderDockBar() {
    dock.hidden = dockTabs.length === 0;
    dockTabsEl.innerHTML = "";
    dockTabs.forEach(function (t) {
      var btn = el("button", "qm-dock-tab" + (t.id === dockActiveId ? " is-active" : ""));
      btn.type = "button";
      btn.appendChild(el("span", "", "📍 " + t.label));
      var close = el("span", "qm-dock-tab-close", "✕");
      close.addEventListener("click", function (e) { e.stopPropagation(); closeDockTab(t.id); });
      btn.appendChild(close);
      btn.addEventListener("click", function () { activateDockTab(t.id); setDockExpanded(true); });
      dockTabsEl.appendChild(btn);
    });
  }

  function setDockExpanded(open) {
    dockExpanded = open && dockTabs.length > 0;
    dockPanel.hidden = !dockExpanded;
    dockToggle.textContent = dockExpanded ? "▾" : "▴";
    dockTabs.forEach(function (t) { t.root.hidden = !dockExpanded || t.id !== dockActiveId; });
  }
  dockToggle.addEventListener("click", function () { setDockExpanded(!dockExpanded); });

  function activateDockTab(id) {
    dockActiveId = id;
    dockTabs.forEach(function (t) { t.root.hidden = !dockExpanded || t.id !== id; });
    renderDockBar();
    var t = dockTabs.filter(function (x) { return x.id === id; })[0];
    if (t && !t.loaded) { t.loaded = true; t.board.load(); }
  }

  function closeDockTab(id) {
    var t = dockTabs.filter(function (x) { return x.id === id; })[0];
    if (!t) return;
    t.root.remove();
    dockTabs = dockTabs.filter(function (x) { return x.id !== id; });
    if (dockActiveId === id) dockActiveId = dockTabs.length ? dockTabs[dockTabs.length - 1].id : null;
    renderDockBar();
    if (dockActiveId) activateDockTab(dockActiveId); else setDockExpanded(false);
  }

  function openDockTab(level, chain, label) {
    var existing = dockTabs.filter(function (t) { return t.level === level && (t.chain[level] || {}).id === (chain[level] || {}).id; })[0];
    if (existing) { activateDockTab(existing.id); setDockExpanded(true); return; }
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
    dockTabs.push({ id: id, level: level, label: label, chain: chain, root: root, board: board, loaded: false });
    renderDockBar();
    activateDockTab(id);
    setDockExpanded(true);
  }
})();
