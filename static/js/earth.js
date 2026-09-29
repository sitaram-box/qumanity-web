/**
 * earth.js — homepage controller for the Indian Sub-continent view.
 *
 * The map is one 3D globe locked to the Sub-continent (India, Nepal, Bhutan,
 * Bangladesh, Myanmar, Sri Lanka, Pakistan, Balochistan, Afghanistan), shown
 * as a single highlighted region with no inner borders and no whole-Earth
 * view (see subcontinent.js). The right-hand panel's two tabs show
 * registered-user stats for the whole Sub-continent, or for one of its 9
 * countries picked from the Country dropdown. India is the one country that
 * swaps the globe for its dedicated zone/state map (QMIndiaMap); the thumbnail
 * returns to the Sub-continent globe.
 */
(function () {
  "use strict";

  // ---- DOM refs ----
  var earthSlot = document.getElementById("qm-earth-slot");
  var countrySlot = document.getElementById("qm-country-slot");
  var earthThumb = document.getElementById("qm-earth-thumb");
  var canvas = document.getElementById("earth-canvas");
  var tooltip = document.getElementById("qm-tooltip");
  var resetBtn = document.getElementById("reset-view-btn");
  var breadcrumb = document.getElementById("qm-breadcrumb");
  var countryIndiaMapEl = document.getElementById("qm-country-india-map");
  var ddCountry = document.getElementById("qm-dd-country");

  var tabSub = document.getElementById("qm-tab-sub");
  var tabCountry = document.getElementById("qm-tab-country");
  var subView = document.getElementById("qm-sub-view");
  var countryView = document.getElementById("qm-country-stats-view");
  var countryPlaceholder = document.getElementById("qm-country-placeholder");
  var countryContent = document.getElementById("qm-country-content");
  var csName = document.getElementById("qm-country-stats-name");

  var GENDER_LABELS = { male: "Male", female: "Female", both: "Third gender" };

  // ---- State ----
  var worldData = null;
  var indiaMap = null;

  var globe = QMEarthGlobe.create(canvas, QMSubcontinent.globeOptions({
    tooltipEl: tooltip,
    // The hero stage is squarer than the registration one -- stand back a bit so Afghanistan and Maldives fit.
    lockRegion: Object.assign({}, QMSubcontinent.LOCK, { distance: 11.6, minDistance: 9, maxDistance: 13.5 }),
    onCountryPick: handleGlobePick,
  }));

  // ---- Map level: the Sub-continent globe, or India's own state map ----
  function showMapLevel(level) {
    earthSlot.hidden = level !== "earth";
    countrySlot.hidden = level !== "india";
    earthThumb.hidden = level === "earth";
    if (level === "earth") globe.resize();
    else if (indiaMap) indiaMap.resize();
  }
  earthThumb.addEventListener("click", function () {
    showMapLevel("earth");
    setBreadcrumb(null);
    switchTab("sub");
  });

  function setBreadcrumb(countryName) {
    breadcrumb.textContent = countryName ? QMSubcontinent.NAME + " › " + countryName : QMSubcontinent.NAME;
  }

  // ---- Tabs ----
  function switchTab(name) {
    tabSub.classList.toggle("is-active", name === "sub");
    tabCountry.classList.toggle("is-active", name === "country");
    subView.hidden = name !== "sub";
    countryView.hidden = name !== "country";
  }
  tabSub.addEventListener("click", function () { switchTab("sub"); });
  tabCountry.addEventListener("click", function () { switchTab("country"); });

  // ---- Stats rendering ----
  // Proportional bar rows (label · bar · count) instead of a plain list.
  function renderStatRows(container, pairs) {
    container.innerHTML = "";
    var total = pairs.reduce(function (sum, p) { return sum + p[1]; }, 0);
    pairs.forEach(function (pair) {
      var pct = total > 0 ? Math.round((pair[1] / total) * 100) : 0;
      var row = document.createElement("div");
      row.className = "hm-bar";
      var label = document.createElement("span");
      label.className = "hm-bar-label";
      label.textContent = pair[0];
      var track = document.createElement("div");
      track.className = "hm-bar-track";
      var fill = document.createElement("div");
      fill.className = "hm-bar-fill";
      fill.style.width = pct + "%";
      track.appendChild(fill);
      var value = document.createElement("span");
      value.className = "hm-bar-value";
      value.textContent = pair[1];
      row.appendChild(label);
      row.appendChild(track);
      row.appendChild(value);
      container.appendChild(row);
    });
  }

  function renderRegisteredStats(stats, prefix) {
    document.getElementById(prefix + "-total").textContent = stats.total_humans;
    var emptyNote = document.getElementById(prefix + "-empty-note");
    if (emptyNote) emptyNote.hidden = stats.total_humans !== 0;
    renderStatRows(document.getElementById(prefix + "-gender-list"), Object.keys(stats.gender).map(function (g) {
      return [GENDER_LABELS[g] || g, stats.gender[g]];
    }));
    renderStatRows(document.getElementById(prefix + "-age-list"), stats.age_bands.map(function (b) { return [b.label, b.count]; }));
    renderStatRows(document.getElementById(prefix + "-element-list"), Object.keys(stats.elements).map(function (e) { return [e, stats.elements[e]]; }));
    renderStatRows(document.getElementById(prefix + "-sign-list"), Object.keys(stats.signs).map(function (s) { return [s, stats.signs[s]]; }));
  }

  function loadSubcontinentStats() {
    fetch("/api/subcontinent/stats")
      .then(function (res) { return res.json(); })
      .then(function (stats) { renderRegisteredStats(stats, "qm-sub"); })
      .catch(function (err) { console.error("Failed to load Sub-continent stats", err); });
  }

  function showCountryStats(country) {
    countryPlaceholder.hidden = true;
    countryContent.hidden = false;
    csName.textContent = country.name;
    fetch("/api/country/stats/" + encodeURIComponent(country.id))
      .then(function (res) { return res.json(); })
      .then(function (stats) {
        document.getElementById("qm-cs-total").textContent = stats.total_humans;
        document.getElementById("qm-country-empty-note").hidden = stats.total_humans !== 0;
        renderStatRows(document.getElementById("qm-country-gender-list"), Object.keys(stats.gender).map(function (g) {
          return [GENDER_LABELS[g] || g, stats.gender[g]];
        }));
        renderStatRows(document.getElementById("qm-country-age-list"), stats.age_bands.map(function (b) { return [b.label, b.count]; }));
        renderStatRows(document.getElementById("qm-country-element-list"), Object.keys(stats.elements).map(function (e) { return [e, stats.elements[e]]; }));
        renderStatRows(document.getElementById("qm-country-sign-list"), Object.keys(stats.signs).map(function (s) { return [s, stats.signs[s]]; }));
      })
      .catch(function (err) { console.error("Failed to load country stats", err); });
  }

  // ---- Country selection (the 9 Sub-continent countries) ----
  function findWorldEntryByCode(code) {
    for (var i = 0; i < worldData.continents.length; i++) {
      var c = worldData.continents[i];
      for (var j = 0; j < c.countries.length; j++) {
        if (c.countries[j].code === code) return c.countries[j];
      }
    }
    return null;
  }

  function populateCountryDropdown() {
    ddCountry.innerHTML = '<option value="">Select a country…</option>';
    QMSubcontinent.CODES.forEach(function (code) {
      var country = findWorldEntryByCode(code);
      if (!country) return;
      var opt = document.createElement("option");
      opt.value = country.id;
      opt.textContent = country.name;
      ddCountry.appendChild(opt);
    });
  }

  function ensureIndiaMap() {
    if (indiaMap) return;
    indiaMap = QMIndiaMap.create(countryIndiaMapEl, {});
  }

  ddCountry.addEventListener("change", function () {
    if (!ddCountry.value) return;
    var country = null;
    QMSubcontinent.CODES.forEach(function (code) {
      var c = findWorldEntryByCode(code);
      if (c && c.id === ddCountry.value) country = c;
    });
    if (!country) return;
    if (country.code === "IND") {
      ensureIndiaMap();
      showMapLevel("india");
    } else {
      showMapLevel("earth");
    }
    setBreadcrumb(country.name);
    switchTab("country");
    showCountryStats(country);
  });

  function handleGlobePick(feature) {
    if (feature && feature.properties.qm_country_id === "SUBCONTINENT") switchTab("sub");
  }

  resetBtn.addEventListener("click", function () {
    globe.resetView();
    setBreadcrumb(null);
    showMapLevel("earth");
    switchTab("sub");
  });

  // ---- Data ----
  QMSubcontinent.loadData().then(function (data) { QMSubcontinent.apply(globe, data); })
    .catch(function (err) { console.error("Failed to load Sub-continent map", err); });
  fetch("/api/world-data").then(function (r) { return r.json(); }).then(function (data) {
    worldData = data;
    populateCountryDropdown();
  }).catch(function (err) { console.error("Failed to load world data", err); });

  loadSubcontinentStats();
})();
