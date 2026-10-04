/**
 * scoreboard.js — homepage India live scoreboard (Zones + top States ranked by member count).
 * Shared data source (/api/scoreboard/india) with the phone app's own equivalent screen.
 */
(function () {
  "use strict";

  var totalEl = document.getElementById("sb-total-count");
  var zonesList = document.getElementById("sb-zones-list");
  var statesList = document.getElementById("sb-states-list");
  var statesMore = document.getElementById("sb-states-more");
  if (!totalEl) return;

  function fmt(n) { return n.toLocaleString("en-US"); }

  function countUp(el, target) {
    var start = null, dur = 1200;
    function step(ts) {
      if (start === null) start = ts;
      var t = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = fmt(Math.round(target * eased));
      if (t < 1) requestAnimationFrame(step);
    }
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = fmt(target);
    } else {
      requestAnimationFrame(step);
    }
  }

  function renderList(container, rows, level) {
    container.innerHTML = "";
    var max = rows.length ? rows[0].total_users || 1 : 1;
    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.className = "hm-sb-row";
      var a = document.createElement("a");
      a.className = "hm-sb-link";
      a.href = "/elements?level=" + encodeURIComponent(level) + "&id=" + encodeURIComponent(row.id) + "&name=" + encodeURIComponent(row.name);

      var rank = document.createElement("span");
      rank.className = "hm-sb-rank";
      rank.textContent = row.rank;
      a.appendChild(rank);

      var mid = document.createElement("span");
      mid.className = "hm-sb-mid";
      var name = document.createElement("span");
      name.className = "hm-sb-name";
      name.textContent = row.name;
      var track = document.createElement("span");
      track.className = "hm-sb-track";
      var fill = document.createElement("span");
      fill.className = "hm-sb-fill";
      fill.style.width = Math.max(4, Math.round(100 * (row.total_users || 0) / max)) + "%";
      track.appendChild(fill);
      mid.appendChild(name);
      mid.appendChild(track);
      a.appendChild(mid);

      var count = document.createElement("span");
      count.className = "hm-sb-count";
      count.textContent = fmt(row.total_users || 0) + " member" + (row.total_users === 1 ? "" : "s");
      a.appendChild(count);

      li.appendChild(a);
      container.appendChild(li);
    });
  }

  fetch("/api/scoreboard/india")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      countUp(totalEl, data.total_members || 0);
      renderList(zonesList, data.zones || [], "zone");
      renderList(statesList, data.states || [], "state");
      if (data.states_total_count > (data.states || []).length) {
        statesMore.hidden = false;
        statesMore.textContent = "+ " + (data.states_total_count - data.states.length) + " more States";
      }
    })
    .catch(function (err) { console.error("Failed to load the India scoreboard", err); });
})();
