/**
 * earth-globe.js — reusable rotatable/zoomable Three.js Earth.
 *
 * Extracted from the homepage's original earth.js so the same globe (drag
 * to rotate, scroll/pinch to zoom, click-to-pick markers) can be mounted
 * on both the homepage and the registration wizard (birth location step,
 * then reset and reused for the present location step) without duplicating
 * the Three.js scene code.
 *
 * Since the "dots for continents" version, this also renders real
 * continent/country shapes: static/images/earth_texture.png (a rasterized
 * equirectangular map, see scripts/build_world_texture.py) as the sphere's
 * material map, plus point-in-polygon hit-testing against
 * static/data/world_borders.geojson for per-country click/hover — see
 * setEarthTexture() / setCountryBorders() / onCountryPick.
 *
 * Usage:
 *   var globe = QMEarthGlobe.create(canvasEl, {
 *     tooltipEl: someEl,          // optional, shows entry.name / country name on hover
 *     defaultFocusLng: 78.7,      // longitude the default view should face
 *     onPick: function (userData) {},           // marker clicks, userData = { kind, entry }
 *     onCountryPick: function (feature) {},      // country-shape clicks (feature.properties)
 *     onCountryHover: function (feature|null) {},
 *     countryTooltipLabel: function (feature) { return feature.properties.name; },  // optional override, e.g. to show the continent name instead of the country's
 *   });
 *   globe.addMarker(entry, kind);       // kind is caller-defined, e.g. 'continent' | 'india' | 'state'
 *   globe.clearMarkers();
 *   globe.setEarthTexture('/static/images/earth_texture.png');
 *   globe.setCountryBorders(geojson.features);
 *   globe.highlightCountry(feature, '#FF9933');
 *   globe.clearCountryHighlight();
 *   globe.flyTo(lat, lng, distance);    // smooth camera move, eased over subsequent frames
 *   globe.resetView();
 *   globe.destroy();
 */
(function (global) {
  "use strict";

  function degToRad(d) { return (d * Math.PI) / 180; }
  function radToDeg(r) { return (r * 180) / Math.PI; }

  // ---- Antimeridian-safe point-in-polygon (shared by hit-testing) ----
  function unwrapRing(ring) {
    var out = [ring[0].slice()];
    for (var i = 1; i < ring.length; i++) {
      var lng = ring[i][0], lat = ring[i][1];
      var prevLng = out[out.length - 1][0];
      while (lng - prevLng > 180) lng -= 360;
      while (lng - prevLng < -180) lng += 360;
      out.push([lng, lat]);
    }
    return out;
  }

  function pointInRing(lng, lat, ring) {
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      var intersect = (yi > lat) !== (yj > lat) &&
        lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
      if (intersect) inside = !inside;
    }
    return inside;
  }

  function pointInRings(lng, lat, rings) {
    var exterior = unwrapRing(rings[0]);
    var refLng = exterior[0][0];
    var qLng = lng;
    while (qLng - refLng > 180) qLng -= 360;
    while (qLng - refLng < -180) qLng += 360;
    if (!pointInRing(qLng, lat, exterior)) return false;
    for (var h = 1; h < rings.length; h++) {
      if (pointInRing(qLng, lat, unwrapRing(rings[h]))) return false;
    }
    return true;
  }

  function polygonRingsOf(geometry) {
    if (geometry.type === "Polygon") return [geometry.coordinates];
    if (geometry.type === "MultiPolygon") return geometry.coordinates;
    return [];
  }

  function featureBBox(geometry) {
    var minLng = 180, maxLng = -180, minLat = 90, maxLat = -90;
    polygonRingsOf(geometry).forEach(function (rings) {
      rings[0].forEach(function (pt) {
        if (pt[0] < minLng) minLng = pt[0];
        if (pt[0] > maxLng) maxLng = pt[0];
        if (pt[1] < minLat) minLat = pt[1];
        if (pt[1] > maxLat) maxLat = pt[1];
      });
    });
    return { minLng: minLng, maxLng: maxLng, minLat: minLat, maxLat: maxLat };
  }

  function featureContainsPoint(feature, lng, lat) {
    var bbox = feature._bbox;
    if (bbox && (lat < bbox.minLat - 1 || lat > bbox.maxLat + 1)) return false;
    var polys = polygonRingsOf(feature.geometry);
    for (var p = 0; p < polys.length; p++) {
      if (pointInRings(lng, lat, polys[p])) return true;
    }
    return false;
  }

  // Bulk-shift an already-internally-unwrapped ring so it sits in the same
  // 360deg band as refLng -- same "while" technique pointInRings already
  // uses for a single query point, just applied to every vertex of a ring
  // (needed so a hole ring triangulates in the same coordinate space as its
  // exterior ring when the polygon straddles the antimeridian).
  function unwrapRingToReference(ring, refLng) {
    var unwrapped = unwrapRing(ring);
    var lng0 = unwrapped[0][0];
    var shift = 0;
    while (lng0 + shift - refLng > 180) shift -= 360;
    while (lng0 + shift - refLng < -180) shift += 360;
    if (shift === 0) return unwrapped;
    return unwrapped.map(function (pt) { return [pt[0] + shift, pt[1]]; });
  }

  function create(canvas, opts) {
    opts = opts || {};
    var tooltipEl = opts.tooltipEl || null;
    var onPick = opts.onPick || function () {};
    var onHover = opts.onHover || function () {};
    var onCountryPick = opts.onCountryPick || function () {};
    var onCountryHover = opts.onCountryHover || function () {};
    // Defaults to the raw country name (registration wizard's location
    // pickers want that); the homepage's Earth view overrides this to show
    // the continent name instead, since individual countries are never
    // meant to be identified there — see earth.js.
    var countryTooltipLabel = opts.countryTooltipLabel || function (feature) { return feature.properties.name; };

    var EARTH_RADIUS = 5;
    var MARKER_RADIUS = EARTH_RADIUS * 1.01;
    var HIGHLIGHT_RADIUS = EARTH_RADIUS * 1.006;
    // Optional regional lock (the Indian Sub-continent maps): the camera is
    // held on {lat, lng} and can only pan/zoom a little around it, so the
    // whole Earth is never on screen. {lat, lng, panRad, distance, minDistance, maxDistance}
    var lock = opts.lockRegion || null;
    var DEFAULT_DISTANCE = lock ? lock.distance : 13;
    var MIN_DISTANCE = lock ? lock.minDistance : 6;
    var MAX_DISTANCE = lock ? lock.maxDistance : 24;
    var ZOOM_DISTANCE = 8.5;

    var stage = canvas.parentElement;
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });

    var cameraDistance = DEFAULT_DISTANCE;
    var defaultFocusLng = lock ? lock.lng : (typeof opts.defaultFocusLng === "number" ? opts.defaultFocusLng : 0);
    function lngToRotationY(lng) { return -degToRad(lng) - Math.PI / 2; }
    var DEFAULT_ROTATION_Y = lngToRotationY(defaultFocusLng);
    // A positive x-rotation tips the northern hemisphere toward the camera, bringing lock.lat to screen centre.
    var DEFAULT_ROTATION_X = lock ? degToRad(lock.lat) : -0.15;
    var rotation = { x: DEFAULT_ROTATION_X, y: DEFAULT_ROTATION_Y };

    function clampToLock() {
      if (!lock) return;
      rotation.y = Math.max(DEFAULT_ROTATION_Y - lock.panRad, Math.min(DEFAULT_ROTATION_Y + lock.panRad, rotation.y));
      rotation.x = Math.max(DEFAULT_ROTATION_X - lock.panRad, Math.min(DEFAULT_ROTATION_X + lock.panRad, rotation.x));
    }

    // Fly-to target: when set, animate() eases rotation/cameraDistance toward
    // it every frame instead of jumping instantly.
    var flyTarget = null;

    var globeGroup = new THREE.Group();
    scene.add(globeGroup);

    var markerMeshes = [];
    var oceanMesh = null;
    var oceanMaterial = null;
    var countryFeatures = [];
    var highlightLines = [];
    var regionHighlightLines = [];
    var rafId = null;
    var destroyed = false;

    function resize() {
      var w = stage.clientWidth;
      var h = stage.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    window.addEventListener("resize", resize);

    // Covers the case where this canvas is created while its container is
    // display:none (e.g. a wizard step not shown yet) — window resize never
    // fires for that, so the renderer would be stuck at a 0x0 / default size.
    var resizeObserver = null;
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(function () { resize(); });
      resizeObserver.observe(stage);
    }

    function buildEarth() {
      var oceanGeo = new THREE.SphereGeometry(EARTH_RADIUS, 96, 96);
      // opts.oceanColor switches to the flat-vector look (plain blue sea,
      // land/regions drawn as polygons -- no raster texture, so it stays crisp).
      var vector = typeof opts.oceanColor === "number";
      oceanMaterial = new THREE.MeshPhongMaterial({
        color: vector ? opts.oceanColor : 0x0A1929,
        emissive: vector ? 0x062a52 : 0x03101c,
        shininess: vector ? 30 : 10,
        specular: vector ? 0x4d8fd6 : 0x336699,
      });
      oceanMesh = new THREE.Mesh(oceanGeo, oceanMaterial);
      globeGroup.add(oceanMesh);

      var glowGeo = new THREE.SphereGeometry(EARTH_RADIUS * 1.08, 48, 48);
      var glowMat = new THREE.MeshBasicMaterial({
        color: typeof opts.atmosphereColor === "number" ? opts.atmosphereColor : 0xff9933,
        transparent: true, opacity: typeof opts.atmosphereColor === "number" ? 0.16 : 0.06, side: THREE.BackSide,
      });
      globeGroup.add(new THREE.Mesh(glowGeo, glowMat));

      scene.add(new THREE.AmbientLight(0x9fb0c3, 1.05));
      var sun = new THREE.DirectionalLight(0xffffff, 0.75);
      sun.position.set(8, 6, 10);
      scene.add(sun);
    }

    function setEarthTexture(url) {
      new THREE.TextureLoader().load(url, function (tex) {
        if (destroyed) return;
        tex.colorSpace = THREE.SRGBColorSpace;
        oceanMaterial.map = tex;
        oceanMaterial.color.set(0xffffff);
        oceanMaterial.needsUpdate = true;
      });
    }

    function setCountryBorders(features) {
      countryFeatures = features || [];
      countryFeatures.forEach(function (f) { f._bbox = featureBBox(f.geometry); });
    }

    function findCountryAt(lng, lat) {
      for (var i = 0; i < countryFeatures.length; i++) {
        if (featureContainsPoint(countryFeatures[i], lng, lat)) return countryFeatures[i];
      }
      return null;
    }

    function latLngToVector3(lat, lng, radius) {
      var phi = degToRad(90 - lat);
      var theta = degToRad(lng + 180);
      return new THREE.Vector3(
        -radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.sin(theta)
      );
    }

    // ---- Filled + elevated region rendering (earcut-triangulated GeoJSON
    // polygons draped on the sphere at a raised radius) -- separate from the
    // point-in-polygon hit-testing above, which stays flat-radius-agnostic. ----
    var triangulationCache = typeof WeakMap !== "undefined" ? new WeakMap() : null;

    function triangulateFeatureAt(feature, radius) {
      var positions = [];
      if (typeof earcut === "undefined") return positions;
      polygonRingsOf(feature.geometry).forEach(function (rings) {
        var exterior = unwrapRing(rings[0]);
        var refLng = exterior[0][0];
        var allRings = [exterior];
        for (var h = 1; h < rings.length; h++) allRings.push(unwrapRingToReference(rings[h], refLng));

        var vertices = [];
        var holeIndices = [];
        allRings.forEach(function (ring, idx) {
          if (idx > 0) holeIndices.push(vertices.length / 2);
          var n = ring.length;
          if (n > 1 && ring[0][0] === ring[n - 1][0] && ring[0][1] === ring[n - 1][1]) n -= 1;
          for (var i = 0; i < n; i++) vertices.push(ring[i][0], ring[i][1]);
        });

        var indices = earcut(vertices, holeIndices.length ? holeIndices : undefined);
        for (var t = 0; t < indices.length; t++) {
          var vi = indices[t] * 2;
          var v = latLngToVector3(vertices[vi + 1], vertices[vi], radius);
          positions.push(v.x, v.y, v.z);
        }
      });
      return positions;
    }

    function triangulateFeatureCached(feature, radius) {
      if (!triangulationCache) return triangulateFeatureAt(feature, radius);
      var cached = triangulationCache.get(feature);
      if (!cached) { cached = {}; triangulationCache.set(feature, cached); }
      var key = radius.toFixed(4);
      if (!cached[key]) cached[key] = triangulateFeatureAt(feature, radius);
      return cached[key];
    }

    function buildFillGeometry(features, radius) {
      var positions = [];
      (features || []).forEach(function (f) {
        positions = positions.concat(triangulateFeatureCached(f, radius));
      });
      var geo = new THREE.BufferGeometry();
      if (positions.length) {
        geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geo.computeVertexNormals();
      }
      return geo;
    }

    function complementOf(activeFeatures) {
      var activeIds = {};
      activeFeatures.forEach(function (f) { activeIds[f.properties.qm_country_id] = true; });
      return countryFeatures.filter(function (f) { return !activeIds[f.properties.qm_country_id]; });
    }

    var dimMesh = null, regionFillMesh = null, countryFillMesh = null, glowMesh = null;

    function replaceMesh(existing, geometry, material) {
      if (existing) {
        globeGroup.remove(existing);
        existing.geometry.dispose();
        existing.material.dispose();
      }
      var mesh = new THREE.Mesh(geometry, material);
      globeGroup.add(mesh);
      return mesh;
    }

    function setDimMesh(activeFeatures) {
      var geo = buildFillGeometry(complementOf(activeFeatures), EARTH_RADIUS * 1.001);
      var mat = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.55, side: THREE.DoubleSide });
      dimMesh = replaceMesh(dimMesh, geo, mat);
    }

    // Soft glow halo just above the fill's own radius -- same "extra
    // low-opacity shell" idea buildEarth() already uses for the whole-Earth
    // atmosphere glow, just sized to the active selection instead of the
    // whole sphere. DoubleSide + no depth write (not BackSide) since this
    // cap geometry's winding/normal direction isn't guaranteed consistent
    // (same reason the fill meshes themselves use DoubleSide).
    function setGlowMesh(features, radius, colorHex) {
      var geo = buildFillGeometry(features, radius);
      var mat = new THREE.MeshBasicMaterial({
        color: colorHex, transparent: true, opacity: 0.3, side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending, depthWrite: false,
      });
      glowMesh = replaceMesh(glowMesh, geo, mat);
    }

    function setRegionFill(features, colorHex) {
      features = features || [];
      var color = colorHex || "#FFD700";
      var geo = buildFillGeometry(features, EARTH_RADIUS * 1.015);
      var mat = new THREE.MeshPhongMaterial({
        color: color, emissive: color, emissiveIntensity: 0.35,
        transparent: true, opacity: 0.55, side: THREE.DoubleSide,
      });
      regionFillMesh = replaceMesh(regionFillMesh, geo, mat);
      if (countryFillMesh) { globeGroup.remove(countryFillMesh); countryFillMesh.geometry.dispose(); countryFillMesh.material.dispose(); countryFillMesh = null; }
      setDimMesh(features);
      setGlowMesh(features, EARTH_RADIUS * 1.045, color);
    }

    function setCountryFill(feature, colorHex) {
      if (!feature) return;
      var color = colorHex || "#FF9933";
      var geo = buildFillGeometry([feature], EARTH_RADIUS * 1.03);
      var mat = new THREE.MeshPhongMaterial({
        color: color, emissive: color, emissiveIntensity: 0.5,
        transparent: true, opacity: 0.78, side: THREE.DoubleSide,
      });
      countryFillMesh = replaceMesh(countryFillMesh, geo, mat);
      setDimMesh([feature]);
      setGlowMesh([feature], EARTH_RADIUS * 1.06, color);
    }

    // ---- Flat-vector layers (used by the Sub-continent maps) ----
    var landMesh = null, layerFillMesh = null, layerBorderMesh = null, layerGlowMesh = null;

    // Everything that isn't the highlighted region: one uniform colour.
    function setLandLayer(features, colorHex) {
      var geo = buildFillGeometry(features, EARTH_RADIUS * 1.003);
      var mat = new THREE.MeshBasicMaterial({ color: colorHex || "#050505", side: THREE.DoubleSide });
      landMesh = replaceMesh(landMesh, geo, mat);
    }

    function colouredFillGeometry(features, radius, center, innerHex, outerHex, spanDeg) {
      var geo = buildFillGeometry(features, radius);
      var pos = geo.getAttribute("position");
      if (!pos) return geo;
      var c = latLngToVector3(center.lat, center.lng, 1).normalize();
      var inner = new THREE.Color(innerHex), outer = new THREE.Color(outerHex), mix = new THREE.Color();
      var colors = new Float32Array(pos.count * 3);
      var v = new THREE.Vector3();
      for (var i = 0; i < pos.count; i++) {
        v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).normalize();
        var angle = radToDeg(Math.acos(Math.max(-1, Math.min(1, v.dot(c)))));
        var t = Math.max(0, Math.min(1, 1 - angle / spanDeg));
        t = t * t * (3 - 2 * t);
        mix.copy(outer).lerp(inner, t);
        colors[i * 3] = mix.r; colors[i * 3 + 1] = mix.g; colors[i * 3 + 2] = mix.b;
      }
      geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      return geo;
    }

    // o = { fill, border: feature arrays; center: {lat,lng}; inner, outer, borderColor }
    // Warm-white core fading to yellow at the edge, a crisp white border
    // band, and a faint additive glow just above it.
    function setRegionLayers(o) {
      var fillGeo = colouredFillGeometry(o.fill, EARTH_RADIUS * 1.006, o.center, o.inner || "#FFF7DC", o.outer || "#FFC61A", o.spanDeg || 30);
      layerFillMesh = replaceMesh(layerFillMesh, fillGeo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
      layerBorderMesh = replaceMesh(layerBorderMesh, buildFillGeometry(o.border, EARTH_RADIUS * 1.008),
        new THREE.MeshBasicMaterial({ color: o.borderColor || "#FFFFFF", side: THREE.DoubleSide }));
      layerGlowMesh = replaceMesh(layerGlowMesh, buildFillGeometry(o.fill, EARTH_RADIUS * 1.02),
        new THREE.MeshBasicMaterial({
          color: o.glowColor || "#FFE58A", transparent: true, opacity: 0.16, side: THREE.DoubleSide,
          blending: THREE.AdditiveBlending, depthWrite: false,
        }));
    }

    function clearFills() {
      [dimMesh, regionFillMesh, countryFillMesh, glowMesh].forEach(function (m) {
        if (m) { globeGroup.remove(m); m.geometry.dispose(); m.material.dispose(); }
      });
      dimMesh = null; regionFillMesh = null; countryFillMesh = null; glowMesh = null;
    }

    // ---- Auto-frame a selection: pick a fly-to distance from its actual
    // angular size, so small countries zoom in tight and large continents
    // pull back enough to stay in full view. ----
    function spanOfFeatures(features) {
      var minLng = 180, maxLng = -180, minLat = 90, maxLat = -90;
      (features || []).forEach(function (f) {
        var b = f._bbox || featureBBox(f.geometry);
        if (b.minLng < minLng) minLng = b.minLng;
        if (b.maxLng > maxLng) maxLng = b.maxLng;
        if (b.minLat < minLat) minLat = b.minLat;
        if (b.maxLat > maxLat) maxLat = b.maxLat;
      });
      // bbox longitude isn't antimeridian-aware, so a feature/group that
      // wraps it (e.g. Russia, or "Asia" once Russia is included) can show
      // a delta up to ~360 -- 180 is the real angular ceiling on a sphere,
      // so clamp there rather than reading that as "needs to zoom out more
      // than the whole globe."
      var lngSpan = Math.min(maxLng - minLng, 180);
      return Math.max(maxLat - minLat, lngSpan, 0);
    }
    function distanceForSpan(spanDeg) {
      var span = Math.max(spanDeg, 3);
      return Math.max(MIN_DISTANCE, Math.min(MAX_DISTANCE, 6.2 + span * 0.075));
    }
    function flyToFeatures(lat, lng, features) {
      flyTo(lat, lng, distanceForSpan(spanOfFeatures(features)));
    }

    function vector3ToLatLng(v) {
      var r = v.length();
      var lat = 90 - radToDeg(Math.acos(v.y / r));
      var lng = radToDeg(Math.atan2(v.z, -v.x)) - 180;
      if (lng < -180) lng += 360;
      if (lng > 180) lng -= 360;
      return { lat: lat, lng: lng };
    }

    function addMarker(entry, kind, markerOpts) {
      markerOpts = markerOpts || {};
      var size = markerOpts.size || 0.12;
      var color = markerOpts.color || 0xffd700;
      var withRing = !!markerOpts.ring;

      var geo = new THREE.SphereGeometry(size, 16, 16);
      var mat = new THREE.MeshBasicMaterial({ color: color });
      var mesh = new THREE.Mesh(geo, mat);
      mesh.position.copy(latLngToVector3(entry.lat, entry.lng, MARKER_RADIUS));
      mesh.userData = { kind: kind, entry: entry };
      globeGroup.add(mesh);
      markerMeshes.push(mesh);

      if (withRing) {
        var ringGeo = new THREE.RingGeometry(size * 1.6, size * 2.1, 32);
        var ringMat = new THREE.MeshBasicMaterial({
          color: color, transparent: true, opacity: 0.85, side: THREE.DoubleSide,
        });
        var ring = new THREE.Mesh(ringGeo, ringMat);
        ring.position.copy(mesh.position);
        ring.lookAt(mesh.position.clone().multiplyScalar(2));
        globeGroup.add(ring);
        mesh.userData.ring = ring;
      }
      return mesh;
    }

    function clearMarkers() {
      markerMeshes.forEach(function (m) {
        globeGroup.remove(m);
        if (m.userData.ring) globeGroup.remove(m.userData.ring);
      });
      markerMeshes = [];
    }

    // ---- Country boundary highlight (outline traced on the sphere surface) ----
    function highlightCountry(feature, colorHex) {
      clearCountryHighlight();
      if (!feature) return;
      var color = colorHex || "#FFD700";
      polygonRingsOf(feature.geometry).forEach(function (rings) {
        var ring = rings[0]; // exterior only — enough to read as "this shape is selected"
        var points = ring.map(function (pt) { return latLngToVector3(pt[1], pt[0], HIGHLIGHT_RADIUS); });
        var geo = new THREE.BufferGeometry().setFromPoints(points);
        var mat = new THREE.LineBasicMaterial({ color: color, linewidth: 2 });
        var line = new THREE.LineLoop(geo, mat);
        globeGroup.add(line);
        highlightLines.push(line);
      });
    }
    function clearCountryHighlight() {
      highlightLines.forEach(function (l) { globeGroup.remove(l); });
      highlightLines = [];
    }

    // ---- Region highlight (outline traced for every feature in a group,
    // e.g. all of a continent's countries) — a separate line set from the
    // single-country highlight above so both can be shown at once (the
    // active continent's countries, plus one specifically selected country
    // among them, drawn in a different color). ----
    function highlightRegion(features, colorHex) {
      clearRegionHighlight();
      var color = colorHex || "#FFD700";
      (features || []).forEach(function (feature) {
        polygonRingsOf(feature.geometry).forEach(function (rings) {
          var ring = rings[0];
          var points = ring.map(function (pt) { return latLngToVector3(pt[1], pt[0], HIGHLIGHT_RADIUS); });
          var geo = new THREE.BufferGeometry().setFromPoints(points);
          var mat = new THREE.LineBasicMaterial({ color: color, linewidth: 1, transparent: true, opacity: 0.6 });
          var line = new THREE.LineLoop(geo, mat);
          globeGroup.add(line);
          regionHighlightLines.push(line);
        });
      });
    }
    function clearRegionHighlight() {
      regionHighlightLines.forEach(function (l) { globeGroup.remove(l); });
      regionHighlightLines = [];
    }

    // ---- Interaction: drag to rotate, wheel/pinch to zoom ----
    var dragging = false;
    var dragMoved = false;
    var lastX = 0, lastY = 0;
    var autoRotate = opts.autoRotate !== false;

    function pointerDown(x, y) {
      dragging = true;
      dragMoved = false;
      autoRotate = false;
      flyTarget = null;
      lastX = x; lastY = y;
    }
    function pointerMove(x, y) {
      if (!dragging) return;
      dragMoved = true;
      var dx = x - lastX, dy = y - lastY;
      rotation.y += dx * 0.005;
      rotation.x += dy * 0.005;
      rotation.x = Math.max(-1.2, Math.min(1.2, rotation.x));
      clampToLock();
      lastX = x; lastY = y;
    }
    function pointerUp() { dragging = false; }

    function onMouseDown(e) { pointerDown(e.clientX, e.clientY); }
    function onMouseMove(e) { pointerMove(e.clientX, e.clientY); }
    function onMouseUp() { pointerUp(); }
    canvas.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    function onTouchStart(e) {
      if (e.touches.length === 1) pointerDown(e.touches[0].clientX, e.touches[0].clientY);
    }
    function onTouchMove(e) {
      if (e.touches.length === 1) pointerMove(e.touches[0].clientX, e.touches[0].clientY);
    }
    canvas.addEventListener("touchstart", onTouchStart, { passive: true });
    canvas.addEventListener("touchmove", onTouchMove, { passive: true });
    canvas.addEventListener("touchend", pointerUp);

    function onWheel(e) {
      e.preventDefault();
      flyTarget = null;
      cameraDistance += e.deltaY * 0.01;
      cameraDistance = Math.max(MIN_DISTANCE, Math.min(MAX_DISTANCE, cameraDistance));
    }
    canvas.addEventListener("wheel", onWheel, { passive: false });

    var pinchStartDist = null;
    var pinchStartCamera = cameraDistance;
    function touchDist(touches) {
      var dx = touches[0].clientX - touches[1].clientX;
      var dy = touches[0].clientY - touches[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }
    canvas.addEventListener("touchstart", function (e) {
      if (e.touches.length === 2) {
        pinchStartDist = touchDist(e.touches);
        pinchStartCamera = cameraDistance;
      }
    }, { passive: true });
    canvas.addEventListener("touchmove", function (e) {
      if (e.touches.length === 2 && pinchStartDist) {
        flyTarget = null;
        var d = touchDist(e.touches);
        cameraDistance = Math.max(MIN_DISTANCE, Math.min(MAX_DISTANCE, pinchStartCamera * (pinchStartDist / d)));
      }
    }, { passive: true });

    // ---- Click / hover picking ----
    var raycaster = new THREE.Raycaster();
    var pointerNDC = new THREE.Vector2();

    function sphereHitLatLng(clientX, clientY) {
      var rect = canvas.getBoundingClientRect();
      pointerNDC.x = ((clientX - rect.left) / rect.width) * 2 - 1;
      pointerNDC.y = -((clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointerNDC, camera);
      var hits = raycaster.intersectObject(oceanMesh);
      if (hits.length === 0) return null;
      var local = globeGroup.worldToLocal(hits[0].point.clone());
      return vector3ToLatLng(local);
    }

    function onClick(e) {
      if (dragMoved) return;
      var rect = canvas.getBoundingClientRect();
      pointerNDC.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointerNDC.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointerNDC, camera);

      var markerHits = raycaster.intersectObjects(markerMeshes);
      if (markerHits.length > 0) {
        onPick(markerHits[0].object.userData);
        return;
      }

      var latLng = sphereHitLatLng(e.clientX, e.clientY);
      if (!latLng) return;
      var feature = findCountryAt(latLng.lng, latLng.lat);
      onCountryPick(feature, latLng);
    }
    canvas.addEventListener("click", onClick);

    function onHoverMove(e) {
      var rect = canvas.getBoundingClientRect();
      pointerNDC.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointerNDC.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointerNDC, camera);
      var markerHits = raycaster.intersectObjects(markerMeshes);
      if (markerHits.length > 0) {
        var entry = markerHits[0].object.userData.entry;
        onHover(entry);
        if (tooltipEl) {
          tooltipEl.textContent = entry.name;
          tooltipEl.style.left = e.clientX - rect.left + 14 + "px";
          tooltipEl.style.top = e.clientY - rect.top + 10 + "px";
          tooltipEl.hidden = false;
        }
        canvas.style.cursor = "pointer";
        return;
      }

      var latLng = sphereHitLatLng(e.clientX, e.clientY);
      if (latLng && countryFeatures.length) {
        var feature = findCountryAt(latLng.lng, latLng.lat);
        onCountryHover(feature);
        var label = feature && countryTooltipLabel(feature);
        if (label && tooltipEl) {
          tooltipEl.textContent = label;
          tooltipEl.style.left = e.clientX - rect.left + 14 + "px";
          tooltipEl.style.top = e.clientY - rect.top + 10 + "px";
          tooltipEl.hidden = false;
          canvas.style.cursor = "pointer";
          return;
        }
      }
      onHover(null);
      onCountryHover(null);
      if (tooltipEl) tooltipEl.hidden = true;
      canvas.style.cursor = dragging ? "grabbing" : "grab";
    }
    canvas.addEventListener("mousemove", onHoverMove);

    function resetView() {
      flyTarget = null;
      rotation.x = DEFAULT_ROTATION_X;
      rotation.y = DEFAULT_ROTATION_Y;
      cameraDistance = DEFAULT_DISTANCE;
      autoRotate = opts.autoRotate !== false;
      clearCountryHighlight();
      clearRegionHighlight();
      clearFills();
    }

    function flyTo(lat, lng, distance) {
      autoRotate = false;
      flyTarget = {
        y: lngToRotationY(lng),
        x: Math.max(-1.1, Math.min(1.1, -0.15 - degToRad(lat) * 0.25)),
        distance: typeof distance === "number" ? distance : ZOOM_DISTANCE,
      };
    }

    function animate() {
      if (destroyed) return;
      rafId = requestAnimationFrame(animate);

      if (flyTarget) {
        // Shortest-path ease toward the target longitude rotation.
        var dy = flyTarget.y - rotation.y;
        while (dy > Math.PI) dy -= Math.PI * 2;
        while (dy < -Math.PI) dy += Math.PI * 2;
        rotation.y += dy * 0.08;
        rotation.x += (flyTarget.x - rotation.x) * 0.08;
        cameraDistance += (flyTarget.distance - cameraDistance) * 0.08;
        if (Math.abs(dy) < 0.001 && Math.abs(flyTarget.x - rotation.x) < 0.001) flyTarget = null;
      } else if (autoRotate && !dragging) {
        rotation.y += 0.0009;
      }

      clampToLock();
      globeGroup.rotation.y = rotation.y;
      globeGroup.rotation.x = rotation.x;
      camera.position.set(0, 0, cameraDistance);
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
    }

    function destroy() {
      destroyed = true;
      clearFills();
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      if (resizeObserver) resizeObserver.disconnect();
    }

    resize();
    buildEarth();
    animate();

    return {
      setLandLayer: setLandLayer,
      setRegionLayers: setRegionLayers,
      addMarker: addMarker,
      clearMarkers: clearMarkers,
      setEarthTexture: setEarthTexture,
      setCountryBorders: setCountryBorders,
      highlightCountry: highlightCountry,
      clearCountryHighlight: clearCountryHighlight,
      highlightRegion: highlightRegion,
      clearRegionHighlight: clearRegionHighlight,
      setRegionFill: setRegionFill,
      setCountryFill: setCountryFill,
      clearFills: clearFills,
      flyTo: flyTo,
      flyToFeatures: flyToFeatures,
      resetView: resetView,
      resize: resize,
      destroy: destroy,
      _debugRaycastAt: function (x, y) {
        var rect = canvas.getBoundingClientRect();
        var ndc = new THREE.Vector2(
          ((x - rect.left) / rect.width) * 2 - 1,
          -((y - rect.top) / rect.height) * 2 + 1
        );
        raycaster.setFromCamera(ndc, camera);
        var hits = raycaster.intersectObjects(markerMeshes);
        return {
          rect: { left: rect.left, top: rect.top, w: rect.width, h: rect.height },
          ndc: { x: ndc.x, y: ndc.y },
          markerCount: markerMeshes.length,
          hitCount: hits.length,
          dragMoved: dragMoved,
        };
      },
      _debugMarkerScreenPositions: function () {
        var rect = canvas.getBoundingClientRect();
        return markerMeshes.map(function (m) {
          var v = m.position.clone().applyMatrix4(globeGroup.matrixWorld).project(camera);
          return {
            name: m.userData.entry.name,
            kind: m.userData.kind,
            x: rect.left + (v.x * 0.5 + 0.5) * rect.width,
            y: rect.top + (-v.y * 0.5 + 0.5) * rect.height,
          };
        });
      },
      _debugCameraState: function () { return { cameraDistance: cameraDistance, flyTarget: flyTarget, rotation: { x: rotation.x, y: rotation.y } }; },
      _debugSphereHitLatLng: sphereHitLatLng,
      _debugFindCountryAt: findCountryAt,
      _debugLatLngToScreen: function (lat, lng) {
        var rect = canvas.getBoundingClientRect();
        var v = latLngToVector3(lat, lng, EARTH_RADIUS * 1.001)
          .applyMatrix4(globeGroup.matrixWorld)
          .project(camera);
        return { x: rect.left + (v.x * 0.5 + 0.5) * rect.width, y: rect.top + (-v.y * 0.5 + 0.5) * rect.height };
      },
    };
  }

  global.QMEarthGlobe = { create: create };
})(window);
