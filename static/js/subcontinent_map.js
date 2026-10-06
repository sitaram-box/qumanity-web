/**
 * subcontinent_map.js — flat Leaflet map of the Indian Sub-continent's 10
 * countries, for the Global Account registration step (replaces the 3D
 * globe there — see Item 14c). Visually matches india_map.js: base fill
 * very light (#FDF8E3), light gray country borders, the selected country
 * fills bright gold with a black 2px border. No zoom/pan/rotate, no
 * attribution, consistent with the Public Account map.
 *
 * Coverage note: real polygon boundaries exist for 8 of the 10 countries
 * (India, Nepal, Bhutan, Bangladesh, Myanmar, Sri Lanka, Pakistan,
 * Afghanistan — static/data/subcontinent_countries.geojson, extracted from
 * world_borders.geojson). Balochistan is a Qumanity-specific political
 * designation with no real-world boundary data to source, and Maldives
 * (small island nation) isn't present in the world-borders dataset this
 * project ships. Both remain selectable via the country chips below the
 * map (select() still accepts their id and updates state/chips correctly)
 * -- they just have no polygon to fill on the map itself.
 *
 * Usage:
 *   var map = QMSubcontinentMap.create(containerEl, {
 *     onCountrySelect: function (qmCountryId) {},
 *   });
 *   map.select(qmCountryId);   // highlight a country (e.g. from a chip click or dropdown change)
 *   map.resize();
 *   map.destroy();
 */
(function (global) {
  "use strict";

  function create(container, opts) {
    opts = opts || {};
    var onCountrySelect = opts.onCountrySelect || function () {};

    var DEFAULT_CENTER = [24, 78];
    var DEFAULT_ZOOM = 3.6;

    var leafletMap = L.map(container, {
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      minZoom: 3,
      maxZoom: 7,
      attributionControl: false,
      worldCopyJump: false,
      zoomControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      touchZoom: false,
      boxZoom: false,
      keyboard: false,
      tap: false,
    });

    var geoLayer = null;
    var selectedId = null;

    function baseStyle() {
      return { fillColor: "#FDF8E3", fillOpacity: 1, color: "#CCCCCC", weight: 1, opacity: 1 };
    }
    function selectedStyle() {
      return { fillColor: "#FFD700", fillOpacity: 1, color: "#000000", weight: 2, opacity: 1 };
    }
    function styleFor(feature) {
      return feature.properties.qm_country_id === selectedId ? selectedStyle() : baseStyle();
    }

    function onEachFeature(feature, layer) {
      layer.bindTooltip(feature.properties.name, { sticky: true, className: "qm-state-tooltip" });
      layer.on("click", function () { select(feature.properties.qm_country_id); onCountrySelect(feature.properties.qm_country_id); });
    }

    function select(qmCountryId) {
      selectedId = qmCountryId || null;
      if (!geoLayer) return;
      geoLayer.eachLayer(function (layer) { layer.setStyle(styleFor(layer.feature)); });
    }

    function loadData() {
      return fetch("/static/data/subcontinent_countries.geojson")
        .then(function (r) { return r.json(); })
        .then(function (geojson) {
          geoLayer = L.geoJSON(geojson, { style: baseStyle, onEachFeature: onEachFeature }).addTo(leafletMap);
        });
    }

    function resize() {
      leafletMap.invalidateSize();
      leafletMap.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    }

    function destroy() {
      leafletMap.remove();
    }

    var ready = loadData();

    return { select: select, resize: resize, destroy: destroy, ready: ready };
  }

  global.QMSubcontinentMap = { create: create };
})(window);
