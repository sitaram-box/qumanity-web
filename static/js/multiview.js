/**
 * multiview.js — Founder/Council "monitor other locations" dashboard tab (2026-10-28).
 *
 * Only ever loaded for is_admin_panel_user (dashboard.html's own gate, same context var
 * qm-dash-admin already uses) -- a Founder (scope "global") can open any location Earth down to
 * Village (India/Sub-continent only reaches real Village data -- elsewhere stops at Country, the
 * data ceiling documented in the research); a currently-serving village council head (scope
 * "limited") can open sibling villages in their own Tehsil, but only during their own birth
 * sign's month (GET /api/admin/viewable-locations' own access_window, re-checked every time this
 * tab opens or the "+ Open location" picker is used -- never cached across a session).
 *
 * Each open location is a tab holding its own window.QMBoard(root, {pinnedLocation}) instance
 * (board.js) -- the exact same board() macro/rendering every real Global/Public board uses,
 * always read-only (app.py's POST /api/admin/board forces that server-side, this file never
 * re-implements or trusts a client-side copy of that rule).
 */
(function () {
  "use strict";

  var panel = document.getElementById("qm-dash-multiview");
  if (!panel) return; // not is_admin_panel_user -- the tab/markup don't exist on this page at all

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function api(url, body) {
    var opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }

  var mainEl = document.getElementById("qm-mv-main");
  var tabbarEl = document.getElementById("qm-mv-tabbar");
  var addTabBtn = document.getElementById("qm-mv-add-tab");
  var pickerModal = document.getElementById("qm-mv-picker-modal");
  var pickerBody = document.getElementById("qm-mv-picker-body");
  var boardTemplate = document.getElementById("qm-mv-board-template");

  pickerModal.addEventListener("click", function (e) {
    if (e.target === pickerModal || e.target.hasAttribute("data-close")) pickerModal.hidden = true;
  });

  var scope = null;          // last-fetched GET /api/admin/viewable-locations result
  var tabs = [];              // [{id, level, label, present_location, root, board}]
  var activeTabId = null;
  var initialized = false;
  var tabCounter = 0;

  function capFor(s) { return s && s.scope === "global" ? Infinity : 5; }

  // ---- Tab bar -------------------------------------------------------------------------------
  function renderTabBar() {
    Array.prototype.slice.call(tabbarEl.querySelectorAll(".qm-mv-tab:not(.qm-mv-tab-add)")).forEach(function (b) { b.remove(); });
    tabs.forEach(function (t) {
      var btn = el("button", "qm-mv-tab" + (t.id === activeTabId ? " is-active" : ""));
      btn.type = "button";
      btn.appendChild(el("span", "", "📍 " + t.label));
      var close = el("span", "qm-mv-tab-close", "✕");
      close.addEventListener("click", function (e) { e.stopPropagation(); closeTab(t.id); });
      btn.appendChild(close);
      btn.addEventListener("click", function () { activateTab(t.id); });
      tabbarEl.insertBefore(btn, addTabBtn);
    });
    addTabBtn.title = tabs.length >= capFor(scope) ? "You've reached your open-location limit" : "";
  }

  function activateTab(id) {
    activeTabId = id;
    tabs.forEach(function (t) { t.root.hidden = t.id !== id; });
    renderTabBar();
    var t = tabs.filter(function (x) { return x.id === id; })[0];
    if (t && !t.loaded) { t.loaded = true; t.board.load(); }
  }

  function closeTab(id) {
    var t = tabs.filter(function (x) { return x.id === id; })[0];
    if (!t) return;
    t.root.remove();
    tabs = tabs.filter(function (x) { return x.id !== id; });
    if (activeTabId === id) activeTabId = tabs.length ? tabs[tabs.length - 1].id : null;
    renderMain();
    renderTabBar();
  }

  function renderMain() {
    if (!tabs.length) {
      mainEl.innerHTML = "";
      mainEl.appendChild(el("p", "qm-dash-empty", "No location open yet — use “+ Open location” below to start monitoring one."));
    }
  }

  function openTab(level, presentLocation, label) {
    if (tabs.length >= capFor(scope)) { alert("You can have at most " + capFor(scope) + " locations open at once — close one first."); return; }
    var existing = tabs.filter(function (t) { return t.level === level && (t.present_location[level] || {}).id === (presentLocation[level] || {}).id; })[0];
    if (existing) { activateTab(existing.id); pickerModal.hidden = true; return; }

    tabCounter += 1;
    var id = "qm-mv-tab-" + tabCounter;
    var frag = boardTemplate.content.cloneNode(true);
    var root = frag.querySelector(".bd");
    root.id = id + "-board";
    root.setAttribute("data-level", level);
    root.hidden = true;
    if (mainEl.querySelector(".qm-dash-empty")) mainEl.innerHTML = "";
    mainEl.appendChild(root);

    var board = window.QMBoard(root, { pinnedLocation: presentLocation });
    tabs.push({ id: id, level: level, label: label, present_location: presentLocation, root: root, board: board, loaded: false });
    renderTabBar();
    activateTab(id);
    pickerModal.hidden = true;
  }

  // ---- Picker: Founder (scope "global") ------------------------------------------------------
  function renderFounderPicker() {
    pickerBody.innerHTML = "";
    pickerBody.appendChild(el("h3", "", "Open a location"));

    var quickRow = el("div", "qm-mv-quickrow");
    quickRow.appendChild(el("span", "", "Open directly: "));
    var earthBtn = el("button", "qm-btn qm-btn-ghost", "🌍 Earth"); earthBtn.type = "button";
    earthBtn.addEventListener("click", function () { openTab("earth", {}, "Earth"); });
    quickRow.appendChild(earthBtn);
    pickerBody.appendChild(quickRow);

    var countrySelect = document.createElement("select");
    countrySelect.id = "qm-mv-country-select";
    var allCountries = []; // [{id, name, continent: {id, name}}]
    var subcontinentIds = {};

    var countryStep = el("div", "qm-mv-picker-step");
    countryStep.appendChild(el("p", "qm-form-section-title", "Continent / Country"));
    countryStep.appendChild(countrySelect);
    var countryActions = el("div", "qm-mv-quickrow");
    var openContinentBtn = el("button", "qm-btn qm-btn-ghost", "Open Continent board"); openContinentBtn.type = "button"; openContinentBtn.disabled = true;
    var openCountryBtn = el("button", "qm-btn qm-btn-ghost", "Open Country board"); openCountryBtn.type = "button"; openCountryBtn.disabled = true;
    countryActions.appendChild(openContinentBtn);
    countryActions.appendChild(openCountryBtn);
    countryStep.appendChild(countryActions);
    var countryNote = el("p", "qm-dash-empty", "");
    countryStep.appendChild(countryNote);
    pickerBody.appendChild(countryStep);

    var wizardHost = el("div", "qm-mv-wizard-host");
    wizardHost.hidden = true;
    pickerBody.appendChild(wizardHost);
    var wizard = null;

    Promise.all([
      fetch("/api/world-data").then(function (r) { return r.json(); }),
      fetch("/api/subcontinent").then(function (r) { return r.json(); }),
    ]).then(function (results) {
      var world = results[0], subcontinent = results[1];
      (world.continents || []).forEach(function (c) {
        (c.countries || []).forEach(function (co) {
          allCountries.push({ id: co.id, name: co.name, continent: { id: c.id, name: c.name } });
        });
      });
      (subcontinent.countries || []).forEach(function (c) { subcontinentIds[c.id] = c; });

      allCountries.sort(function (a, b) { return a.name.localeCompare(b.name); });
      allCountries.forEach(function (c) {
        var opt = document.createElement("option");
        opt.value = c.id; opt.textContent = c.name + (subcontinentIds[c.id] ? " ★" : "");
        countrySelect.appendChild(opt);
      });
      if (window.QMSearchableSelect) window.QMSearchableSelect.enhance(countrySelect, { placeholder: "Search a country…" });

      countrySelect.addEventListener("change", function () {
        var country = allCountries.filter(function (c) { return c.id === countrySelect.value; })[0];
        openContinentBtn.disabled = !country;
        openCountryBtn.disabled = !country;
        wizardHost.hidden = true;
        if (wizard) { wizard.destroy(); wizard = null; }
        if (!country) { countryNote.textContent = ""; return; }

        openContinentBtn.onclick = function () { openTab("continent", { continent: country.continent }, country.continent.name); };
        openCountryBtn.onclick = function () { openTab("country", { continent: country.continent, country: { id: country.id, name: country.name } }, country.name); };

        var scData = subcontinentIds[country.id];
        if (!scData) {
          countryNote.textContent = "★ marks the 9 countries with real Zone/State/District/Tehsil/Village data. " +
            country.name + " isn't one of them yet — you can still monitor it at the Country level above.";
          return;
        }
        countryNote.textContent = "";
        wizardHost.hidden = false;
        wizard = window.QMLocationWizard.create(wizardHost, {
          zonesData: { zones: scData.zones },
          districtsData: window.__qmMvSubcontinentDistricts,
          fetchVillages: function (tehsilId) { return fetch("/api/india-villages/" + encodeURIComponent(tehsilId)).then(function (r) { return r.json(); }); },
          onConfirm: function (selection) {
            openTab("village", {
              continent: country.continent, country: { id: country.id, name: country.name },
              zone: selection.zone, state: selection.state, district: selection.district,
              tehsil: selection.tehsil, village: selection.village,
            }, selection.village.name);
          },
          onCancel: function () { wizardHost.hidden = true; wizard.destroy(); wizard = null; },
        });
        wizard.resize();
      });
    }).catch(function () { countryNote.textContent = "Could not load the country list — try again."; });

    pickerModal.hidden = false;
  }

  // ---- Picker: council member (scope "limited") -----------------------------------------------
  function renderCouncilPicker() {
    pickerBody.innerHTML = "";
    pickerBody.appendChild(el("h3", "", "Open a village in " + scope.parent.name));
    pickerBody.appendChild(el("p", "qm-dash-empty",
      "You can monitor other villages inside your own Tehsil while your own zodiac month is open " +
      "(" + scope.access_window.sign + ", " + scope.access_window.opens + " → " + scope.access_window.closes + ")."));

    var select = document.createElement("select");
    (scope.locations || []).forEach(function (loc) {
      var opt = document.createElement("option");
      opt.value = loc.id; opt.textContent = loc.name + (loc.is_own ? " (yours)" : "");
      select.appendChild(opt);
    });
    pickerBody.appendChild(select);
    if (window.QMSearchableSelect) window.QMSearchableSelect.enhance(select, { placeholder: "Search a village…" });

    var openBtn = el("button", "qm-btn qm-btn-primary", "Open board →");
    openBtn.type = "button";
    openBtn.addEventListener("click", function () {
      var loc = scope.locations.filter(function (l) { return l.id === select.value; })[0];
      if (!loc) return;
      openTab("village", { tehsil: scope.parent, village: { id: loc.id, name: loc.name } }, loc.name);
    });
    pickerBody.appendChild(openBtn);
    pickerModal.hidden = false;
  }

  function renderLockedState(reason) {
    mainEl.innerHTML = "";
    if (reason === "training") {
      mainEl.appendChild(el("p", "qm-dash-empty",
        "Multi-view opens during your own zodiac month (" + scope.access_window.sign + ", " +
        scope.access_window.opens + " → " + scope.access_window.closes + "). You're training the rest of the year."));
    } else {
      mainEl.appendChild(el("p", "qm-dash-empty", "Multi-view is for Admins and currently-serving council heads."));
    }
    addTabBtn.hidden = true;
  }

  function openPicker() {
    if (!scope) return;
    if (scope.scope === "global") renderFounderPicker();
    else if (scope.scope === "limited") renderCouncilPicker();
  }
  addTabBtn.addEventListener("click", openPicker);

  function init() {
    if (initialized) return;
    initialized = true;
    mainEl.innerHTML = "";
    mainEl.appendChild(el("p", "qm-dash-empty", "Loading…"));
    Promise.all([
      api("/api/admin/viewable-locations"),
      fetch("/api/subcontinent/districts").then(function (r) { return r.json(); }),
    ]).then(function (results) {
      scope = results[0];
      window.__qmMvSubcontinentDistricts = results[1];
      if (scope.scope === "none") renderLockedState(scope.reason);
      else renderMain();
    }).catch(function (e) {
      mainEl.innerHTML = "";
      mainEl.appendChild(el("p", "qm-dash-empty", e.message));
    });
  }

  document.querySelector('.qm-dash-tab[data-tab="multiview"]').addEventListener("click", init);
})();
