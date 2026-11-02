/**
 * qmap.js — the Q-Map page (static/data/pilot/north_west_delhi_osm.geojson base layers, plus an
 * authenticated member's own GPS + OSM-proximity layer via the existing, already-authorized
 * GET /api/qmap/user-nearby/<user_id>).
 *
 * Reads QM_USER_ID / QM_GPS_CENTER / QM_GEOJSON_URL, set by templates/qmap.html directly from the
 * server-rendered session -- this file never reads a user id from a URL query parameter, a form
 * field, or localStorage, and never calls the user-nearby endpoint for anyone but QM_USER_ID.
 */
(function () {
  "use strict";

  var mapEl = document.getElementById("qmap-map");
  if (!mapEl) return;

  var loadingEl = document.getElementById("qmap-loading");
  var errorEl = document.getElementById("qmap-error");
  var emptyEl = document.getElementById("qmap-empty");

  function hideLoading() { loadingEl.hidden = true; }
  function showError(msg) { loadingEl.hidden = true; errorEl.hidden = false; errorEl.textContent = msg; }
  function showEmpty(msg) { emptyEl.hidden = false; emptyEl.textContent = msg; }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function safeName(props, fallback) { return (props && props.name) ? escapeHtml(props.name) : fallback; }
  function osmRef(props) { return escapeHtml((props.osm_type || "?") + "/" + (props.osm_id != null ? props.osm_id : "?")); }

  // North West Delhi, roughly -- only the map's own pre-data placeholder center, used for the
  // few frames before either the pilot GeoJSON's own bounds or an authenticated member's GPS
  // center is known. Never used as a final resting center once real data is available.
  var map = L.map(mapEl, { preferCanvas: true, center: [28.75, 77.10], zoom: 12 });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>',
  }).addTo(map);

  var roadsLayer = L.layerGroup();
  var buildingsLayer = L.layerGroup();
  var hospitalsLayer = L.layerGroup();
  var yourLayer = L.layerGroup(); // the authenticated member's own GPS marker + highlighted links

  // osm_type+":"+osm_id -> the pilot's own Leaflet layer for that feature. Built once while
  // parsing the pilot GeoJSON (never re-fetched/re-parsed), reused to cross-reference a member's
  // OWN linked features (api_qmap_user_nearby() deliberately never returns geometry -- see its
  // own docstring/osm_proximity_core.get_user_nearby()'s "never includes raw coordinates") against
  // this same already-loaded pilot dataset, instead of asking the server for geometry a second way.
  var pilotIndex = {};
  function indexKey(osmType, osmId) { return (osmType || "?") + ":" + osmId; }

  function roadStyle() { return { color: "#2563eb", weight: 2, opacity: 0.75 }; }
  function buildingStyle() { return { color: "#6b7280", weight: 1, fillColor: "#9ca3af", fillOpacity: 0.25 }; }
  function hospitalOutlineStyle() { return { color: "#dc2626", weight: 2, fillColor: "#fecaca", fillOpacity: 0.3 }; }
  function highlightStyle() { return { color: "#ffd24a", weight: 4, opacity: 1 }; }

  function hospitalIcon() {
    return L.divIcon({ className: "qmap-hospital-icon-wrap", html: '<span class="qmap-hospital-icon">🏥</span>', iconSize: [26, 26], iconAnchor: [13, 13] });
  }
  function youIcon() {
    return L.divIcon({ className: "qmap-you-icon-wrap", html: '<span class="qmap-you-icon">📍</span>', iconSize: [30, 30], iconAnchor: [15, 28] });
  }

  function roadPopup(props) {
    var kind = (props.tags && props.tags.highway) ? escapeHtml(props.tags.highway) : "road";
    return "<strong>" + safeName(props, "Unnamed road") + "</strong><br>Type: " + kind;
  }
  function buildingPopup(props) {
    var kind = (props.tags && props.tags.building && props.tags.building !== "yes") ? escapeHtml(props.tags.building) : "building";
    return "<strong>" + safeName(props, "Unnamed building") + "</strong><br>Type: " + kind + "<br>OSM: " + osmRef(props);
  }
  function hospitalPopup(props) {
    return "<strong>🏥 " + safeName(props, "Unnamed hospital") + "</strong><br>OSM: " + osmRef(props);
  }

  // ---- Load the pilot dataset (once, local static file -- never Overpass, never re-fetched) ----
  var pilotBounds = null;
  function extendBounds(latLngBounds) {
    if (!latLngBounds) return;
    pilotBounds = pilotBounds ? pilotBounds.extend(latLngBounds) : L.latLngBounds(latLngBounds.getSouthWest ? latLngBounds.getSouthWest() : latLngBounds, latLngBounds.getNorthEast ? latLngBounds.getNorthEast() : latLngBounds);
  }

  function buildPilotLayers(data) {
    data.features.forEach(function (feature) {
      var props = feature.properties || {};
      var cats = props.categories || [];
      var geom = feature.geometry;
      if (!geom) return;
      var key = indexKey(props.osm_type, props.osm_id);

      if (cats.indexOf("road") !== -1 && geom.type === "LineString") {
        var roadLayer = L.geoJSON(feature, { style: roadStyle });
        roadLayer.bindPopup(roadPopup(props));
        roadLayer.addTo(roadsLayer);
        pilotIndex[key] = { layer: roadLayer, category: "road" };
        extendBounds(roadLayer.getBounds());
      } else if (cats.indexOf("building") !== -1 && (geom.type === "Polygon" || geom.type === "MultiPolygon")) {
        var buildingLayer = L.geoJSON(feature, { style: buildingStyle });
        buildingLayer.bindPopup(buildingPopup(props));
        buildingLayer.addTo(buildingsLayer);
        pilotIndex[key] = { layer: buildingLayer, category: "building" };
        extendBounds(buildingLayer.getBounds());
      } else if (cats.indexOf("hospital") !== -1) {
        if (geom.type === "Point") {
          var marker = L.marker([geom.coordinates[1], geom.coordinates[0]], { icon: hospitalIcon() });
          marker.bindPopup(hospitalPopup(props));
          marker.addTo(hospitalsLayer);
          pilotIndex[key] = { layer: marker, category: "hospital" };
          extendBounds(L.latLngBounds(marker.getLatLng(), marker.getLatLng()));
        } else if (geom.type === "Polygon" || geom.type === "MultiPolygon") {
          var outline = L.geoJSON(feature, { style: hospitalOutlineStyle });
          outline.bindPopup(hospitalPopup(props));
          outline.addTo(hospitalsLayer);
          var center = outline.getBounds().getCenter();
          var hMarker = L.marker(center, { icon: hospitalIcon() });
          hMarker.bindPopup(hospitalPopup(props));
          hMarker.addTo(hospitalsLayer);
          pilotIndex[key] = { layer: outline, marker: hMarker, category: "hospital" };
          extendBounds(outline.getBounds());
        } else {
          // Hospital relation or other geometry the pilot export didn't resolve -- reported, never
          // silently dropped from the count, but there is nothing drawable without coordinates.
          console.warn("Q-Map: hospital feature with unsupported/missing geometry", geom.type, key);
        }
      }
    });

    roadsLayer.addTo(map);     // default ON -- gives geographic context without overwhelming the map
    hospitalsLayer.addTo(map); // default ON -- only 56 features, small and useful
    // buildingsLayer starts OFF by default: ~14,500 polygons is visually heavy and the slowest of
    // the three to render; a reader turns it on deliberately via the layer control below.

    L.control.layers(null, {
      "Roads": roadsLayer,
      "Buildings": buildingsLayer,
      "Hospitals": hospitalsLayer,
    }, { collapsed: true, position: "topright" }).addTo(map);
  }

  var pilotReady = fetch(QM_GEOJSON_URL)
    .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
    .then(function (data) {
      if (!data || data.type !== "FeatureCollection" || !Array.isArray(data.features)) {
        throw new Error("unexpected GeoJSON structure");
      }
      if (data.features.length === 0) {
        hideLoading();
        showEmpty("The North West Delhi pilot dataset is currently empty.");
        return false;
      }
      buildPilotLayers(data);
      hideLoading();
      return true;
    })
    .catch(function (err) {
      console.error("Q-Map pilot data:", err);
      showError("The North West Delhi pilot map could not be loaded right now. Please try again later.");
      return false;
    });

  // ---- The authenticated member's own GPS + proximity layer (never for an anonymous visitor) ----
  var youMarker = null;

  if (QM_GPS_CENTER) {
    youMarker = L.marker([QM_GPS_CENTER.lat, QM_GPS_CENTER.lon], { icon: youIcon() });
    youMarker.addTo(yourLayer);
    yourLayer.addTo(map);
    map.setView([QM_GPS_CENTER.lat, QM_GPS_CENTER.lon], 16);
  }

  function categoryCounts(features) {
    var counts = { road: 0, building: 0, hospital: 0, other: 0 };
    features.forEach(function (f) {
      if (f.category === "road") counts.road++;
      else if (f.category === "building") counts.building++;
      else if (f.category === "poi" && f.tags && f.tags.amenity === "hospital") counts.hospital++;
      else counts.other++;
    });
    return counts;
  }

  function youPopupHtml(counts, matchedCount, totalCount) {
    // Never the raw latitude/longitude -- only a category summary, per this feature's own privacy
    // rule (the marker's position already shows where they are on the map; the popup must not
    // additionally spell out the coordinate as text).
    var parts = [];
    if (counts.road) parts.push(counts.road + " road" + (counts.road === 1 ? "" : "s"));
    if (counts.building) parts.push(counts.building + " building" + (counts.building === 1 ? "" : "s"));
    if (counts.hospital) parts.push(counts.hospital + " hospital" + (counts.hospital === 1 ? "" : "s"));
    if (counts.other) parts.push(counts.other + " other place" + (counts.other === 1 ? "" : "s"));
    var summary = parts.length ? parts.join(", ") : "no nearby OSM features linked yet";
    var html = "<strong>Your current consented map location</strong><br>Linked nearby: " + summary + ".";
    if (totalCount > matchedCount) {
      html += "<br><small>" + (totalCount - matchedCount) + " linked feature(s) are outside this pilot area and can't be shown on the map.</small>";
    }
    return html;
  }

  function renderUserFeatures(features) {
    var matched = [];
    features.forEach(function (f) {
      var key = indexKey(f.osm_type, f.osm_id);
      var entry = pilotIndex[key];
      if (!entry) return; // not covered by this pilot's own geographic extent -- nothing to draw
      matched.push(f);
      if (entry.category === "hospital") {
        if (entry.marker) entry.marker.setIcon(hospitalIcon()); // already distinct; ensure visible
        entry.layer.setStyle && entry.layer.setStyle(highlightStyle());
      } else {
        entry.layer.setStyle(highlightStyle());
      }
      entry.layer.addTo(yourLayer);
    });

    var counts = categoryCounts(features);
    if (youMarker) {
      youMarker.bindPopup(youPopupHtml(counts, matched.length, features.length));
      youMarker.on("click", function () {
        // "Bring the associated features into focus": make sure whichever base layers actually
        // hold a linked feature are switched on, so the highlighted (gold) features are visible,
        // not hidden behind a layer the reader never turned on.
        if (counts.road && !map.hasLayer(roadsLayer)) roadsLayer.addTo(map);
        if (counts.building && !map.hasLayer(buildingsLayer)) buildingsLayer.addTo(map);
        if (counts.hospital && !map.hasLayer(hospitalsLayer)) hospitalsLayer.addTo(map);
      });
    }

    if (features.length === 0) {
      showNoLinksMessage();
    }
  }

  function showNoLinksMessage() {
    var msg = QM_GPS_CENTER
      ? "Your OSM proximity data is being prepared. Please check again later."
      : "Register your present location and share GPS to see your map.";
    showEmpty(msg);
  }

  if (QM_USER_ID) {
    var userFetch = fetch("/api/qmap/user-nearby/" + encodeURIComponent(QM_USER_ID))
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
      .then(function (data) { return (data && data.features) || []; })
      .catch(function (err) {
        console.error("Q-Map user-nearby:", err);
        return null; // distinguish "fetch failed" from "genuinely zero features" below
      });

    Promise.all([pilotReady, userFetch]).then(function (results) {
      var pilotOk = results[0], features = results[1];
      if (!QM_GPS_CENTER) {
        // No consented GPS at all -- the friendly empty-state message, pilot bounds stay the view.
        showNoLinksMessage();
        if (pilotOk && pilotBounds) map.fitBounds(pilotBounds, { maxZoom: 15 });
        return;
      }
      if (features === null) return; // the request itself failed; already logged, nothing more to show
      renderUserFeatures(features);
    });
  } else {
    // Anonymous visitor: never request user-nearby data at all. Once the pilot layer is ready,
    // frame the whole pilot area so there's a sensible default view.
    pilotReady.then(function (ok) {
      if (ok && pilotBounds) map.fitBounds(pilotBounds, { maxZoom: 15 });
    });
  }

  // Leaflet needs a real, settled layout size at init -- a late reveal (e.g. web fonts/layout
  // shift) can leave it undersized until the window is resized by hand without this.
  window.addEventListener("load", function () { map.invalidateSize(); });
})();
