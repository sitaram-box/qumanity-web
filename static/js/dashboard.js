/**
 * dashboard.js — 4-tab dashboard shell + Edit Profile request queueing.
 *
 * Private is fully built out; Global/Public have real sub-tabs wired to
 * the user's present location (Earth/Continent/Country and Zone/State/
 * District/Tehsil/Village respectively, via /api/location/stats/<level>/
 * <id>?basis=present — see app.py); Personal is an honest "Coming Soon"
 * placeholder, matching Karma Summary/Recent Activities' same pattern
 * elsewhere on this page (no backing system built for either yet).
 */
(function () {
  "use strict";

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }

  var tabs = Array.prototype.slice.call(document.querySelectorAll(".qm-dash-tab"));
  var panels = {
    private: document.getElementById("qm-dash-private"),
    personal: document.getElementById("qm-dash-personal"),
    public: document.getElementById("qm-dash-public"),
    global: document.getElementById("qm-dash-global"),
  };

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var name = tab.getAttribute("data-tab");
      tabs.forEach(function (t) { t.classList.toggle("is-active", t === tab); });
      Object.keys(panels).forEach(function (key) {
        var panel = panels[key];
        if (panel) panel.hidden = key !== name;
      });
    });
  });

  // ---- Global / Public sub-tabs -- same registered-user demographics
  // shape/rendering the homepage's Earth/Continent/Country tabs already
  // use (see earth.js's renderRegisteredStats/renderStatRows), just a
  // page-local copy since these DOM refs and IDs are dashboard-specific. ----
  var GENDER_LABELS = { male: "Male", female: "Female", both: "Third gender" };

  function renderProgressRows(container, pairs) {
    container.innerHTML = "";
    var total = pairs.reduce(function (sum, p) { return sum + p[1]; }, 0);
    pairs.forEach(function (pair) {
      var pct = total > 0 ? Math.round((pair[1] / total) * 100) : 0;
      var row = document.createElement("div");
      row.className = "qm-stat-row";

      var label = document.createElement("span");
      label.className = "qm-stat-row-label";
      label.textContent = pair[0];

      var barWrap = document.createElement("div");
      barWrap.className = "qm-stat-row-bar";
      var barFill = document.createElement("div");
      barFill.className = "qm-stat-row-bar-fill";
      barFill.style.width = pct + "%";
      barWrap.appendChild(barFill);

      var value = document.createElement("span");
      value.className = "qm-stat-row-value";
      value.textContent = pair[1];

      row.appendChild(label);
      row.appendChild(barWrap);
      row.appendChild(value);
      container.appendChild(row);
    });
  }

  function renderRegisteredStats(prefix, stats) {
    var totalEl = document.getElementById(prefix + "-total");
    if (!totalEl) return;
    totalEl.textContent = stats.total_humans;
    var emptyNote = document.getElementById(prefix + "-empty-note");
    if (emptyNote) emptyNote.hidden = stats.total_humans !== 0;
    renderProgressRows(document.getElementById(prefix + "-gender-list"), Object.keys(stats.gender).map(function (g) {
      return [GENDER_LABELS[g] || g, stats.gender[g]];
    }));
    renderProgressRows(document.getElementById(prefix + "-age-list"), stats.age_bands.map(function (b) { return [b.label, b.count]; }));
    renderProgressRows(document.getElementById(prefix + "-element-list"), Object.keys(stats.elements).map(function (e) { return [e, stats.elements[e]]; }));
    renderProgressRows(document.getElementById(prefix + "-sign-list"), Object.keys(stats.signs).map(function (s) { return [s, stats.signs[s]]; }));
  }

  function loadStatsFor(prefix, url) {
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (stats) { renderRegisteredStats(prefix, stats); })
      .catch(function (err) { console.error("Failed to load dashboard stats from " + url, err); });
  }

  function loadWalletBalanceFor(prefix, locationType, locationId) {
    var el = document.getElementById(prefix + "-wallet");
    if (!el) return;
    fetch("/api/wallet/balance/" + locationType + "/" + encodeURIComponent(locationId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        // 2026-10-27: qoin_count is the PUBLIC figure every viewer gets back (board_core.py's own
        // board header already keys off it, never the private balance_qoins -- council/admin
        // only, and simply absent from this response for anyone else, which is why this used to
        // render the literal string "undefined Qoins"). 1 Qoin = ₹1 flat (wallet_core.py), so
        // the currency value is the identical number, just relabeled.
        var n = data.qoin_count || 0;
        el.textContent = n.toLocaleString() + " Qoins ≈ ₹" + n.toLocaleString() + ".00";
      })
      .catch(function (err) { console.error("Failed to load wallet balance for " + prefix, err); });
  }

  function loadCollectiveKarmaFor(prefix, locationType, locationId) {
    var el = document.getElementById(prefix + "-karma");
    if (!el) return;
    fetch("/api/karma/collective/" + locationType + "/" + encodeURIComponent(locationId))
      .then(function (r) { return r.json(); })
      .then(function (data) { el.textContent = data.points; })
      .catch(function (err) { console.error("Failed to load collective karma for " + prefix, err); });
  }

  // ==================== Detailed Stats modal (2026-10-27) ====================
  // The "📊 Stats" button on a board used to just scroll to this same data already loading,
  // cramped, in the permanent explorer sidebar (qm-dp-stats/qm-dg-stats) -- it still does that
  // job for the explorer tree itself, untouched. This is a SEPARATE, spacious view of the exact
  // same three endpoints (loadStatsFor/loadWalletBalanceFor/loadCollectiveKarmaFor, reused
  // unchanged -- they're already generic over `prefix`), reusing the `stat_block` Jinja macro a
  // second time with prefix "qm-stats-modal" so no new rendering code was needed, just a new
  // target.
  var statsModal = document.getElementById("qm-stats-modal");
  if (statsModal) {
    statsModal.addEventListener("click", function (e) {
      if (e.target === statsModal || e.target.hasAttribute("data-close")) statsModal.hidden = true;
    });
  }

  function openStatsModal(level, locationId, name) {
    if (!statsModal) return;
    document.getElementById("qm-stats-modal-heading").textContent = name ? "📊 " + name : "Statistics";
    // stat_block's Announcements/Report Inbox sections are only ever populated by board.js's
    // renderAnnouncements()/renderReportInbox(), which are hardcoded to the sidebar's own two
    // prefixes -- nothing fills them in for this modal's prefix, so they'd just sit empty
    // forever. Hidden here rather than shown stale, keeping this view to the five items it's
    // actually for (the explorer sidebar still carries both, unaffected).
    ["announce", "reportinbox"].forEach(function (s) {
      var section = document.getElementById("qm-stats-modal-" + s + "-section");
      if (section) section.hidden = true;
    });
    statsModal.hidden = false;
    // "earth" has its own dedicated endpoint (no karma/wallet-shape difference -- just not part
    // of _LOCATION_STATS_LEVELS in app.py, the same special case renderGlobalExplorer() already
    // carves out for the sidebar version of this exact data).
    var statsUrl = level === "earth" ? "/api/earth/stats" : "/api/location/stats/" + level + "/" + encodeURIComponent(locationId) + "?basis=present";
    loadStatsFor("qm-stats-modal", statsUrl);
    loadWalletBalanceFor("qm-stats-modal", level, locationId);
    loadCollectiveKarmaFor("qm-stats-modal", level, locationId);
  }
  window.QMOpenStatsModal = openStatsModal;

  // ==================== Location explorer (Global / Public tabs) ====================
  // A left-sidebar tree scoped to the user's own present-location lineage
  // (siblings at each level, not a free-roam browser of the whole Earth --
  // see docs/DASHBOARD_REDESIGN_PLAN.md). Reuses the same static JSON
  // endpoints register.js's own location pickers already consume; the one
  // per-tehsil village fetch stays lazy (fetched on expand/on root load),
  // everything else is fetched once and cached.
  var presentLocation = window.QM_PRESENT_LOCATION || {};
  var pilotVillageId = window.QM_PILOT_VILLAGE_ID || "";
  var worldData = null, indiaStates = null, indiaDistricts = null;
  // The 9 Indian Sub-continent countries have a Public timeline (zones down to
  // villages); indiaStates/indiaDistricts hold all of them, zones tagged with
  // their country_id.
  var SUBCONTINENT_CODES = ["IND", "NPL", "BTN", "BGD", "MMR", "LKA", "PAK", "BLC", "AFG", "MDV"];
  // Mirrors perception_core.SUBCONTINENT_COUNTRY_IDS / app.SUBCONTINENT_COUNTRY_IDS -- Country
  // Perception is only offered for these 10, matching the Founder's own UI scoping.
  var PERCEPTION_COUNTRY_IDS = [
    "O_AS_IND", "O_AS_NPL", "O_AS_BTN", "O_AS_BGD", "O_AS_MMR",
    "O_AS_LKA", "O_AS_PAK", "O_AS_BLC", "O_AS_AFG", "O_AS_MDV",
  ];
  var INDIA_COUNTRY_ID = "O_AS_IND";

  function loadTreeData() {
    var needsWorld = !!document.getElementById("global-explorer-tree");
    var needsIndia = !!document.getElementById("public-explorer-tree") ||
      (needsWorld && presentLocation.country && SUBCONTINENT_CODES.indexOf(presentLocation.country.code) !== -1);
    var jobs = [];
    if (needsWorld) jobs.push(fetch("/api/world-data").then(function (r) { return r.json(); }).then(function (d) { worldData = d; }));
    if (needsIndia) {
      jobs.push(fetch("/api/subcontinent").then(function (r) { return r.json(); }).then(function (d) {
        indiaStates = { zones: [] };
        d.countries.forEach(function (country) {
          country.zones.forEach(function (zone) {
            indiaStates.zones.push(Object.assign({ country_id: country.id }, zone));
          });
        });
      }));
      jobs.push(fetch("/api/subcontinent/districts").then(function (r) { return r.json(); }).then(function (d) { indiaDistricts = d; }));
    }
    return Promise.all(jobs);
  }

  function findContinentById(id) {
    return (worldData.continents || []).filter(function (c) { return c.id === id; })[0] || null;
  }
  function findZoneById(id) {
    return (indiaStates.zones || []).filter(function (z) { return z.id === id; })[0] || null;
  }
  function findDistrictById(stateId, districtId) {
    var stateData = indiaDistricts.states[stateId];
    if (!stateData) return null;
    return (stateData.districts || []).filter(function (d) { return d.id === districtId; })[0] || null;
  }

  // ---- Generic tree node: a toggle (if it has children) + a selectable
  // label. Children are built lazily on first expand -- getChildren may
  // return an array (already-cached data) or a Promise (the one live
  // per-tehsil village fetch). ----
  function buildNode(tab, label, onSelect, getChildren, depth) {
    var li = document.createElement("li");
    li.className = "qm-explorer-node";

    var row = document.createElement("div");
    row.className = "qm-explorer-row";
    row.style.paddingLeft = (depth * 14) + "px";

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "qm-explorer-toggle";

    var labelBtn = document.createElement("button");
    labelBtn.type = "button";
    labelBtn.className = "qm-explorer-label";
    labelBtn.textContent = label;

    var childList = document.createElement("ul");
    childList.className = "qm-explorer-tree";
    childList.hidden = true;
    var expanded = false, loaded = false;

    if (getChildren) {
      toggle.textContent = "▸";
      toggle.addEventListener("click", function () {
        if (!loaded) {
          loaded = true;
          var result = getChildren();
          var apply = function (items) { items.forEach(function (node) { childList.appendChild(node.li); }); };
          if (result && typeof result.then === "function") result.then(apply);
          else apply(result);
        }
        expanded = !expanded;
        childList.hidden = !expanded;
        toggle.textContent = expanded ? "▾" : "▸";
      });
    } else {
      toggle.disabled = true;
    }

    labelBtn.addEventListener("click", function () {
      var container = document.getElementById(tab + "-explorer-tree");
      Array.prototype.slice.call(container.querySelectorAll(".qm-explorer-label.is-active")).forEach(function (b) {
        b.classList.remove("is-active");
      });
      labelBtn.classList.add("is-active");
      onSelect();
    });

    row.appendChild(toggle);
    row.appendChild(labelBtn);
    li.appendChild(row);
    li.appendChild(childList);
    return { li: li, labelBtn: labelBtn };
  }

  function villageNode(tab, village, depth) {
    return buildNode(tab, village.name, function () { selectLocation(tab, "village", village.id, village.name); }, null, depth);
  }
  function tehsilNode(tab, tehsil, depth) {
    return buildNode(tab, tehsil.name, function () { selectLocation(tab, "tehsil", tehsil.id, tehsil.name); }, function () {
      return fetch("/api/india-villages/" + encodeURIComponent(tehsil.id))
        .then(function (r) { return r.json(); })
        .then(function (data) { return (data.villages || []).map(function (v) { return villageNode(tab, v, depth + 1); }); });
    }, depth);
  }
  // A district's children: its tehsils, plus any villages that hang straight
  // off it (some countries have no tehsil tier there) -- fetched on demand.
  function districtChildren(tab, district, depth) {
    var tehsilNodes = (district.tehsils || []).map(function (t) { return tehsilNode(tab, t, depth); });
    if (!district.direct_villages) return tehsilNodes;
    return fetch("/api/india-villages/" + encodeURIComponent(district.id))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        return tehsilNodes.concat((data.villages || []).map(function (v) { return villageNode(tab, v, depth); }));
      });
  }
  function districtNode(tab, district, depth) {
    return buildNode(tab, district.name, function () { selectLocation(tab, "district", district.id, district.name); }, function () {
      return districtChildren(tab, district, depth + 1);
    }, depth);
  }
  function stateNode(tab, state, depth) {
    return buildNode(tab, state.name, function () { selectLocation(tab, "state", state.id, state.name); }, function () {
      var stateData = indiaDistricts.states[state.id];
      return (stateData ? stateData.districts : []).map(function (d) { return districtNode(tab, d, depth + 1); });
    }, depth);
  }
  function countryLeafNode(tab, country, depth) {
    return buildNode(tab, country.name, function () { selectLocation(tab, "country", country.id, country.name); }, null, depth);
  }
  function continentNode(tab, continent, depth) {
    return buildNode(tab, continent.name, function () { selectLocation(tab, "continent", continent.id, continent.name); }, function () {
      return (continent.countries || []).map(function (c) { return countryLeafNode(tab, c, depth + 1); });
    }, depth);
  }

  function renderTreeRoot(containerId, nodes, emptyMessage) {
    var container = document.getElementById(containerId);
    container.innerHTML = "";
    Array.prototype.forEach.call(container.parentElement.querySelectorAll(".qm-explorer-note"), function (n) { n.remove(); });
    if (!nodes.length) {
      if (!emptyMessage) return;
      var note = document.createElement("p");
      note.className = "qm-explorer-note";
      note.textContent = emptyMessage;
      container.parentElement.insertBefore(note, container);
      return;
    }
    nodes.forEach(function (node) { container.appendChild(node.li); });
  }

  function renderGlobalExplorer(root) {
    if (root === "earth") {
      renderTreeRoot("global-explorer-tree", (worldData.continents || []).map(function (c) { return continentNode("global", c, 0); }), "No continents available.");
      loadStatsFor("qm-dg-stats", "/api/earth/stats");
      loadWalletBalanceFor("qm-dg-stats", "earth", "EARTH");
      loadCollectiveKarmaFor("qm-dg-stats", "earth", "EARTH");
      document.getElementById("qm-dg-stats-heading").textContent = "🌍 Earth statistics";
    } else if (root === "continent") {
      var continent = presentLocation.continent && findContinentById(presentLocation.continent.id);
      renderTreeRoot("global-explorer-tree", continent ? continent.countries.map(function (c) { return countryLeafNode("global", c, 0); }) : [], "Continent not set.");
      if (presentLocation.continent) selectLocation("global", "continent", presentLocation.continent.id, presentLocation.continent.name);
    } else if (root === "country") {
      if (presentLocation.country && SUBCONTINENT_CODES.indexOf(presentLocation.country.code) !== -1) {
        renderTreeRoot("global-explorer-tree", (indiaStates.zones || []).filter(function (z) {
          return z.country_id === presentLocation.country.id;
        }).map(function (z) {
          return buildNode("global", z.name, function () { selectLocation("global", "zone", z.id, z.name); }, function () {
            return (z.states || []).map(function (s) { return stateNode("global", s, 1); });
          }, 0);
        }), "No zones available.");
      } else {
        renderTreeRoot("global-explorer-tree", [], "No further breakdown available for this country.");
      }
      if (presentLocation.country) selectLocation("global", "country", presentLocation.country.id, presentLocation.country.name);
    }
  }

  function renderPublicExplorer(root) {
    var p = presentLocation;
    if (root === "zone" && p.zone) {
      var zone = findZoneById(p.zone.id);
      renderTreeRoot("public-explorer-tree", zone ? zone.states.map(function (s) { return stateNode("public", s, 0); }) : [], "Zone not found.");
      selectLocation("public", "zone", p.zone.id, p.zone.name);
    } else if (root === "state" && p.state) {
      var stateData = indiaDistricts.states[p.state.id];
      renderTreeRoot("public-explorer-tree", stateData ? stateData.districts.map(function (d) { return districtNode("public", d, 0); }) : [], "State not found.");
      selectLocation("public", "state", p.state.id, p.state.name);
    } else if (root === "district" && p.district) {
      var district = findDistrictById(p.state.id, p.district.id);
      if (district) {
        Promise.resolve(districtChildren("public", district, 0)).then(function (nodes) {
          renderTreeRoot("public-explorer-tree", nodes, "No tehsils or villages found.");
        });
      } else {
        renderTreeRoot("public-explorer-tree", [], "District not found.");
      }
      selectLocation("public", "district", p.district.id, p.district.name);
    } else if (root === "tehsil" && p.tehsil) {
      document.getElementById("public-explorer-tree").innerHTML = "";
      fetch("/api/india-villages/" + encodeURIComponent(p.tehsil.id))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          renderTreeRoot("public-explorer-tree", (data.villages || []).map(function (v) { return villageNode("public", v, 0); }), "No villages found.");
        });
      selectLocation("public", "tehsil", p.tehsil.id, p.tehsil.name);
    } else if (root === "village" && p.village) {
      renderTreeRoot("public-explorer-tree", [], "");
      selectLocation("public", "village", p.village.id, p.village.name);
    }
  }

  function wireRootTabs(groupId, onPick) {
    var group = document.getElementById(groupId);
    if (!group) return;
    var buttons = Array.prototype.slice.call(group.querySelectorAll(".qm-panel-tab"));
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.disabled) return;
        buttons.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
        onPick(btn.getAttribute("data-root"));
      });
    });
  }

  function selectLocation(tab, level, id, name) {
    var prefix = tab === "global" ? "qm-dg-stats" : "qm-dp-stats";
    document.getElementById(prefix + "-heading").textContent = name ? "📊 " + name : "Statistics";
    loadStatsFor(prefix, "/api/location/stats/" + level + "/" + encodeURIComponent(id) + "?basis=present");
    loadWalletBalanceFor(prefix, level, id);
    loadCollectiveKarmaFor(prefix, level, id);
    if (tab === "public") {
      var isVillage = level === "village";
      var mc = document.getElementById("qm-village-members-card"); if (mc) mc.hidden = !isVillage;
      document.getElementById("qm-elections-card").hidden = !(isVillage && id === pilotVillageId);
      if (isVillage && document.getElementById("qm-village-member-list")) loadVillageMembers(id);

      var zoneCard = document.getElementById("qm-perception-zone-card");
      if (zoneCard) {
        var zone = level === "zone" ? findZoneById(id) : null;
        if (zone && zone.country_id === INDIA_COUNTRY_ID) {
          zoneCard.hidden = false;
          currentZonePerceptionId = id;
          loadZonePerception(id, name);
        } else {
          zoneCard.hidden = true;
        }
      }
    }
    if (tab === "global") {
      var countryCard = document.getElementById("qm-perception-country-card");
      if (countryCard) {
        if (level === "country" && PERCEPTION_COUNTRY_IDS.indexOf(id) !== -1) {
          countryCard.hidden = false;
          currentCountryPerceptionId = id;
          loadCountryPerception(id, name);
        } else {
          countryCard.hidden = true;
        }
      }
    }
  }

  // ---- Perception Calculator (annual Pro/Anti sentiment, see docs/perception_calculator.md) ----
  function renderPerception(prefix, name, data) {
    document.getElementById(prefix + "-name").textContent = name;
    document.getElementById(prefix + "-year").textContent = data.voting_year;
    var resultsBox = document.getElementById(prefix + "-results");
    if (!data.results_visible) {
      if (resultsBox) { resultsBox.hidden = true; }
      var hiddenNote = document.getElementById(prefix + "-hidden-note");
      if (hiddenNote) { hiddenNote.hidden = false; hiddenNote.textContent = "📊 " + (data.results_reason || "Results are not shown yet."); }
    } else {
      if (resultsBox) { resultsBox.hidden = false; }
      var hiddenNote2 = document.getElementById(prefix + "-hidden-note");
      if (hiddenNote2) { hiddenNote2.hidden = true; }
      var total = data.pro_count + data.anti_count;
      var proPct = total > 0 ? Math.round((data.pro_count / total) * 100) : 0;
      var antiPct = total > 0 ? Math.round((data.anti_count / total) * 100) : 0;
      document.getElementById(prefix + "-pro-bar").style.width = proPct + "%";
      document.getElementById(prefix + "-anti-bar").style.width = antiPct + "%";
      document.getElementById(prefix + "-pro-count").textContent = data.pro_count;
      document.getElementById(prefix + "-anti-count").textContent = data.anti_count;
    }

    var voteBlock = document.getElementById(prefix + "-vote-block");
    var note = document.getElementById(prefix + "-note");
    if (data.my_vote) {
      voteBlock.hidden = true;
      note.textContent = "You voted " + data.my_vote + " this year.";
    } else if (data.can_vote) {
      voteBlock.hidden = false;
      note.textContent = "";
    } else {
      voteBlock.hidden = true;
      note.textContent = data.vote_reason || "";
    }
  }

  function loadCountryPerception(countryId, name) {
    fetch("/api/perception/country/" + encodeURIComponent(countryId))
      .then(function (r) { return r.json(); })
      .then(function (data) { renderPerception("qm-perception-country", name, data); })
      .catch(function (err) { console.error("Failed to load country perception", err); });
  }

  function loadZonePerception(zoneId, name) {
    fetch("/api/perception/zone/" + encodeURIComponent(zoneId))
      .then(function (r) { return r.json(); })
      .then(function (data) { renderPerception("qm-perception-zone", name, data); })
      .catch(function (err) { console.error("Failed to load zone perception", err); });
  }

  function wirePerceptionVoting(prefix, kind, getCurrentId) {
    var block = document.getElementById(prefix + "-vote-block");
    if (!block) return;
    block.querySelectorAll("button[data-vote]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = getCurrentId();
        if (!id) return;
        fetch("/api/perception/" + kind + "/" + encodeURIComponent(id) + "/vote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ vote: btn.getAttribute("data-vote") }),
        })
          .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
          .then(function (result) {
            if (!result.ok) throw new Error(result.body.error || "Could not cast Perception vote");
            var name = document.getElementById(prefix + "-name").textContent;
            if (kind === "country") loadCountryPerception(id, name); else loadZonePerception(id, name);
          })
          .catch(function (err) { alert(err.message); });
      });
    });
  }
  var currentCountryPerceptionId = null, currentZonePerceptionId = null;
  wirePerceptionVoting("qm-perception-country", "country", function () { return currentCountryPerceptionId; });
  wirePerceptionVoting("qm-perception-zone", "zone", function () { return currentZonePerceptionId; });

  // ---- Village member directory + profile popup (privacy-scoped: name/
  // gender/age category only, see /api/location/members/village in app.py). ----
  var villageMembersCache = [];
  function loadVillageMembers(villageId) {
    fetch("/api/location/members/village/" + encodeURIComponent(villageId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        villageMembersCache = data.members || [];
        renderVillageMembers(villageMembersCache);
      })
      .catch(function (err) { console.error("Failed to load village members", err); });
  }
  function renderVillageMembers(members) {
    var list = document.getElementById("qm-village-member-list");
    var empty = document.getElementById("qm-village-members-empty");
    list.innerHTML = "";
    empty.hidden = members.length !== 0;
    members.forEach(function (m) {
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "qm-member-row";
      btn.innerHTML = m.name + ' <span class="qm-member-meta">(' + m.gender + ", " + m.age_category + ")</span>";
      btn.addEventListener("click", function () { openMemberPopup(m); });
      li.appendChild(btn);
      list.appendChild(li);
    });
  }
  var memberSearch = document.getElementById("qm-village-search");
  if (memberSearch) {
    memberSearch.addEventListener("input", function () {
      var q = memberSearch.value.trim().toLowerCase();
      renderVillageMembers(!q ? villageMembersCache : villageMembersCache.filter(function (m) {
        return m.name.toLowerCase().indexOf(q) !== -1;
      }));
    });
  }

  var memberPopup = document.createElement("div");
  memberPopup.className = "qm-gate-message qm-edit-modal";
  memberPopup.hidden = true;
  memberPopup.innerHTML =
    '<h3 id="qm-member-popup-name"></h3>' +
    '<p id="qm-member-popup-meta"></p>' +
    '<div class="qm-member-popup-actions">' +
    '<button type="button" class="qm-btn qm-btn-ghost" disabled>✉️ Send Message</button>' +
    '<button type="button" class="qm-btn qm-btn-ghost" disabled>🤝 Add Friend</button>' +
    '<button type="button" class="qm-btn qm-btn-ghost" disabled>👪 Add Family</button>' +
    '<p class="qm-member-popup-note">Coming soon — Message Box &amp; connections ship in a later update.</p>' +
    '</div>' +
    '<div class="qm-summary-actions" style="margin-top:14px;"><button type="button" class="qm-btn qm-btn-ghost" id="qm-member-popup-close">Close</button></div>';
  document.body.appendChild(memberPopup);
  memberPopup.querySelector("#qm-member-popup-close").addEventListener("click", function () { memberPopup.hidden = true; });

  function openMemberPopup(member) {
    memberPopup.querySelector("#qm-member-popup-name").textContent = member.name;
    memberPopup.querySelector("#qm-member-popup-meta").textContent = member.gender + " · " + member.age_category;
    memberPopup.hidden = false;
  }

  if (document.getElementById("global-explorer-tree") || document.getElementById("public-explorer-tree")) {
    loadTreeData().then(function () {
      if (document.getElementById("global-explorer-tree")) {
        wireRootTabs("global-root-tabs", renderGlobalExplorer);
        renderGlobalExplorer("earth");
      }
      if (document.getElementById("public-explorer-tree")) {
        wireRootTabs("public-root-tabs", renderPublicExplorer);
        renderPublicExplorer("zone");
      }
    }).catch(function (err) { console.error("Failed to load dashboard explorer data", err); });
  }

  // ---- Edit Profile -> queued change request (no auto-apply; see app.py) ----
  var editBtn = document.getElementById("edit-profile-btn");
  var editModal = document.getElementById("edit-profile-modal");
  var editForm = document.getElementById("edit-profile-form");
  var editCancel = document.getElementById("edit-profile-cancel");
  var editError = document.getElementById("edit-profile-error");
  var editSuccess = document.getElementById("edit-profile-success");

  editBtn.addEventListener("click", function () {
    editError.hidden = true;
    editSuccess.hidden = true;
    editModal.hidden = false;
  });
  editCancel.addEventListener("click", function () { editModal.hidden = true; });

  editForm.addEventListener("submit", function (e) {
    e.preventDefault();
    editError.hidden = true;
    editSuccess.hidden = true;

    fetch("/api/dashboard/edit-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("edit-name").value.trim(),
        middle_name: document.getElementById("edit-middle-name").value.trim(),
        email: document.getElementById("edit-email").value.trim(),
        phone: document.getElementById("edit-phone").value.trim(),
        reason: document.getElementById("edit-reason").value.trim(),
      }),
    })
      .then(function (res) {
        return res.json().then(function (body) { return { ok: res.ok, body: body }; });
      })
      .then(function (result) {
        if (!result.ok) throw new Error(result.body.error || "Could not queue request");
        editSuccess.hidden = false;
      })
      .catch(function (err) {
        editError.textContent = err.message;
        editError.hidden = false;
      });
  });

  // ---- Profile picture (2026-10-20): self-service, uploads immediately -- unlike Edit Profile
  // above, this never goes through council approval (see profile_picture_core.py). ----
  var avatarInput = document.getElementById("pv-avatar-input");
  var avatarUploadBtn = document.getElementById("pv-avatar-upload-btn");
  var avatarEl = document.getElementById("pv-avatar");
  var avatarInitialEl = document.getElementById("pv-avatar-initial");
  var avatarErrorEl = document.getElementById("pv-avatar-error");
  if (avatarUploadBtn) {
    avatarUploadBtn.addEventListener("click", function () { avatarInput.click(); });
    avatarInput.addEventListener("change", function () {
      var file = avatarInput.files[0];
      if (!file) return;
      avatarErrorEl.hidden = true;
      var formData = new FormData();
      formData.append("picture", file);
      avatarUploadBtn.disabled = true;
      fetch("/api/profile/picture", { method: "POST", body: formData })
        .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
        .then(function (result) {
          avatarUploadBtn.disabled = false;
          if (!result.ok) throw new Error(result.body.error || "Could not upload picture");
          avatarEl.style.backgroundImage = "url('/api/users/" + QM_USER_ID + "/profile-picture?v=" + Date.now() + "')";
          avatarInitialEl.hidden = true;
        })
        .catch(function (err) {
          avatarUploadBtn.disabled = false;
          avatarErrorEl.textContent = err.message;
          avatarErrorEl.hidden = false;
        });
    });
  }

  // ---- Qoins Wallet (Private tab) ----
  var walletBalanceEl = document.getElementById("qm-wallet-balance");

  function loadWallet() {
    if (!walletBalanceEl) return;
    fetch("/api/wallet/balance")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        walletBalanceEl.textContent = data.balance_qoins;
        document.getElementById("qm-wallet-locked-note").hidden = !data.has_locked_share;
        var list = document.getElementById("qm-wallet-tx-list");
        var empty = document.getElementById("qm-wallet-tx-empty");
        list.innerHTML = "";
        empty.hidden = data.transactions.length !== 0;
        var REASON_LABELS = {
          donation_self: "Your donation share", donation_referrer: "Referral reward",
          donation_location: "Location donation share", admin_adjustment: "Admin adjustment",
        };
        data.transactions.forEach(function (tx) {
          var li = document.createElement("li");
          var sign = tx.amount_qoins >= 0 ? "+" : "";
          li.textContent = sign + tx.amount_qoins + " Qoins — " + (REASON_LABELS[tx.reason] || tx.reason) +
            (tx.locked ? " (locked)" : "");
          list.appendChild(li);
        });
      })
      .catch(function (err) { console.error("Failed to load wallet", err); });
  }
  loadWallet();

  // ---- Your Karma (Private tab) — a Social Credit score, never money, separate from Qoins ----
  var karmaTotalEl = document.getElementById("qm-karma-total");

  function loadKarma() {
    if (!karmaTotalEl) return;
    fetch("/api/karma/me")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        karmaTotalEl.textContent = data.score.total;
        document.getElementById("qm-karma-commercial").textContent = data.score.commercial;
        document.getElementById("qm-karma-noncommercial").textContent = data.score.noncommercial;
        var list = document.getElementById("qm-karma-history-list");
        var empty = document.getElementById("qm-karma-history-empty");
        list.innerHTML = "";
        (data.history || []).forEach(function (entry) {
          var li = document.createElement("li");
          var sign = entry.points >= 0 ? "+" : "";
          li.textContent = sign + entry.points + " — " + entry.reason;
          list.appendChild(li);
        });
        empty.hidden = (data.history || []).length !== 0;
      })
      .catch(function (err) { console.error("Failed to load karma", err); });
  }
  loadKarma();

  var karmaHistoryBtn = document.getElementById("qm-karma-history-btn");
  if (karmaHistoryBtn) {
    karmaHistoryBtn.addEventListener("click", function () {
      var list = document.getElementById("qm-karma-history-list");
      var empty = document.getElementById("qm-karma-history-empty");
      var showing = !list.hidden;
      list.hidden = showing;
      empty.hidden = showing || list.children.length !== 0;
    });
  }

  // ---- Village Council Elections (Public → Village sub-tab) ----
  var electionsCard = document.getElementById("qm-elections-card");
  var lastElectionEligibility = null;

  function loadElectionCandidates() {
    fetch("/api/election/candidates")
      .then(function (r) { return r.json(); })
      .then(function (candidates) {
        var container = document.getElementById("qm-election-candidates");
        var empty = document.getElementById("qm-election-candidates-empty");
        container.innerHTML = "";
        if (candidates.restricted) {
          empty.hidden = false;
          empty.textContent = candidates.your_sign
            ? "This cycle's candidates are only shown to members born under " + candidates.cycle_sign + "."
            : "Sign in to see this cycle's candidates.";
          return;
        }
        var total = (candidates.male || []).length + (candidates.female || []).length;
        empty.hidden = total !== 0;
        empty.textContent = "No approved candidates yet.";

        ["male", "female"].forEach(function (gender) {
          (candidates[gender] || []).forEach(function (c) {
            var row = document.createElement("div");
            row.className = "qm-candidate-row";
            var karmaTotal = c.karma ? c.karma.total : 0;
            var report = document.createElement("div");
            report.className = "qm-candidate-report";
            var head = document.createElement("strong");
            head.textContent = c.name;
            report.appendChild(head);
            report.appendChild(document.createTextNode(
              " (" + gender + ") · Karma Score: " + karmaTotal
            ));
            var dl = document.createElement("dl");
            [
              ["Why running", c.form_reason || c.manifest || ""],
              ["Why vote for me", c.form_why_vote || ""],
              ["What I'll change", c.form_changes || ""],
            ].concat(c.form_past_work ? [["Past work", c.form_past_work]] : [])
              .forEach(function (pair) {
                var dt = document.createElement("dt");
                dt.textContent = pair[0];
                var dd = document.createElement("dd");
                dd.textContent = pair[1];
                dl.appendChild(dt);
                dl.appendChild(dd);
              });
            report.appendChild(dl);
            row.appendChild(report);

            var eligibility = lastElectionEligibility;
            var canVote = eligibility && eligibility.can_vote && eligibility.voted_genders.indexOf(gender) === -1;
            if (canVote) {
              var btn = document.createElement("button");
              btn.type = "button";
              btn.className = "qm-btn qm-btn-ghost";
              btn.textContent = "Vote";
              btn.addEventListener("click", function () {
                fetch("/api/election/vote", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ candidate_user_id: c.user_id, gender: gender }),
                })
                  .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
                  .then(function (result) {
                    if (!result.ok) throw new Error(result.body.error || "Could not vote");
                    loadElectionStatus();
                    loadElectionCandidates();
                    loadElectionSummary();
                  })
                  .catch(function (err) { alert(err.message); });
              });
              row.appendChild(btn);
            }
            container.appendChild(row);
          });
        });
      })
      .catch(function (err) { console.error("Failed to load candidates", err); });
  }

  function loadElectionCouncil() {
    fetch("/api/election/council")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var list = document.getElementById("qm-election-council");
        var empty = document.getElementById("qm-election-council-empty");
        list.innerHTML = "";
        empty.hidden = data.council.length !== 0;
        data.council.forEach(function (seat) {
          var li = document.createElement("li");
          li.textContent = seat.zodiac_sign + " " + seat.year + " — Nayak: " +
            (seat.male_head_name || "—") + ", Nayika: " + (seat.female_head_name || "—") +
            " (" + seat.term_status + ")";
          list.appendChild(li);
        });
      })
      .catch(function (err) { console.error("Failed to load council", err); });
  }

  function loadElectionStatus() {
    fetch("/api/election/status")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        lastElectionEligibility = data.eligibility;
        document.getElementById("qm-election-sign").textContent = data.cycle.zodiac_sign + " (" + data.cycle.element + ")";
        document.getElementById("qm-election-phase").textContent = data.cycle.status;
        document.getElementById("qm-election-window").textContent =
          "Nomination " + data.cycle.nomination_start + " – " + data.cycle.nomination_end +
          " · Voting " + data.cycle.voting_start + " – " + data.cycle.voting_end;
        // The 4-week rhythm and what THIS member should do (same guide as Q-Punch and the phone app).
        var guideEl = document.getElementById("qm-election-guide");
        if (!guideEl) {
          guideEl = document.createElement("p");
          guideEl.id = "qm-election-guide";
          guideEl.className = "qp-elec-guide";
          document.getElementById("qm-election-window").insertAdjacentElement("afterend", guideEl);
        }
        if (data.guide) {
          var wk = (data.weeks || []).filter(function (w) { return w.week === data.week; })[0];
          guideEl.textContent = (data.guide.action ? "📣 " : "ℹ️ ") + "Week " + data.week + " of 4" +
            (wk ? " · " + wk.title : "") + " — " + data.guide.text;
          guideEl.classList.toggle("is-action", !!data.guide.action);
        }

        var nominateBlock = document.getElementById("qm-election-nominate-block");
        var nominateNote = document.getElementById("qm-election-nominate-note");
        nominateBlock.hidden = !data.eligibility.can_nominate;
        if (data.eligibility.already_nominated) {
          nominateNote.textContent = "You've submitted a nomination for this cycle.";
          nominateNote.hidden = false;
        } else if (!data.eligibility.can_nominate && data.eligibility.nominate_reason) {
          nominateNote.textContent = data.eligibility.nominate_reason;
          nominateNote.hidden = false;
        } else {
          nominateNote.hidden = true;
        }
        loadElectionCandidates();
      })
      .catch(function (err) { console.error("Failed to load election status", err); });
  }

  // 2026-10-28 (Q-Punch transparency): turnout while voting is open, a results bar chart once the
  // cycle closes, and the 4-week progress strip. election_core.election_summary() already backs
  // the Q-Punch POPUP's own electionBlock() (static/js/board.js, via GET /api/qpunch/<level>) in
  // plain text -- turnout as a sentence, winners/candidates as a "N votes" suffix, no chart -- but
  // GET /api/election/summary, the dedicated endpoint for this same data, was never called from
  // the main board page at all. This reuses .qp-elec-weeks/.qp-elec-week (board.js's own classes
  // for the identical concept) rather than inventing a second visual language for it.
  function renderElectionWeeks(summary) {
    var box = document.getElementById("qm-election-weeks");
    box.innerHTML = "";
    var tl = el("div", "qp-elec-weeks");
    (summary.weeks || []).forEach(function (w) {
      var s = el("div", "qp-elec-week" + (w.week === summary.week ? " is-now" : w.week < summary.week ? " is-done" : ""));
      s.appendChild(el("b", "", w.week < summary.week ? "✓" : String(w.week)));
      s.appendChild(el("span", "", w.title));
      tl.appendChild(s);
    });
    box.appendChild(tl);
  }

  function renderElectionTurnout(summary) {
    var box = document.getElementById("qm-election-turnout");
    if (summary.status === "nomination") { box.hidden = true; return; }
    box.hidden = false;
    var pct = summary.eligible_voters > 0 ? Math.round((summary.turnout / summary.eligible_voters) * 100) : 0;
    document.getElementById("qm-election-turnout-text").textContent =
      "👥 Turnout: " + summary.turnout.toLocaleString() + " / " + summary.eligible_voters.toLocaleString() +
      " eligible voted (" + pct + "%)";
    document.getElementById("qm-election-turnout-fill").style.width = pct + "%";
    var note = document.getElementById("qm-election-turnout-note");
    note.textContent = summary.status === "closed"
      ? "Voting closed — final turnout for " + summary.sign + " " + summary.year + "."
      : "Votes are counted live — results stay sealed until voting closes.";
  }

  function renderElectionResults(summary) {
    var box = document.getElementById("qm-election-results");
    if (summary.status !== "closed") { box.hidden = true; return; }
    box.hidden = false;
    var body = document.getElementById("qm-election-results-body");
    body.innerHTML = "";
    var winners = summary.winners || {};
    ["male", "female"].forEach(function (gender) {
      var cands = (summary.candidates && summary.candidates[gender]) || [];
      if (!cands.length) return;
      var maxVotes = Math.max.apply(null, cands.map(function (c) { return c.votes || 0; }).concat([1]));
      var seat = gender === "male" ? "Nayak" : "Nayika";
      body.appendChild(el("h4", "qp-results-seat", seat + (winners[gender] ? " — " + winners[gender] : "")));
      cands.slice().sort(function (a, b) { return (b.votes || 0) - (a.votes || 0); }).forEach(function (c) {
        var votes = c.votes || 0;
        var row = el("div", "qp-results-row");
        row.appendChild(el("span", "qp-results-name", c.name));
        var bar = el("div", "qp-results-bar");
        var fill = el("div", "qp-results-fill");
        fill.style.width = Math.round((votes / maxVotes) * 100) + "%";
        bar.appendChild(fill);
        row.appendChild(bar);
        row.appendChild(el("span", "qp-results-count", votes.toLocaleString() + " vote" + (votes === 1 ? "" : "s")));
        body.appendChild(row);
      });
    });
  }

  function loadElectionSummary() {
    fetch("/api/election/summary")
      .then(function (r) { return r.json(); })
      .then(function (summary) {
        renderElectionWeeks(summary);
        renderElectionTurnout(summary);
        renderElectionResults(summary);
      })
      .catch(function (err) { console.error("Failed to load election summary", err); });
  }

  if (electionsCard) {
    loadElectionStatus();
    loadElectionCouncil();
    loadElectionSummary();

    var nominateForm = document.getElementById("qm-election-nominate-form");
    nominateForm.addEventListener("submit", function (e) {
      e.preventDefault();
      fetch("/api/election/nominate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: document.getElementById("qm-election-reason").value.trim(),
          why_vote: document.getElementById("qm-election-why-vote").value.trim(),
          changes: document.getElementById("qm-election-changes").value.trim(),
          past_work: document.getElementById("qm-election-past-work").value.trim(),
        }),
      })
        .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
        .then(function (result) {
          if (!result.ok) throw new Error(result.body.error || "Could not submit nomination");
          loadElectionStatus();
        })
        .catch(function (err) { alert(err.message); });
    });
  }

  // ---- Post Testing cycle admin panel (2026-10-17, docs/test_cycle_design.md) -- the markup
  // only exists in the page at all when is_admin was true at render time (dashboard.html's own
  // {% if is_admin %} gate), so every element here guards with `if (!el) return` exactly like
  // the wallet/karma loaders above -- a non-admin viewer's page simply has none of these ids.
  var testCycleCard = document.getElementById("qm-testcycle-card");

  function loadTestCycle() {
    if (!testCycleCard) return;
    fetch("/api/admin/test-cycle/panel")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var w = data.window;
        var empty = document.getElementById("qm-testcycle-empty");
        var body = document.getElementById("qm-testcycle-body");
        var renewBtn = document.getElementById("qm-testcycle-renew-btn");
        var stopBtn = document.getElementById("qm-testcycle-stop-btn");
        var startBtn = document.getElementById("qm-testcycle-start-btn");
        empty.hidden = !!w;
        body.hidden = !w;
        renewBtn.hidden = !w || w.status !== "active";
        stopBtn.hidden = !w || w.status !== "active";
        startBtn.hidden = !!w && w.status === "active";
        if (!w) return;
        document.getElementById("qm-testcycle-status").textContent = w.status;
        document.getElementById("qm-testcycle-count").textContent = w.demo_user_count;
        document.getElementById("qm-testcycle-posts").textContent = data.posts_this_month;
        document.getElementById("qm-testcycle-votes").textContent = data.votes_this_month;
        try {
          var start = new Date(w.start_date), end = new Date(w.end_date);
          document.getElementById("qm-testcycle-window-start").textContent = start.toLocaleDateString();
          document.getElementById("qm-testcycle-window-end").textContent = end.toLocaleDateString();
        } catch (e) { /* malformed date -- leave blank rather than crash the whole panel */ }
        try {
          var dist = JSON.parse(w.vote_distribution);
          document.getElementById("qm-testcycle-dist").textContent =
            Object.keys(dist).map(function (k) { return Math.round(dist[k] * 100) + "% " + k; }).join(", ");
        } catch (e) { document.getElementById("qm-testcycle-dist").textContent = w.vote_distribution; }
      })
      .catch(function (err) { console.error("Failed to load test cycle panel", err); });
  }
  loadTestCycle();

  function testCycleAction(url, confirmMsg) {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    var errEl = document.getElementById("qm-testcycle-error");
    fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (result) {
        if (!result.ok) throw new Error(result.body.error || "Could not complete that action");
        errEl.hidden = true;
        loadTestCycle();
      })
      .catch(function (err) { errEl.textContent = err.message; errEl.hidden = false; });
  }
  if (testCycleCard) {
    var renewBtnEl = document.getElementById("qm-testcycle-renew-btn");
    var stopBtnEl = document.getElementById("qm-testcycle-stop-btn");
    var startBtnEl = document.getElementById("qm-testcycle-start-btn");
    if (renewBtnEl) renewBtnEl.addEventListener("click", function () { testCycleAction("/api/admin/test-cycle/renew"); });
    if (stopBtnEl) stopBtnEl.addEventListener("click", function () {
      testCycleAction("/api/admin/test-cycle/stop", "Stop the active Post Testing window? Demo users are not retired by this.");
    });
    if (startBtnEl) startBtnEl.addEventListener("click", function () { testCycleAction("/api/admin/test-cycle/start"); });
  }

  // ---- Admin member export (2026-10-18) -- same is_admin gating as the Post Testing panel
  // above: the markup only exists when is_admin was true at render time, so every lookup here
  // guards with the same `if (!el) return` pattern.
  var memberExportCard = document.getElementById("qm-memberexport-card");
  if (memberExportCard) {
    var meLevel = document.getElementById("qm-memberexport-level");
    var meLocField = document.getElementById("qm-memberexport-locid-field");
    var meLocInput = document.getElementById("qm-memberexport-locid");
    var mePeriod = document.getElementById("qm-memberexport-period");
    var meErr = document.getElementById("qm-memberexport-error");
    var meResults = document.getElementById("qm-memberexport-results");
    var meCount = document.getElementById("qm-memberexport-count");
    var meTbody = document.getElementById("qm-memberexport-tbody");

    function meToggleLocField() { meLocField.hidden = meLevel.value === "earth"; }
    meToggleLocField();
    meLevel.addEventListener("change", meToggleLocField);

    function meQueryString() {
      var params = new URLSearchParams();
      params.set("level", meLevel.value);
      if (meLevel.value !== "earth" && meLocInput.value.trim()) params.set("location_id", meLocInput.value.trim());
      params.set("period", mePeriod.value);
      return params.toString();
    }

    document.getElementById("qm-memberexport-preview-btn").addEventListener("click", function () {
      meErr.hidden = true;
      meResults.hidden = true;
      if (meLevel.value !== "earth" && !meLocInput.value.trim()) {
        meErr.textContent = "Enter a Location ID, or choose Earth (everyone).";
        meErr.hidden = false;
        return;
      }
      fetch("/api/admin/users/export?" + meQueryString())
        .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
        .then(function (result) {
          if (!result.ok) throw new Error(result.body.error || "Could not load members");
          meTbody.innerHTML = "";
          result.body.members.forEach(function (m) {
            var tr = document.createElement("tr");
            [m.private_id, m.account_id, m.name, m.location, m.created_at].forEach(function (val) {
              var td = document.createElement("td");
              td.textContent = val || "";
              tr.appendChild(td);
            });
            meTbody.appendChild(tr);
          });
          meCount.textContent = result.body.count + " member" + (result.body.count === 1 ? "" : "s") + " found.";
          meResults.hidden = false;
        })
        .catch(function (err) { meErr.textContent = err.message; meErr.hidden = false; });
    });

    document.getElementById("qm-memberexport-csv-btn").addEventListener("click", function () {
      meErr.hidden = true;
      if (meLevel.value !== "earth" && !meLocInput.value.trim()) {
        meErr.textContent = "Enter a Location ID, or choose Earth (everyone).";
        meErr.hidden = false;
        return;
      }
      window.location.href = "/api/admin/users/export.csv?" + meQueryString();
    });
  }

  // ---- Admin Panel (2026-10-18): a combined inbox over Citizen Reports, ID recovery requests,
  // and general queries. The markup only exists in the DOM for is_admin_panel_user (dashboard.html's
  // {% if %} gate), so loadAdminPanel() itself no-ops for everyone else -- same pattern as the
  // Test Cycle / Member Export blocks above. Small local helpers (apEl/apApi/apAgo) rather than
  // reaching into board.js's own IIFE-scoped el()/api()/ago(), which aren't visible here. ----
  function apEl(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function apApi(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }
  function apAgo(iso) {
    if (!iso) return "";
    var s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + " min ago";
    if (s < 86400) return Math.floor(s / 3600) + " h ago";
    return Math.floor(s / 86400) + " d ago";
  }

  // qmRenderFormattedText (the formatted-text renderer apOpenCouncil below calls) now lives in
  // static/js/qmail_format.js, loaded before this file -- see that file's own header for why it
  // was extracted rather than kept here with a second copy in dash_extras.js.

  // Assigned inside the `if (apList)` block below, read by loadAdminPanel() at the bottom of this
  // IIFE -- a plain outer `var` assignment, not a function declaration, so it's unaffected by
  // strict mode's block-scoping of function declarations (apLoadFeed() itself IS declared inside
  // that block and wouldn't be reachable from outside it directly).
  var apRefreshFeed = null;
  var apList = document.getElementById("ap-list");
  if (apList) {
    var apDetail = document.getElementById("ap-detail");
    var apFilterBtns = Array.prototype.slice.call(document.querySelectorAll(".ap-filter"));
    var apRefreshBtn = document.querySelector(".ap-refresh-btn");
    var apCurrentFilter = "all";
    var apItemsCache = [];

    function apSourceLabel(source) {
      return { report: "Citizen Report", id_recovery: "ID Recovery", query: "Query", council: "Council Queue" }[source] || source;
    }

    function apRenderList() {
      apList.innerHTML = "";
      var filtered = apCurrentFilter === "all" ? apItemsCache : apItemsCache.filter(function (it) { return it.source === apCurrentFilter; });
      // 2026-10-28 fix: apList.innerHTML = "" (above) deletes #ap-list-empty too -- it's a child
      // of #ap-list in the template, not a sibling -- so the OLD cached `apListEmpty` reference
      // (document.getElementById, read once at page load) pointed at a detached node from the
      // very first render onward; toggling .hidden on it had no visible effect. Building this
      // fresh each render, the same way every other node in this list already is, instead of
      // relying on a template node surviving innerHTML wipes it sits inside.
      if (!filtered.length) apList.appendChild(apEl("p", "qm-dash-empty", "Nothing open right now."));
      filtered.forEach(function (it) {
        var row = apEl("button", "ap-row");
        row.type = "button";
        row.appendChild(apEl("span", "ap-badge ap-badge-" + it.status, it.status));
        row.appendChild(apEl("div", "ap-row-title", it.title || "(no subject)"));
        row.appendChild(apEl("div", "ap-row-meta",
          apSourceLabel(it.source) + " · " + (it.author || "Unknown") + (it.location ? " · " + it.location : "") + " · " + apAgo(it.created_at)));
        row.addEventListener("click", function () { apOpenDetail(it); });
        apList.appendChild(row);
      });
    }

    function apLoadFeed() {
      fetch("/api/admin/panel/feed")
        .then(function (r) { return r.json(); })
        .then(function (data) { apItemsCache = data.items || []; apRenderList(); })
        .catch(function (err) { apList.innerHTML = ""; apList.appendChild(apEl("p", "qm-dash-empty", err.message)); });
    }

    apFilterBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        apFilterBtns.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
        apCurrentFilter = btn.getAttribute("data-filter");
        apRenderList();
      });
    });
    if (apRefreshBtn) apRefreshBtn.addEventListener("click", apLoadFeed);

    function apOpenDetail(item) {
      apDetail.innerHTML = "";
      apDetail.appendChild(apEl("p", "qm-dash-empty", "Loading…"));
      if (item.source === "report") apOpenReport(item.id);
      else if (item.source === "id_recovery") apOpenIdRecovery(item.id);
      else if (item.source === "query") apOpenQuery(item.id);
      else if (item.source === "council") apOpenCouncil(item.id);
    }

    function apOpenReport(id) {
      fetch("/api/reports/" + id).then(function (r) { return r.json(); }).then(function (r) {
        apDetail.innerHTML = "";
        apDetail.appendChild(apEl("h3", "ap-detail-title", "Citizen Report #" + r.id));
        apDetail.appendChild(apEl("p", "ap-detail-meta", (r.author_name || "Anonymous Citizen") + " · " + r.location_level + " " + r.location_id));
        apDetail.appendChild(apEl("p", "ap-detail-body", r.body));
        var updatesBox = apEl("div", "ap-updates");
        (r.updates || []).forEach(function (u) {
          var row = apEl("div", "ap-update-row");
          row.appendChild(apEl("b", "", (u.author_name || u.author_role || "System") + " "));
          row.appendChild(apEl("span", "", u.update_type + (u.message ? ": " + u.message : "") + " · " + apAgo(u.created_at)));
          updatesBox.appendChild(row);
        });
        apDetail.appendChild(updatesBox);

        var actions = apEl("div", "ap-actions");
        var replyInput = document.createElement("input");
        replyInput.type = "text"; replyInput.placeholder = "Add a comment…"; replyInput.className = "ap-reply-input";
        actions.appendChild(replyInput);

        function doUpdate(type) {
          apApi("/api/reports/" + id + "/update", { update_type: type, message: replyInput.value })
            .then(function () { apLoadFeed(); apOpenReport(id); })
            .catch(function (e) { alert(e.message); });
        }
        [["comment", "Comment"], ["acknowledged", "Acknowledge"], ["resolved", "Resolve"], ["denied", "Deny"]].forEach(function (x) {
          var btn = apEl("button", "qm-btn qm-btn-ghost", x[1]); btn.type = "button";
          btn.addEventListener("click", function () { doUpdate(x[0]); });
          actions.appendChild(btn);
        });
        var escBtn = apEl("button", "qm-btn qm-btn-primary", "Escalate"); escBtn.type = "button";
        escBtn.addEventListener("click", function () {
          apApi("/api/reports/" + id + "/escalate", {}).then(function () { apLoadFeed(); apOpenReport(id); }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(escBtn);
        apDetail.appendChild(actions);
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    function apOpenIdRecovery(id) {
      fetch("/api/admin/recover-id").then(function (r) { return r.json(); }).then(function (data) {
        var rq = (data.requests || []).filter(function (x) { return x.id === id; })[0];
        apDetail.innerHTML = "";
        if (!rq) { apDetail.appendChild(apEl("p", "qm-dash-empty", "Not found.")); return; }
        apDetail.appendChild(apEl("h3", "ap-detail-title", "ID Recovery — " + rq.name));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "DOB " + rq.dob + " · status: " + rq.status));
        apDetail.appendChild(apEl("p", "ap-detail-body", rq.note || "(no note)"));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "Contact: " + (rq.phone || rq.email || "—")));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "Mailing address: " + rq.mailing_address));

        var actions = apEl("div", "ap-actions");
        if (rq.candidate_user_id && rq.status !== "sent" && rq.status !== "rejected") {
          var revealBtn = apEl("button", "qm-btn qm-btn-primary", "Approve & reveal ID"); revealBtn.type = "button";
          revealBtn.addEventListener("click", function () {
            if (!window.confirm("Reveal this member's real Private ID for the physical letter? This is logged.")) return;
            apApi("/api/admin/recover-id/" + id + "/reveal", {}).then(function (res) {
              return apApi("/api/admin/recover-id/" + id + "/decide", { status: "sent" }).then(function () {
                alert("Private ID: " + res.private_code + "\n\nWrite this into the physical letter now. It will not be shown again here.");
                apLoadFeed(); apOpenIdRecovery(id);
              });
            }).catch(function (e) { alert(e.message); });
          });
          actions.appendChild(revealBtn);
        }
        if (rq.status !== "sent" && rq.status !== "rejected") {
          var rejectBtn = apEl("button", "qm-btn qm-btn-ghost", "Reject"); rejectBtn.type = "button";
          rejectBtn.addEventListener("click", function () {
            apApi("/api/admin/recover-id/" + id + "/decide", { status: "rejected" })
              .then(function () { apLoadFeed(); apOpenIdRecovery(id); }).catch(function (e) { alert(e.message); });
          });
          actions.appendChild(rejectBtn);
        }
        apDetail.appendChild(actions);
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    function apOpenQuery(id) {
      fetch("/api/admin/queries/" + id).then(function (r) { return r.json(); }).then(function (q) {
        apDetail.innerHTML = "";
        apDetail.appendChild(apEl("h3", "ap-detail-title", q.subject));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "Category: " + q.category + " · status: " + q.status));
        apDetail.appendChild(apEl("p", "ap-detail-body", q.body));
        var repliesBox = apEl("div", "ap-updates");
        (q.replies || []).forEach(function (r) {
          var row = apEl("div", "ap-update-row");
          if (window.QMAvatar) row.appendChild(window.QMAvatar.render({ name: r.author_name, gender: r.author_gender, profile_picture_url: r.author_profile_picture_url }, 22));
          row.appendChild(apEl("b", "", r.author_name + " "));
          row.appendChild(apEl("span", "", r.message + " · " + apAgo(r.created_at)));
          repliesBox.appendChild(row);
        });
        apDetail.appendChild(repliesBox);

        var actions = apEl("div", "ap-actions");
        var replyInput = document.createElement("input");
        replyInput.type = "text"; replyInput.placeholder = "Write a reply…"; replyInput.className = "ap-reply-input";
        actions.appendChild(replyInput);
        var replyBtn = apEl("button", "qm-btn qm-btn-primary", "Reply"); replyBtn.type = "button";
        replyBtn.addEventListener("click", function () {
          if (!replyInput.value.trim()) return;
          apApi("/api/admin/queries/" + id + "/reply", { message: replyInput.value })
            .then(function () { apLoadFeed(); apOpenQuery(id); }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(replyBtn);
        var closeBtn = apEl("button", "qm-btn qm-btn-ghost", "Close ticket"); closeBtn.type = "button";
        closeBtn.addEventListener("click", function () {
          apApi("/api/admin/queries/" + id + "/close", {}).then(function () { apLoadFeed(); apDetail.innerHTML = ""; }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(closeBtn);
        apDetail.appendChild(actions);
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    function apOpenCouncil(id) {
      fetch("/api/admin/panel/council/" + id).then(function (r) { return r.json(); }).then(function (m) {
        apDetail.innerHTML = "";
        apDetail.appendChild(apEl("h3", "ap-detail-title", m.subject || "(no subject)"));
        apDetail.appendChild(apEl("p", "ap-detail-meta", m.level.charAt(0).toUpperCase() + m.level.slice(1) +
          " " + m.location_id + " · status: " + m.status));
        var bodyP = document.createElement("p"); bodyP.className = "ap-detail-body";
        bodyP.appendChild(window.qmRenderFormattedText(m.body));
        apDetail.appendChild(bodyP);

        (m.attachments || []).forEach(function (att) {
          var link = document.createElement("a");
          link.href = "/api/qmail/attachments/" + att.id; link.target = "_blank"; link.rel = "noopener noreferrer";
          link.className = "ap-attachment-link";
          link.textContent = "📎 " + att.filename + " (" + Math.round(att.byte_size / 1024) + " KB)";
          apDetail.appendChild(link);
        });

        var repliesBox = apEl("div", "ap-updates");
        (m.actions || []).filter(function (a) { return a.action === "replied"; }).forEach(function (a) {
          var row = apEl("div", "ap-update-row");
          row.appendChild(apEl("b", "", a.actor_name + " "));
          var span = document.createElement("span");
          span.appendChild(window.qmRenderFormattedText(a.detail));
          span.appendChild(document.createTextNode(" · " + apAgo(a.created_at)));
          row.appendChild(span);
          repliesBox.appendChild(row);
        });
        apDetail.appendChild(repliesBox);

        if (m.status !== "closed") {
          var actions2 = apEl("div", "ap-actions");
          var replyInput = document.createElement("input");
          replyInput.type = "text"; replyInput.placeholder = "Write a reply…"; replyInput.className = "ap-reply-input";
          actions2.appendChild(replyInput);
          var replyBtn = apEl("button", "qm-btn qm-btn-primary", "Reply"); replyBtn.type = "button";
          replyBtn.addEventListener("click", function () {
            if (!replyInput.value.trim()) return;
            apApi("/api/admin/panel/council/" + id + "/reply", { message: replyInput.value })
              .then(function () { apLoadFeed(); apOpenCouncil(id); }).catch(function (e) { alert(e.message); });
          });
          actions2.appendChild(replyBtn);
          var closeBtn2 = apEl("button", "qm-btn qm-btn-ghost", "Close"); closeBtn2.type = "button";
          closeBtn2.addEventListener("click", function () {
            apApi("/api/admin/panel/council/" + id + "/close", {}).then(function () { apLoadFeed(); apOpenCouncil(id); }).catch(function (e) { alert(e.message); });
          });
          actions2.appendChild(closeBtn2);
          apDetail.appendChild(actions2);
        }
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    apRefreshFeed = apLoadFeed;
  }

  function loadAdminPanel() {
    if (apRefreshFeed) apRefreshFeed();
  }
  // 2026-10-28 (Hierarchical Explorer redesign): the Admin Queue moved from its own top-level tab
  // into the explorer modal's second sub-tab -- multiview.js calls this the first time that
  // sub-tab opens, same lazy-load-once pattern the old "admin" tab click used.
  window.QMLoadAdminPanel = loadAdminPanel;
})();
