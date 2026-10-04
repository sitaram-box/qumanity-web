/**
 * elements-dashboard.js — Elemental Dashboard (Part 7): a location-level
 * selector over /api/global/elements' all_locations list, plus the
 * current + upcoming lunar timeline from /api/lunar/phase.
 */
(function () {
  "use strict";

  var levelSelect = document.getElementById("location-level");
  var cardsEl = document.getElementById("dashboard-cards");
  var emptyEl = document.getElementById("dashboard-empty");

  var allLocations = [];

  // Deep-link from the homepage scoreboard: ?level=zone&id=IND/CS&name=Central%20State --
  // pre-select that level and highlight+scroll to the matching card once rendered.
  var params = new URLSearchParams(location.search);
  var targetLevel = params.get("level");
  var targetId = params.get("id");
  var targetName = params.get("name");
  if (targetLevel) levelSelect.value = targetLevel;

  function renderCards(level) {
    var rows = allLocations.filter(function (r) { return r.location_type === level; });
    cardsEl.innerHTML = "";
    emptyEl.hidden = rows.length !== 0;

    rows.forEach(function (r) {
      var card = document.createElement("div");
      card.className = "el-card";
      var isTarget = targetLevel === level && targetId === r.location_id;
      if (isTarget) card.className += " el-card--target";

      var h3 = document.createElement("h3");
      h3.textContent = isTarget && targetName ? targetName : r.location_id;
      var sub = document.createElement("p");
      sub.className = "el-card-sub";
      sub.textContent = r.total_users + " user" + (r.total_users === 1 ? "" : "s") + " registered";
      card.appendChild(h3);
      card.appendChild(sub);

      [
        ["fire", "Fire", r.fire_count, r.fire_percentage],
        ["earth", "Earth", r.earth_count, r.earth_percentage],
        ["air", "Air", r.air_count, r.air_percentage],
        ["water", "Water", r.water_count, r.water_percentage],
      ].forEach(function (row) {
        var div = document.createElement("div");
        div.className = "el-stat-row";
        div.innerHTML =
          '<span><span class="el-dot dot--' + row[0] + '"></span>' + row[1] + "</span>" +
          "<span>" + row[2] + " (" + row[3] + "%)</span>";
        card.appendChild(div);
      });

      cardsEl.appendChild(card);
    });
    var target = cardsEl.querySelector(".el-card--target");
    if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  levelSelect.addEventListener("change", function () { renderCards(levelSelect.value); });

  function loadElements() {
    fetch("/api/global/elements")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        allLocations = data.all_locations || [];
        renderCards(levelSelect.value);
      })
      .catch(function (err) { console.error("Failed to load elemental data", err); });
  }

  function loadLunar() {
    fetch("/api/lunar/phase")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var c = data.current;
        document.getElementById("lunar-current").textContent =
          "Current phase: " + c.phase_name + " (" + Math.round(c.illuminated_fraction * 100) + "% illuminated)";

        var list = document.getElementById("lunar-upcoming");
        list.innerHTML = "";
        (data.upcoming || []).forEach(function (e) {
          var li = document.createElement("li");
          li.innerHTML =
            '<span class="le-type">' + e.event_type + (e.zodiac_sign ? " · " + e.zodiac_sign : "") + "</span>" +
            '<span class="le-date">' + e.date + (e.time ? " " + e.time + " UTC" : "") + "</span>";
          list.appendChild(li);
        });
      })
      .catch(function (err) { console.error("Failed to load lunar data", err); });
  }

  loadElements();
  loadLunar();
})();
