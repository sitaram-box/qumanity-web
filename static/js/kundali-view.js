/**
 * kundali-view.js — the "private account kundali view" (Part 10 checklist
 * item): fetches a previously-registered user's saved kundali and renders
 * it, independent of the registration wizard's in-memory state.
 */
(function () {
  "use strict";

  fetch("/api/user/zodiac/" + window.QM_USER_ID)
    .then(function (r) { return r.json(); })
    .then(function (z) {
      document.getElementById("k-sun-sign").textContent = z.sun_sign;
      document.getElementById("k-sun-element").textContent = z.sun_element;
      document.getElementById("k-moon-sign").textContent = z.moon_sign;
      document.getElementById("k-moon-nakshatra").textContent = z.moon_nakshatra;
      document.getElementById("k-ascendant").textContent = z.ascendant_sign;
      document.getElementById("k-summary-text").textContent = z.kundali_summary;

      var list = document.getElementById("k-planetary-list");
      list.innerHTML = "";
      Object.keys(z.planetary_positions || {}).forEach(function (name) {
        var p = z.planetary_positions[name];
        var li = document.createElement("li");
        li.textContent = name + ": " + p.sign + " (" + p.degree + "°)";
        list.appendChild(li);
      });

      var precision = z.birth_chart && z.birth_chart.ephemeris ? z.birth_chart.ephemeris.location_precision : null;
      document.getElementById("k-precision-note").textContent = precision
        ? "Ascendant & houses used a " + precision.replace(/_/g, " ") + " birth location — approximate, not your exact birthplace."
        : "";
    })
    .catch(function (err) {
      console.error("Failed to load kundali", err);
    });
})();
