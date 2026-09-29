/**
 * subcontinent.js — shared constants/helpers for the Indian Sub-continent:
 * the 10 countries India, Nepal, Bhutan, Bangladesh, Myanmar, Sri Lanka,
 * Pakistan, Balochistan, Afghanistan and Maldives.
 *
 * All of them have a Public timeline: Zone/State/District/Tehsil/Village for
 * India, and each country's own tiers for the rest (see /api/subcontinent).
 *
 * The maps (homepage, registration) draw the region as ONE highlighted shape
 * on a globe locked to the region: warm-white/yellow region, every other land
 * area uniform black, blue ocean, no inner borders, no whole-Earth view. It is
 * all vector geometry (static/data/subcontinent*.geojson, built by
 * scripts/build_subcontinent_data.py), so it stays sharp at any size.
 */
(function (global) {
  "use strict";

  var CODES = ["IND", "NPL", "BTN", "BGD", "MMR", "LKA", "PAK", "BLC", "AFG", "MDV"];
  var LOCK = { lat: 22, lng: 79, panRad: 0.28, distance: 9, minDistance: 7.6, maxDistance: 10.8 };
  var CENTER = { lat: 23, lng: 80 };
  var NAME = "Indian Sub-continent";
  var OCEAN = 0x0f62b8;
  var LAND = "#050505";

  function isMember(countryCode) { return CODES.indexOf(countryCode) !== -1; }

  function byRole(features, role) {
    return features.filter(function (f) { return f.properties.role === role; });
  }

  // Options every Sub-continent globe shares (merge your own handlers over these).
  function globeOptions(extra) {
    var o = {
      lockRegion: LOCK,
      autoRotate: false,
      oceanColor: OCEAN,
      atmosphereColor: 0x7cc4ff,
      onCountryHover: function () {},
      countryTooltipLabel: function () { return NAME; },
    };
    Object.keys(extra || {}).forEach(function (k) { o[k] = extra[k]; });
    return o;
  }

  var dataPromise = null;
  function loadData() {
    if (!dataPromise) {
      dataPromise = Promise.all([
        fetch("/static/data/subcontinent.geojson").then(function (r) { return r.json(); }),
        fetch("/static/data/subcontinent_land.geojson").then(function (r) { return r.json(); }),
      ]).then(function (results) { return { region: results[0].features, land: results[1].features }; });
    }
    return dataPromise;
  }

  // Draw the region (and the black land around it) onto a globe.
  function apply(globe, data) {
    globe.setCountryBorders(byRole(data.region, "outline"));
    globe.setLandLayer(data.land, LAND);
    globe.setRegionLayers({
      fill: byRole(data.region, "fill"),
      border: byRole(data.region, "border"),
      center: CENTER,
    });
  }

  global.QMSubcontinent = {
    CODES: CODES, NAME: NAME, LOCK: LOCK,
    isMember: isMember,
    globeOptions: globeOptions, loadData: loadData, apply: apply,
  };
})(window);
