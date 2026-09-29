/**
 * india_map.js — reusable Leaflet map of India's states/UTs, colored by
 * zone, for the Public Location Selection Tool (Part 3 of the brief).
 *
 * No raster basemap tiles — just the state GeoJSON polygons on a blank
 * dark background, consistent with the rest of the app and avoiding an
 * external tile-server dependency.
 *
 * Real-data note: the brief asked for 6 zones (adding "North-East" in
 * teal) and 28 states + 8 UTs. SITAXML.xml — the actual source — has 5
 * zones (Central/North/South/East/West; the North-Eastern states are
 * already grouped under Central Zone) and 37 states/UTs. This map uses
 * the 5 real zones and their already-established colors from
 * india_states.json (South's zone color was brightened from the brief's
 * navy #0A1929 to #4A90D9 earlier — pure navy is illegible against this
 * app's own dark-navy theme) rather than inventing a 6th zone the data
 * doesn't support.
 *
 * Usage:
 *   var map = QMIndiaMap.create(containerEl, {
 *     onStateConfirm: function (stateProps) {},  // stateProps = the GeoJSON feature's properties
 *     onStateHover: function (stateProps|null) {},
 *   });
 *   map.reset();
 *   map.resize();     // call after the container becomes visible (Leaflet needs this, like the globe)
 *   map.destroy();
 */
(function (global) {
  "use strict";

  function create(container, opts) {
    opts = opts || {};
    var onStateConfirm = opts.onStateConfirm || function () {};
    var onStateHover = opts.onStateHover || function () {};

    var DEFAULT_CENTER = [22.6, 80.5];
    var DEFAULT_ZOOM = 4.4;

    var leafletMap = L.map(container, {
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      minZoom: 3.5,
      maxZoom: 8,
      attributionControl: false,
      worldCopyJump: false,
    });
    L.control.attribution({ prefix: false }).addTo(leafletMap).addAttribution("Qumanity — India states (SITAXML)");

    var geoLayer = null;
    var selectedLayer = null;
    var selectedProps = null;
    var zoneFilter = null; // qm_zone_id string, or null for "all states selectable"

    // ---- District layer (real 2011-census district shapes, a DIFFERENT
    // taxonomy than the SITAXML districts the dropdown selects from — shown
    // here as decorative texture over the zoomed state, with best-effort
    // name-matched highlighting; see highlightDistrictByName). ----
    var districtLayer = null;
    var districtSelectedLayer = null;

    function districtBaseStyle() {
      // fillOpacity must stay > 0 (even if barely visible) -- an SVG path
      // with fillOpacity 0 doesn't capture pointer events over its interior
      // in most browsers, so hovering the middle of a district would fall
      // through to the state layer underneath and never show its tooltip.
      return { fillOpacity: 0.04, fillColor: "#8A6A4A", color: "#8A6A4A", weight: 1, opacity: 0.55 };
    }
    function districtSelectedStyle() {
      return { fillColor: "#FF6600", fillOpacity: 0.95, color: "#FFFFFF", weight: 2, opacity: 1 };
    }

    function clearDistrictLayer() {
      if (districtLayer) {
        leafletMap.removeLayer(districtLayer);
        districtLayer = null;
      }
      districtSelectedLayer = null;
    }

    function showDistrictsForState(stateId) {
      clearDistrictLayer();
      if (!stateId) return;
      fetch("/api/india/state-districts/" + encodeURIComponent(stateId))
        .then(function (r) { return r.json(); })
        .then(function (geojson) {
          var features = geojson.features || [];
          if (!features.length) return;
          districtLayer = L.geoJSON(geojson, {
            style: districtBaseStyle,
            onEachFeature: function (feature, layer) {
              layer.bindTooltip(feature.properties.district || "", { sticky: true, className: "qm-state-tooltip" });
            },
          }).addTo(leafletMap);
        })
        .catch(function (err) { console.error("Failed to load state district shapes", err); });
    }

    function highlightDistrictByName(name) {
      if (!districtLayer) { districtSelectedLayer = null; return; }
      var target = null;
      var needle = (name || "").trim().toLowerCase();
      districtLayer.eachLayer(function (layer) {
        var label = (layer.feature.properties.district || "").trim().toLowerCase();
        if (label && label === needle) target = layer;
      });
      if (districtSelectedLayer && districtSelectedLayer !== target) districtSelectedLayer.setStyle(districtBaseStyle());
      districtSelectedLayer = target;
      if (target) {
        target.setStyle(districtSelectedStyle());
        leafletMap.fitBounds(target.getBounds(), { padding: [30, 30], maxZoom: 11 });
      }
    }

    function baseStyle(feature) {
      return {
        fillColor: "#4A7A9A",
        fillOpacity: 0.5,
        color: "#4A7A9A",
        weight: 1,
        opacity: 0.6,
      };
    }
    function dimStyle() {
      return { fillColor: "#5A4A7A", fillOpacity: 0.35, color: "#5A4A7A", weight: 1, opacity: 0.4 };
    }
    function zoneActiveStyle() {
      return { fillColor: "#FF9933", fillOpacity: 0.8, color: "#FF9933", weight: 1.5, opacity: 0.9 };
    }
    function styleFor(feature) {
      if (!zoneFilter) return baseStyle(feature);
      return feature.properties.qm_zone_id === zoneFilter ? zoneActiveStyle() : dimStyle();
    }
    function isSelectable(feature) {
      return !zoneFilter || feature.properties.qm_zone_id === zoneFilter;
    }
    function hoverStyle(feature) {
      return { fillOpacity: 0.72, weight: 1.5, opacity: 0.9 };
    }
    function selectedStyle() {
      return { fillColor: "#00FF88", fillOpacity: 0.9, color: "#FFFFFF", weight: 2.5, opacity: 1 };
    }

    function onEachFeature(feature, layer) {
      layer.bindTooltip(feature.properties.name, { sticky: true, className: "qm-state-tooltip" });
      layer.on("mouseover", function () {
        if (!isSelectable(feature)) return;
        if (layer !== selectedLayer) layer.setStyle(hoverStyle(feature));
        onStateHover(feature.properties);
      });
      layer.on("mouseout", function () {
        if (!isSelectable(feature)) return;
        if (layer !== selectedLayer) layer.setStyle(styleFor(feature));
        onStateHover(null);
      });
      layer.on("click", function () {
        if (!isSelectable(feature)) return;
        if (selectedLayer) selectedLayer.setStyle(styleFor(selectedLayer.feature));
        selectedLayer = layer;
        selectedProps = feature.properties;
        layer.setStyle(selectedStyle());
        leafletMap.fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 9 });
        showDistrictsForState(feature.properties.qm_state_id);
        renderConfirmBar();
      });
    }

    function zoomToState(stateId) {
      if (!geoLayer) return;
      var target = null;
      geoLayer.eachLayer(function (layer) {
        if (layer.feature.properties.qm_state_id === stateId) target = layer;
      });
      if (!target) return;
      if (selectedLayer && selectedLayer !== target) selectedLayer.setStyle(styleFor(selectedLayer.feature));
      selectedLayer = target;
      selectedProps = target.feature.properties;
      target.setStyle(selectedStyle());
      leafletMap.fitBounds(target.getBounds(), { padding: [40, 40], maxZoom: 9 });
      showDistrictsForState(stateId);
    }

    function setZoneFilter(zoneId) {
      zoneFilter = zoneId || null;
      clearDistrictLayer();
      if (!geoLayer) return;
      geoLayer.eachLayer(function (layer) {
        if (layer === selectedLayer) return;
        layer.setStyle(styleFor(layer.feature));
      });
      // A zone pick alone stays at the full India view (zone highlighted,
      // not zoomed) -- zooming in only starts once a state within it is
      // picked (zoomToState/the map's own click handler).
      leafletMap.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    }

    function loadData() {
      return fetch("/static/data/india_states.geojson")
        .then(function (r) { return r.json(); })
        .then(function (geojson) {
          geoLayer = L.geoJSON(geojson, { style: baseStyle, onEachFeature: onEachFeature }).addTo(leafletMap);
        });
    }

    // ---- Confirm bar ----
    var confirmBar = document.createElement("div");
    confirmBar.className = "qm-india-map-confirm";
    confirmBar.hidden = true;
    var confirmText = document.createElement("span");
    var confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "qm-btn qm-btn-primary";
    confirmBtn.textContent = "Confirm selection";
    confirmBtn.addEventListener("click", function () {
      if (selectedProps) onStateConfirm(selectedProps);
    });
    confirmBar.appendChild(confirmText);
    confirmBar.appendChild(confirmBtn);
    container.parentElement.appendChild(confirmBar);

    function renderConfirmBar() {
      if (!selectedProps) { confirmBar.hidden = true; return; }
      confirmText.textContent = selectedProps.name + " (" + selectedProps.qm_zone_name + ")";
      confirmBar.hidden = false;
    }

    // ---- Legend ----
    var legend = document.createElement("div");
    legend.className = "qm-india-map-legend";
    container.parentElement.appendChild(legend);

    function renderLegend(zones) {
      legend.innerHTML = "";
      zones.forEach(function (z) {
        var chip = document.createElement("span");
        chip.className = "legend-chip";
        var swatch = document.createElement("span");
        swatch.className = "legend-swatch";
        swatch.style.background = z.color;
        chip.appendChild(swatch);
        chip.appendChild(document.createTextNode(z.name));
        legend.appendChild(chip);
      });
    }

    function clearSelection() {
      if (selectedLayer) {
        selectedLayer.setStyle(styleFor(selectedLayer.feature));
        selectedLayer = null;
        selectedProps = null;
      }
      clearDistrictLayer();
      confirmBar.hidden = true;
    }

    function reset() {
      zoneFilter = null;
      if (selectedLayer) {
        selectedLayer.setStyle(baseStyle(selectedLayer.feature));
        selectedLayer = null;
        selectedProps = null;
      }
      if (geoLayer) geoLayer.eachLayer(function (layer) { layer.setStyle(baseStyle(layer.feature)); });
      clearDistrictLayer();
      confirmBar.hidden = true;
      leafletMap.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    }

    function resize() {
      // The map was likely created while its container was display:none
      // (a wizard step not shown yet), so Leaflet's initial view/pixel
      // origin was computed against a bogus 0-size container.
      // invalidateSize() alone doesn't reliably fix that — re-apply the
      // default view explicitly once the container has a real size.
      leafletMap.invalidateSize();
      if (!selectedLayer) leafletMap.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    }

    function destroy() {
      leafletMap.remove();
      confirmBar.remove();
      legend.remove();
    }

    var ready = loadData();

    return {
      reset: reset,
      clearSelection: clearSelection,
      setZoneFilter: setZoneFilter,
      zoomToState: zoomToState,
      highlightDistrictByName: highlightDistrictByName,
      resize: resize,
      destroy: destroy,
      renderLegend: renderLegend,
      ready: ready,
      _debugState: function () {
        return {
          center: leafletMap.getCenter(),
          zoom: leafletMap.getZoom(),
          size: leafletMap.getSize(),
          containerRect: container.getBoundingClientRect(),
        };
      },
    };
  }

  global.QMIndiaMap = { create: create };
})(window);
