/**
 * home_stats_carousel.js — the homepage's Statistics Carousel (2026-10-28 redesign).
 *
 * Earth + the Indian Sub-continent total + each of its 9 countries, as a horizontal-scroll row
 * of live counts. Every endpoint here is PUBLIC (no login) and already backs the #live section
 * further down the page (/api/earth/stats, /api/subcontinent/stats, /api/country/stats/<id>) --
 * this is a second, scannable presentation of the same data, not a new data source.
 *
 * Clicking a card never opens a competing view: it scrolls to #live and drives that section's
 * OWN existing controls (earth.js's switchTab()/showCountryStats(), triggered here by setting
 * #qm-dd-country's value and dispatching its real "change" event) -- a logged-out visitor has no
 * per-location "board" to open, so "see more detail" means the detailed stats panel that's
 * already built, not a second one.
 */
(function () {
  "use strict";

  var carousel = document.getElementById("hm-stats-carousel");
  if (!carousel) return;

  function card(name, count, label) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "hm-carousel-card";
    var nameEl = document.createElement("span");
    nameEl.className = "hm-carousel-card-name";
    nameEl.textContent = name;
    var countEl = document.createElement("span");
    countEl.className = "hm-carousel-card-count";
    countEl.textContent = (count || 0).toLocaleString();
    var labelEl = document.createElement("span");
    labelEl.className = "hm-carousel-card-label";
    labelEl.textContent = label;
    btn.appendChild(nameEl);
    btn.appendChild(countEl);
    btn.appendChild(labelEl);
    return btn;
  }

  function scrollToLive() {
    var live = document.getElementById("live");
    if (live) live.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function openEarthOrSub() {
    scrollToLive();
    var tabSub = document.getElementById("qm-tab-sub");
    if (tabSub) tabSub.click();
  }

  function openCountry(countryId) {
    scrollToLive();
    var dd = document.getElementById("qm-dd-country");
    if (!dd) return;
    dd.value = countryId;
    dd.dispatchEvent(new Event("change"));
  }

  Promise.all([
    fetch("/api/earth/stats").then(function (r) { return r.json(); }),
    fetch("/api/subcontinent/stats").then(function (r) { return r.json(); }),
    fetch("/api/world-data").then(function (r) { return r.json(); }),
  ]).then(function (results) {
    var earth = results[0], subcontinent = results[1], world = results[2];
    carousel.innerHTML = "";

    var earthCard = card("Earth", earth.total_humans, "Humans");
    earthCard.addEventListener("click", openEarthOrSub);
    carousel.appendChild(earthCard);

    var subCard = card(window.QMSubcontinent ? window.QMSubcontinent.NAME : "Indian Sub-continent", subcontinent.total_humans, "Humans");
    subCard.addEventListener("click", openEarthOrSub);
    carousel.appendChild(subCard);

    var codes = (window.QMSubcontinent && window.QMSubcontinent.CODES) || [];
    var countries = [];
    (world.continents || []).forEach(function (c) {
      (c.countries || []).forEach(function (co) {
        if (codes.indexOf(co.code) !== -1) countries.push(co);
      });
    });
    // India first (the one country everyone already expects to see), then the rest as given.
    countries.sort(function (a, b) { return (a.code === "IND" ? -1 : b.code === "IND" ? 1 : 0); });

    countries.forEach(function (country) {
      fetch("/api/country/stats/" + encodeURIComponent(country.id))
        .then(function (r) { return r.json(); })
        .then(function (stats) {
          var c = card(country.name, stats.total_humans, "Humans");
          c.addEventListener("click", function () { openCountry(country.id); });
          carousel.appendChild(c);
        })
        .catch(function () {});
    });
  }).catch(function () {
    carousel.innerHTML = "";
    var note = document.createElement("p");
    note.className = "hm-fine hm-carousel-loading";
    note.textContent = "Live statistics are unavailable right now.";
    carousel.appendChild(note);
  });
})();
