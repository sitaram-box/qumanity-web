/**
 * location_select.js — the redesigned Public Location Selection Tool:
 * a clean, one-step-at-a-time wizard (Zone -> State -> District -> Tehsil
 * -> Village) with a numbered progress header, map+list for Zone/State,
 * search+list for District/Tehsil/Village, and a summary screen with
 * per-level Edit links.
 *
 * Real-data notes (see also india_map.js, scripts/extract_india_districts_
 * tehsils.py, scripts/import_india_villages.py):
 *   - 5 real zones, not 6 — the source has no "North-East" zone; those
 *     states are already part of Central Zone.
 *   - "District"/"Tehsil" are the source's real administrative divisions,
 *     not verified Lok Sabha/Vidhan Sabha constituency data.
 *   - Villages are fetched on demand per tehsil (621,057 nationally —
 *     too many to ship upfront), so the Village step has a brief load.
 *   - The "Location Path" shown in the summary (e.g. CS.DL.1.1.A.5) is
 *     real — it's the actual id chain through the selected levels. It is
 *     NOT the full Private/Account ID string (name initials, gender/age
 *     codes, zodiac codes) — that generator is a separate, later phase.
 *
 * Usage:
 *   var wizard = QMLocationWizard.create(containerEl, {
 *     zonesData: { zones: [...] },        // GET /api/india-states
 *     districtsData: { states: {...} },   // GET /api/india-districts
 *     fetchVillages: function (tehsilId) { return fetch(...).then(r => r.json()); },
 *     onConfirm: function (selection) {},  // selection = {zone,state,district,tehsil,village}
 *     onCancel: function () {},            // "Back to world map" from step 1
 *   });
 *   wizard.reset();
 *   wizard.resize();   // call once the container becomes visible (the embedded map needs this)
 */
(function (global) {
  "use strict";

  var STEPS = [
    { key: "zone", label: "Zone" },
    { key: "state", label: "State" },
    { key: "district", label: "District" },
    { key: "tehsil", label: "Tehsil" },
    { key: "village", label: "Village" },
  ];

  function el(tag, className, text) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (text != null) e.textContent = text;
    return e;
  }

  function create(container, opts) {
    opts = opts || {};
    var zonesData = opts.zonesData || { zones: [] };
    var districtsData = opts.districtsData || { states: {} };
    var fetchVillages = opts.fetchVillages || function () { return Promise.resolve({ villages: [] }); };
    var onConfirm = opts.onConfirm || function () {};
    var onCancel = opts.onCancel || function () {};

    var stepIndex = 0;
    var maxReached = 0;
    var sel = { zone: null, state: null, district: null, tehsil: null, village: null };

    // ---- Build the static skeleton once; never re-set innerHTML on
    // ancestors of the map div again (that would destroy the Leaflet
    // instance) — only toggle [hidden] / populate specific sub-regions. ----
    container.innerHTML =
      '<div class="qm-india-flow-header">' +
      '<p class="qm-picker-eyebrow">India — Public Location Selection Tool</p>' +
      '<button type="button" class="qm-btn qm-btn-ghost" id="qmw-cancel">← Back to world map</button>' +
      "</div>" +
      '<nav class="qm-wizard-steps" id="qmw-steps"></nav>' +
      '<div class="qm-wizard-body">' +
      '<div class="qm-india-map-wrap" id="qmw-map-wrap"><div id="qmw-map"></div></div>' +
      '<div class="qm-wizard-card-list" id="qmw-map-cards"></div>' +
      '<div class="qm-wizard-list-step" id="qmw-list-step" hidden>' +
      '<input type="text" class="qm-wizard-search" id="qmw-search" placeholder="Search…" autocomplete="off" />' +
      '<div class="qm-wizard-card-list qm-wizard-card-list--plain" id="qmw-list"></div>' +
      '<p class="qm-wizard-hint" id="qmw-list-hint"></p>' +
      "</div>" +
      '<div class="qm-wizard-summary" id="qmw-summary" hidden></div>' +
      "</div>" +
      '<div class="qm-wizard-footer" id="qmw-footer">' +
      '<button type="button" class="qm-btn qm-btn-ghost" id="qmw-prev">← Back</button>' +
      '<button type="button" class="qm-btn qm-btn-primary" id="qmw-next" disabled>Next →</button>' +
      "</div>";

    var stepsNav = container.querySelector("#qmw-steps");
    var mapWrap = container.querySelector("#qmw-map-wrap");
    var mapCards = container.querySelector("#qmw-map-cards");
    var listStep = container.querySelector("#qmw-list-step");
    var searchInput = container.querySelector("#qmw-search");
    var listEl = container.querySelector("#qmw-list");
    var listHint = container.querySelector("#qmw-list-hint");
    var summaryEl = container.querySelector("#qmw-summary");
    var footer = container.querySelector("#qmw-footer");
    var prevBtn = container.querySelector("#qmw-prev");
    var nextBtn = container.querySelector("#qmw-next");
    var cancelBtn = container.querySelector("#qmw-cancel");

    cancelBtn.addEventListener("click", function () { onCancel(); });

    var map = QMIndiaMap.create(container.querySelector("#qmw-map"), {
      onStateConfirm: handleMapStateConfirm,
    });
    map.ready.then(function () {
      map.renderLegend(zonesData.zones.map(function (z) { return { name: z.name, color: z.color }; }));
    });

    // ---- Step header ----
    function renderStepsNav() {
      stepsNav.innerHTML = "";
      STEPS.forEach(function (s, i) {
        var btn = el("button", "qm-wizard-step", null);
        btn.type = "button";
        var num = el("span", "qm-wizard-step-num", String(i + 1));
        var label = el("span", "qm-wizard-step-label", s.label);
        btn.appendChild(num);
        btn.appendChild(label);
        btn.classList.toggle("is-active", i === stepIndex);
        btn.classList.toggle("is-done", i < stepIndex || (summaryEl.hidden === false));
        btn.disabled = i > maxReached;
        btn.addEventListener("click", function () { goToStep(i); });
        stepsNav.appendChild(btn);
        if (i < STEPS.length - 1) {
          var conn = el("span", "qm-wizard-connector", null);
          conn.classList.toggle("is-done", i < stepIndex);
          stepsNav.appendChild(conn);
        }
      });
    }

    function clearFrom(stepKey) {
      var idx = STEPS.map(function (s) { return s.key; }).indexOf(stepKey);
      for (var i = idx; i < STEPS.length; i++) sel[STEPS[i].key] = null;
    }

    function goToStep(i) {
      if (i > maxReached) return;
      // Jumping back to edit a step clears everything after it.
      if (i < stepIndex) clearFrom(STEPS[i].key);
      stepIndex = i;
      summaryEl.hidden = true;
      renderCurrentStep();
    }

    // ---- Map-based steps (Zone, State) ----
    function handleMapStateConfirm(stateProps) {
      if (stepIndex === 0) {
        sel.zone = { id: stateProps.qm_zone_id, name: stateProps.qm_zone_name };
        advance();
      } else if (stepIndex === 1) {
        sel.state = { id: stateProps.qm_state_id, name: stateProps.name };
        advance();
      }
    }

    function renderZoneCards() {
      mapCards.innerHTML = "";
      zonesData.zones.forEach(function (z) {
        mapCards.appendChild(makeCard(z.name, function () {
          sel.zone = { id: z.id, name: z.name };
          advance();
        }, z.color));
      });
    }

    function renderStateCards() {
      mapCards.innerHTML = "";
      var zone = zonesData.zones.filter(function (z) { return z.id === sel.zone.id; })[0];
      (zone ? zone.states : []).forEach(function (s) {
        mapCards.appendChild(makeCard(s.name, function () {
          sel.state = { id: s.id, name: s.name };
          advance();
        }, zone.color));
      });
    }

    function makeCard(label, onClick, accentColor) {
      var btn = el("button", "qm-wizard-card", label);
      btn.type = "button";
      if (accentColor) btn.style.borderLeftColor = accentColor;
      btn.addEventListener("click", onClick);
      return btn;
    }

    // ---- List-based steps (District, Tehsil, Village) ----
    var currentListItems = [];
    var listLoading = false;

    function renderListStep(items, onPick, placeholder, emptyMessage) {
      currentListItems = items;
      searchInput.value = "";
      searchInput.placeholder = placeholder;
      searchInput.onclick = null;
      searchInput.oninput = function () { renderListCards(items, onPick, emptyMessage); };
      renderListCards(items, onPick, emptyMessage);
    }

    function renderListCards(items, onPick, emptyMessage) {
      var q = searchInput.value.trim().toLowerCase();
      var filtered = q ? items.filter(function (it) { return it.name.toLowerCase().indexOf(q) !== -1; }) : items;
      var CAP = 200;
      var shown = filtered.slice(0, CAP);

      listEl.innerHTML = "";
      if (listLoading) {
        listHint.textContent = "Loading…";
        return;
      }
      if (items.length === 0) {
        listHint.textContent = emptyMessage || "Nothing found.";
        return;
      }
      shown.forEach(function (it) {
        listEl.appendChild(makeCard(it.name, function () { onPick(it); }));
      });
      if (filtered.length > CAP) {
        listHint.textContent = "Showing " + CAP + " of " + filtered.length + " — keep typing to narrow it down.";
      } else if (filtered.length === 0) {
        listHint.textContent = "No matches for “" + searchInput.value + "”.";
      } else {
        listHint.textContent = filtered.length + " option" + (filtered.length === 1 ? "" : "s") + ".";
      }
    }

    function renderDistrictStep() {
      var stateEntry = districtsData.states[sel.state.id];
      var items = (stateEntry && stateEntry.districts) || [];
      renderListStep(items, function (d) {
        sel.district = { id: d.id, name: d.name };
        advance();
      }, "Search district…", "No district data for this state yet.");
    }

    function renderTehsilStep() {
      var stateEntry = districtsData.states[sel.state.id];
      var district = ((stateEntry && stateEntry.districts) || []).filter(function (d) { return d.id === sel.district.id; })[0];
      var items = (district && district.tehsils) || [];
      renderListStep(items, function (t) {
        sel.tehsil = { id: t.id, name: t.name };
        advance();
      }, "Search tehsil…", "No tehsil data for this district.");
    }

    function renderVillageStep() {
      listLoading = true;
      renderListStep([], function () {}, "Search village…", "");
      fetchVillages(sel.tehsil.id).then(function (data) {
        listLoading = false;
        renderListStep(data.villages || [], function (v) {
          sel.village = { id: v.id, name: v.name };
          advance();
        }, "Search village…", "No village data for this tehsil.");
      }).catch(function () {
        listLoading = false;
        listHint.textContent = "Could not load villages — try again.";
      });
    }

    // ---- Step rendering dispatch ----
    function renderCurrentStep() {
      renderStepsNav();
      summaryEl.hidden = true;
      footer.hidden = false;
      prevBtn.hidden = stepIndex === 0;
      nextBtn.hidden = true; // every step advances via card click, not a separate Next button

      var mapStep = stepIndex === 0 || stepIndex === 1;
      mapWrap.hidden = !mapStep;
      mapCards.hidden = !mapStep;
      listStep.hidden = mapStep;

      if (stepIndex === 0) {
        map.resize();
        map.clearSelection();
        map.setZoneFilter(null);
        renderZoneCards();
      } else if (stepIndex === 1) {
        map.resize();
        map.clearSelection();
        map.setZoneFilter(sel.zone.id);
        renderStateCards();
      } else if (stepIndex === 2) {
        renderDistrictStep();
      } else if (stepIndex === 3) {
        renderTehsilStep();
      } else if (stepIndex === 4) {
        renderVillageStep();
      }
    }

    function advance() {
      if (stepIndex === STEPS.length - 1) {
        showSummary();
        return;
      }
      stepIndex += 1;
      if (stepIndex > maxReached) maxReached = stepIndex;
      renderCurrentStep();
    }

    prevBtn.addEventListener("click", function () {
      if (stepIndex > 0) goToStep(stepIndex - 1);
    });

    // ---- Summary ----
    function locationPath() {
      // Each level's id is already the full hierarchical path (e.g. a
      // village id like "CS.DL.1.1.10" already encodes zone/state/
      // district/tehsil) — the path is just the deepest selected id, not
      // a concatenation of all of them.
      var deepest = sel.village || sel.tehsil || sel.district || sel.state || sel.zone;
      return deepest ? deepest.id : "";
    }

    function showSummary() {
      mapWrap.hidden = true;
      mapCards.hidden = true;
      listStep.hidden = true;
      footer.hidden = true;
      summaryEl.hidden = false;
      renderStepsNav();

      summaryEl.innerHTML = "";
      var title = el("h3", "qm-wizard-summary-title", "Location confirmed");
      summaryEl.appendChild(title);

      var list = el("dl", "qm-wizard-summary-list", null);
      STEPS.forEach(function (s, i) {
        var row = el("div", null, null);
        var dt = el("dt", null, s.label);
        var dd = el("dd", null, sel[s.key] ? sel[s.key].name : "—");
        var editBtn = el("button", "qm-wizard-edit-link", "Edit");
        editBtn.type = "button";
        editBtn.addEventListener("click", function () { goToStep(i); });
        dd.appendChild(editBtn);
        row.appendChild(dt);
        row.appendChild(dd);
        list.appendChild(row);
      });
      summaryEl.appendChild(list);

      var pathP = el("p", "qm-wizard-path", null);
      pathP.innerHTML = "Location path: <code>" + locationPath() + "</code>";
      summaryEl.appendChild(pathP);

      var confirmBtn = el("button", "qm-btn qm-btn-primary", "Confirm & continue →");
      confirmBtn.type = "button";
      confirmBtn.addEventListener("click", function () {
        onConfirm({
          zone: sel.zone, state: sel.state, district: sel.district,
          tehsil: sel.tehsil, village: sel.village, path: locationPath(),
        });
      });
      summaryEl.appendChild(confirmBtn);
    }

    // ---- Public API ----
    function reset() {
      stepIndex = 0;
      maxReached = 0;
      sel = { zone: null, state: null, district: null, tehsil: null, village: null };
      summaryEl.hidden = true;
      map.reset();
      renderCurrentStep();
    }

    function resize() { map.resize(); }
    function destroy() { map.destroy(); container.innerHTML = ""; }

    renderCurrentStep();

    return { reset: reset, resize: resize, destroy: destroy };
  }

  global.QMLocationWizard = { create: create };
})(window);
