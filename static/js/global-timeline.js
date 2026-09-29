/**
 * global-timeline.js — fetches placeholder Global Timeline data and
 * renders the sidebar stat panel. Also exposes window.QM_GLOBAL_DATA
 * so earth.js can plot continents/countries once loaded.
 */
(function () {
  "use strict";

  function fmt(n) {
    return typeof n === "number" ? n.toLocaleString("en-IN") : n;
  }

  function renderStats(data) {
    var stats = data.global_timeline_stats;
    var list = document.getElementById("qm-stat-list");
    var rows = [
      ["Continents mapped", stats.continents_mapped],
      ["Countries mapped", stats.countries_mapped],
      ["Countries onboarded", stats.countries_onboarded],
      ["Zones (India)", stats.zones],
      ["States", stats.states],
      ["Districts", stats.districts],
      ["Tehsils", stats.tehsils],
      ["Villages", fmt(stats.villages)],
    ];
    list.innerHTML = rows
      .map(function (r) {
        return (
          '<div class="qm-stat"><dt>' + r[0] + "</dt><dd>" + r[1] + "</dd></div>"
        );
      })
      .join("");

    document.getElementById("qm-timeline-note").textContent = stats.note || "";
  }

  fetch("/api/global-data")
    .then(function (res) { return res.json(); })
    .then(function (data) {
      window.QM_GLOBAL_DATA = data;
      renderStats(data);
      window.dispatchEvent(new CustomEvent("qm:global-data-ready", { detail: data }));
    })
    .catch(function (err) {
      console.error("Failed to load global timeline data", err);
      document.getElementById("qm-timeline-note").textContent =
        "Could not load Global Timeline data.";
    });
})();
