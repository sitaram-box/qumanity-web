/**
 * future.js — Qumanity 3D Future Vision Experience (templates/future.html, 2026-11-08; content
 * expanded from 4 to 8 scenes, 2026-11-09, same engine -- see the note below the scene list).
 *
 * Eight scenes, driven by normal document scroll (never hijacked -- this script only reads scroll
 * position via IntersectionObserver, it never calls preventDefault on wheel/touch events):
 *   0. 2026 -- The Present       -- a fragmented Earth, fine luminous crack lines across the globe.
 *   1. The Gap                   -- a sparse, clustered handful of lit points appear -- access and
 *                                    opportunity reach only a few places, unevenly.
 *   2. The Thread                -- the Qumanity Tree: golden lines grow across the fractures,
 *                                    branching; the cracks begin to dim.
 *   3. Connected Communities     -- the rest of the globe's points light up too (the earlier sparse
 *                                    cluster was never the whole picture); cracks fade further.
 *   4. A New Way to Participate  -- small glows at the Tree's own hub points begin a slow pulse --
 *                                    local councils, alive and active, not just data.
 *   5. Shared Responsibility     -- the ambient light itself warms and greens; the atmosphere glow
 *                                    deepens -- a world connected is a world that also tends itself.
 *   6. 2126                      -- cracks are gone, the network is at full brightness, hubs still
 *                                    pulsing -- an illustrated vision, not live data.
 *   7. Your Part In It           -- the globe recedes behind a CTA panel (plain HTML/CSS, not 3D --
 *                                    no fabricated statistics) inviting the visitor to register or
 *                                    sign in.
 *
 * Still ONE shared Three.js scene/camera/renderer persisting across all eight scenes (the
 * 2026-11-08 architecture is unchanged); each scene only changes material opacities/colors, camera
 * position, and which line/point/glow groups are visible, growing, or pulsing. No scene is ever
 * rebuilt from scratch, and no new rendering technique or dependency was introduced for this
 * expansion -- every new visual (the sparse/fill node split, the hub glows, the ambient color
 * shift) reuses the exact same primitives (THREE.Points, THREE.Line, GSAP tweens on existing
 * materials/lights) the original four scenes already used.
 *
 * Reuses the project's existing Three.js version/loading convention (three@0.160.0 via unpkg,
 * lazy-loaded only after a synchronous WebGL capability check -- see earth.js's own
 * ensureThree()/loadScriptOnce()) and the existing procedurally-generated, border-free
 * static/images/earth_texture.png (continent-colored equirectangular texture, see
 * scripts/build_world_texture.py -- it deliberately carries no country border pixels, which is
 * also why this page never draws political borders: the asset doesn't support that precision).
 * The lat/lng -> sphere-surface formula below is the same one earth-globe.js already uses, kept
 * identical so points align with this texture's UV mapping.
 */
(function () {
  "use strict";

  var stage = document.getElementById("qmf-canvas-stage");
  var canvas = document.getElementById("qmf-canvas");
  var fallbackEl = document.getElementById("qmf-fallback");
  var skipBtn = document.getElementById("qmf-skip");
  var sceneEls = Array.prototype.slice.call(document.querySelectorAll(".qmf-scene"));
  var progressDots = Array.prototype.slice.call(document.querySelectorAll(".qmf-progress-dot"));
  var continueBtns = Array.prototype.slice.call(document.querySelectorAll(".qmf-continue"));
  var SCENE_COUNT = sceneEls.length; // 8

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var isMobile = window.innerWidth < 640;

  // ==================== Skip control (works even if Three.js/WebGL never loads) ====================
  // Fixed destination per the product brief: always the sign-in page, regardless of how far the
  // visitor has scrolled or whether they're already signed in (the authenticated-specific action
  // lives only in the final scene's own CTA, rendered server-side in future.html).
  skipBtn.setAttribute("href", QMF_LOGIN_URL);

  // ==================== Scene navigation (scroll-based, plus Continue/progress-dot buttons) ====================
  function goToScene(index) {
    var el = sceneEls[index];
    if (!el) return;
    el.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }
  continueBtns.forEach(function (btn) {
    btn.addEventListener("click", function () { goToScene(parseInt(btn.getAttribute("data-scene-target"), 10)); });
  });
  progressDots.forEach(function (dot) {
    dot.addEventListener("click", function () { goToScene(parseInt(dot.getAttribute("data-scene-target"), 10)); });
  });

  var playedScene = new Array(SCENE_COUNT).fill(false);

  function setActiveScene(index) {
    sceneEls.forEach(function (el, i) { el.classList.toggle("is-active", i === index); });
    progressDots.forEach(function (dot, i) {
      dot.classList.toggle("is-active", i === index);
      if (i === index) dot.setAttribute("aria-current", "true"); else dot.removeAttribute("aria-current");
    });
    if (!playedScene[index]) {
      playedScene[index] = true;
      if (sceneApi) sceneApi.play(index);
    } else if (sceneApi) {
      sceneApi.focus(index);
    }
  }

  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
          setActiveScene(parseInt(entry.target.getAttribute("data-scene"), 10));
        }
      });
    }, { threshold: [0.5] });
    sceneEls.forEach(function (el) { io.observe(el); });
  } else {
    // No IntersectionObserver: show every scene's text immediately rather than none of it.
    sceneEls.forEach(function (el) { el.classList.add("is-active"); });
  }

  // ==================== WebGL capability check -- before ever fetching Three.js ====================
  function hasWebGL() {
    try {
      var c = document.createElement("canvas");
      return !!(window.WebGLRenderingContext && (c.getContext("webgl") || c.getContext("experimental-webgl")));
    } catch (e) {
      return false;
    }
  }

  function showFallback() {
    if (fallbackEl) fallbackEl.hidden = false;
    canvas.style.display = "none";
  }

  function loadScriptOnce(src) {
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[src="' + src + '"]');
      if (existing) { resolve(); return; }
      var s = document.createElement("script");
      s.src = src;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error("Failed to load " + src)); };
      document.head.appendChild(s);
    });
  }

  function ensureThree() {
    if (window.THREE) return Promise.resolve();
    // Same exact version/CDN earth.js already uses -- never a second Three.js version on the site.
    return loadScriptOnce("https://unpkg.com/three@0.160.0/build/three.min.js");
  }

  var sceneApi = null; // set once Three.js init succeeds; setActiveScene() checks this before use

  if (!hasWebGL()) {
    showFallback();
  } else {
    ensureThree()
      .then(function () {
        sceneApi = initThree();
        // Scene 0 is already the one in view on page load; the IntersectionObserver's own first
        // callback (which marks playedScene[0] = true) typically fires before this network-
        // dependent load finishes, so apply its resting camera/opacity state now rather than
        // waiting for a scroll event that may never come.
        if (sceneApi && playedScene[0]) sceneApi.play(0);
      })
      .catch(function (err) {
        console.error("Future Vision: Three.js failed to load/initialize", err);
        showFallback();
      });
  }

  // ==================== Three.js scene ====================
  function initThree() {
    var renderer, scene, camera, earthGroup, earthMesh, atmosphereMesh;
    var crackLines = [], threadLines = [], sparseNodes, fillNodes, hubGlow;
    var ambientLight, sun;
    var rafId = null;
    var disposed = false;
    var pointerX = 0, pointerY = 0;
    var EARTH_R = 2.6;
    var hubPulseStarted = false;

    function degToRad(d) { return (d * Math.PI) / 180; }

    // Identical to earth-globe.js's latLngToVector3 -- keeps point placement consistent with the
    // same equirectangular texture's UV orientation used elsewhere on the site.
    function latLngToVector3(lat, lng, radius) {
      var phi = degToRad(90 - lat);
      var theta = degToRad(lng + 180);
      return new THREE.Vector3(
        -radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.sin(theta)
      );
    }

    // Deterministic pseudo-random generator (seeded) so the fracture/thread/node layout is
    // identical on every page load and every visitor -- not re-randomized per session, and not
    // meant to represent any real geographic or member data.
    function makeRng(seed) {
      var s = seed % 2147483647; if (s <= 0) s += 2147483646;
      return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
    }
    var rng = makeRng(20260211);

    try {
      renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true, powerPreference: "low-power" });
    } catch (e) {
      showFallback();
      return null;
    }
    var pixelRatio = Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2);
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(window.innerWidth, window.innerHeight);

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(42, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.set(0, 0, 7.4);

    earthGroup = new THREE.Group();
    scene.add(earthGroup);

    var segs = isMobile ? 40 : 64;
    var earthGeo = new THREE.SphereGeometry(EARTH_R, segs, segs);
    var earthMat = new THREE.MeshPhongMaterial({ color: 0xffffff, shininess: 4, emissive: 0x05050f, emissiveIntensity: 0.6, transparent: true, opacity: 1 });
    earthMesh = new THREE.Mesh(earthGeo, earthMat);
    earthGroup.add(earthMesh);
    new THREE.TextureLoader().load(QMF_EARTH_TEXTURE_URL, function (tex) {
      if (disposed) return;
      if ("colorSpace" in tex) tex.colorSpace = THREE.SRGBColorSpace;
      earthMat.map = tex;
      earthMat.needsUpdate = true;
    });

    var glowGeo = new THREE.SphereGeometry(EARTH_R * 1.09, isMobile ? 32 : 48, isMobile ? 32 : 48);
    var glowMat = new THREE.MeshBasicMaterial({ color: 0xd4af37, transparent: true, opacity: 0.05, side: THREE.BackSide });
    atmosphereMesh = new THREE.Mesh(glowGeo, glowMat);
    earthGroup.add(atmosphereMesh);

    ambientLight = new THREE.AmbientLight(0x4a4a72, 1.15);
    scene.add(ambientLight);
    sun = new THREE.DirectionalLight(0xfff2cc, 1.0);
    sun.position.set(5, 3, 5);
    scene.add(sun);

    // ---- Fractures (Scene 0): fine jagged crack lines, present from the start, dim reddish-gold. ----
    var CRACK_COUNT = isMobile ? 7 : 12;
    for (var ci = 0; ci < CRACK_COUNT; ci++) {
      var lat0 = rng() * 150 - 75, lng0 = rng() * 360 - 180;
      var pts = [];
      var lat = lat0, lng = lng0;
      var steps = 7 + Math.floor(rng() * 5);
      for (var s = 0; s <= steps; s++) {
        pts.push(latLngToVector3(lat, lng, EARTH_R * 1.004));
        lat += (rng() - 0.5) * 18;
        lng += (rng() - 0.5) * 22;
      }
      var crackGeo = new THREE.BufferGeometry().setFromPoints(pts);
      var crackMat = new THREE.LineBasicMaterial({ color: 0x8a5a3a, transparent: true, opacity: 0.55 });
      var crackLine = new THREE.Line(crackGeo, crackMat);
      earthGroup.add(crackLine);
      crackLines.push(crackLine);
    }

    // ---- Golden Thread (Scene 2): a connected tree of geodesic arcs between "hub" points,
    // each grown progressively via BufferGeometry.setDrawRange(), animated with GSAP. ----
    var HUB_COUNT = isMobile ? 8 : 14;
    var hubs = [];
    for (var hi = 0; hi < HUB_COUNT; hi++) {
      var hlat = rng() * 150 - 75, hlng = rng() * 360 - 180;
      hubs.push({ lat: hlat, lng: hlng, vec: latLngToVector3(hlat, hlng, EARTH_R) });
    }
    var ARC_POINTS = 24;
    function buildArcLine(a, b) {
      var va = a.vec.clone().normalize(), vb = b.vec.clone().normalize();
      var angle = va.angleTo(vb);
      var positions = new Float32Array(ARC_POINTS * 3);
      for (var p = 0; p < ARC_POINTS; p++) {
        var t = p / (ARC_POINTS - 1);
        var v;
        if (angle < 1e-4) {
          v = va.clone();
        } else {
          var s0 = Math.sin((1 - t) * angle) / Math.sin(angle);
          var s1 = Math.sin(t * angle) / Math.sin(angle);
          v = va.clone().multiplyScalar(s0).add(vb.clone().multiplyScalar(s1));
        }
        v.normalize().multiplyScalar(EARTH_R * (1.012 + 0.01 * Math.sin(t * Math.PI)));
        positions[p * 3] = v.x; positions[p * 3 + 1] = v.y; positions[p * 3 + 2] = v.z;
      }
      var geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geo.setDrawRange(0, 0);
      var mat = new THREE.LineBasicMaterial({ color: 0xd4af37, transparent: true, opacity: 0.85 });
      var line = new THREE.Line(geo, mat);
      earthGroup.add(line);
      return line;
    }
    // Connect each hub to its nearest already-connected hub -- a single connected tree (the
    // "Qumanity Tree" metaphor), not an arbitrary mesh of lines.
    var connected = [hubs[0]];
    for (var hj = 1; hj < hubs.length; hj++) {
      var candidate = hubs[hj], nearest = connected[0], nearestD = candidate.vec.distanceTo(connected[0].vec);
      for (var hk = 1; hk < connected.length; hk++) {
        var d = candidate.vec.distanceTo(connected[hk].vec);
        if (d < nearestD) { nearestD = d; nearest = connected[hk]; }
      }
      threadLines.push(buildArcLine(nearest, candidate));
      connected.push(candidate);
    }

    // ---- Nodes, split into two layers (2026-11-09 content expansion):
    //   sparseNodes -- a small subset clustered around only 3 of the hub regions, revealed first
    //                  (Scene 1, "The Gap") to depict uneven reach.
    //   fillNodes   -- the remaining points, spread globally, revealed later (Scene 3, "Connected
    //                  Communities") once the Thread already exists -- the rest of the world
    //                  catching up, not a second unrelated dataset.
    // Both are illustrative placement only, not live member data (same disclosure as before). ----
    function makeNodeSprite() {
      var c = document.createElement("canvas"); c.width = c.height = 32;
      var g = c.getContext("2d");
      var grad = g.createRadialGradient(16, 16, 0, 16, 16, 16);
      grad.addColorStop(0, "rgba(255,245,210,1)");
      grad.addColorStop(0.5, "rgba(245,222,130,0.55)");
      grad.addColorStop(1, "rgba(245,222,130,0)");
      g.fillStyle = grad; g.fillRect(0, 0, 32, 32);
      return new THREE.CanvasTexture(c);
    }
    var nodeSpriteTex = makeNodeSprite();

    function buildNodeLayer(positions, size) {
      var geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      var mat = new THREE.PointsMaterial({
        size: size, map: nodeSpriteTex, transparent: true, opacity: 0,
        depthWrite: false, blending: THREE.AdditiveBlending,
      });
      var pts = new THREE.Points(geo, mat);
      earthGroup.add(pts);
      return pts;
    }

    var TOTAL_NODES = isMobile ? 90 : 180;
    var SPARSE_COUNT = Math.round(TOTAL_NODES * 0.22); // ~ a handful of places, not the whole globe
    var SPARSE_REGION_CENTERS = [hubs[0].vec, hubs[Math.floor(hubs.length / 3)].vec, hubs[Math.floor((hubs.length * 2) / 3)].vec];
    var sparsePositions = new Float32Array(SPARSE_COUNT * 3);
    for (var si = 0; si < SPARSE_COUNT; si++) {
      var center = SPARSE_REGION_CENTERS[si % SPARSE_REGION_CENTERS.length];
      var jitterLat = (rng() - 0.5) * 22, jitterLng = (rng() - 0.5) * 26;
      // Walk a small random offset from the chosen hub's own lat/lng rather than resampling the
      // whole globe, so these points genuinely cluster near just 3 regions.
      var baseHub = hubs[(si % SPARSE_REGION_CENTERS.length) === 0 ? 0 : Math.floor(hubs.length / 3)];
      var v = latLngToVector3(baseHub.lat + jitterLat, baseHub.lng + jitterLng, EARTH_R * 1.015);
      sparsePositions[si * 3] = v.x; sparsePositions[si * 3 + 1] = v.y; sparsePositions[si * 3 + 2] = v.z;
    }
    sparseNodes = buildNodeLayer(sparsePositions, isMobile ? 0.1 : 0.08);

    var FILL_COUNT = TOTAL_NODES - SPARSE_COUNT;
    var fillPositions = new Float32Array(FILL_COUNT * 3);
    for (var fi = 0; fi < FILL_COUNT; fi++) {
      var flat = rng() * 160 - 80, flng = rng() * 360 - 180;
      var fv = latLngToVector3(flat, flng, EARTH_R * 1.015);
      fillPositions[fi * 3] = fv.x; fillPositions[fi * 3 + 1] = fv.y; fillPositions[fi * 3 + 2] = fv.z;
    }
    fillNodes = buildNodeLayer(fillPositions, isMobile ? 0.09 : 0.07);

    // ---- Hub glow (Scene 4, "A New Way to Participate"): a small pulsing point at each Tree hub
    // -- local councils, alive and active. Reuses the same sprite texture/blending as the nodes
    // above, just a distinct, larger, slow-pulsing layer so it reads as "active," not "static." ----
    var hubPositions = new Float32Array(hubs.length * 3);
    hubs.forEach(function (h, i) {
      var v = h.vec.clone().normalize().multiplyScalar(EARTH_R * 1.02);
      hubPositions[i * 3] = v.x; hubPositions[i * 3 + 1] = v.y; hubPositions[i * 3 + 2] = v.z;
    });
    hubGlow = buildNodeLayer(hubPositions, isMobile ? 0.16 : 0.13);

    // ==================== GSAP scene choreography ====================
    // Per-scene target state, shared by play() (first visit -- also triggers one-shot growth/pulse
    // starts) and focus() (re-visiting -- snaps/tweens straight to the same resting values, never
    // re-running a one-shot animation). Keeping these as parallel arrays (one entry per scene)
    // means both functions read the same numbers; a wrong value can't drift between them.
    var CAMERA_POS = [
      { x: 0, y: 0.1, z: 7.4 }, { x: 0.3, y: 0.15, z: 7.0 }, { x: 0.6, y: 0.2, z: 6.4 }, { x: 0.2, y: 0.1, z: 6.0 },
      { x: -0.2, y: 0.05, z: 5.8 }, { x: -0.5, y: 0.0, z: 5.7 }, { x: -0.4, y: 0.05, z: 5.6 }, { x: 0, y: 0, z: 10.5 },
    ];
    var CRACK_OPACITY = [0.55, 0.55, 0.35, 0.15, 0.1, 0.08, 0, 0];
    var SPARSE_OPACITY = [0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.9, 0];
    var FILL_OPACITY = [0, 0, 0, 0.75, 0.8, 0.8, 0.9, 0];
    var HUB_OPACITY = [0, 0, 0, 0, 0.9, 0.9, 0.9, 0];
    var THREAD_OPACITY = [0.85, 0.85, 1, 1, 1, 1, 1, 0];
    var GLOW_OPACITY = [0.05, 0.05, 0.05, 0.07, 0.1, 0.22, 0.18, 0];
    var EMISSIVE_INTENSITY = [0.6, 0.6, 0.6, 0.7, 0.8, 0.9, 1.1, 1.1];
    var AMBIENT_COLOR = [ // THREE.Color-style 0-1 floats; scenes 0-4 keep the original cool tone,
      // 5 onward (Shared Responsibility) warms and greens it -- never reverts, carrying into 2126.
      { r: 0x4a / 255, g: 0x4a / 255, b: 0x72 / 255 },
      { r: 0x4a / 255, g: 0x4a / 255, b: 0x72 / 255 },
      { r: 0x4a / 255, g: 0x4a / 255, b: 0x72 / 255 },
      { r: 0x4a / 255, g: 0x4a / 255, b: 0x72 / 255 },
      { r: 0x4a / 255, g: 0x4a / 255, b: 0x72 / 255 },
      { r: 0x5c / 255, g: 0x74 / 255, b: 0x56 / 255 },
      { r: 0x5c / 255, g: 0x74 / 255, b: 0x56 / 255 },
      { r: 0x5c / 255, g: 0x74 / 255, b: 0x56 / 255 },
    ];
    var EARTH_SCALE = [1, 1, 1, 1, 1, 1, 1, 0.4];
    var EARTH_OPACITY = [1, 1, 1, 1, 1, 1, 1, 0];

    function tweenOrSet(target, props, duration) {
      if (reducedMotion || typeof gsap === "undefined") {
        Object.keys(props).forEach(function (k) { if (k !== "ease" && k !== "onUpdate" && k !== "stagger" && k !== "delay" && k !== "repeat" && k !== "yoyo") target[k] = props[k]; });
        if (props.onUpdate) props.onUpdate();
        return;
      }
      gsap.to(target, Object.assign({ duration: duration }, props));
    }

    function startHubPulse() {
      if (hubPulseStarted || reducedMotion || typeof gsap === "undefined") return;
      hubPulseStarted = true;
      // A slow, gentle breathing loop -- "alive," never distracting; respects reduced-motion by
      // simply never starting (the hub glow still shows at its base opacity via tweenOrSet above).
      gsap.to(hubGlow.material, { opacity: HUB_OPACITY[4] * 0.55, duration: 2.2, repeat: -1, yoyo: true, ease: "sine.inOut" });
    }

    function play(index) {
      tweenOrSet(camera.position, CAMERA_POS[index], 1.6);
      tweenOrSet(ambientLight.color, AMBIENT_COLOR[index], 1.6);
      tweenOrSet(glowMat, { opacity: GLOW_OPACITY[index] }, 1.6);
      tweenOrSet(earthMat, { emissiveIntensity: EMISSIVE_INTENSITY[index], opacity: EARTH_OPACITY[index] }, 1.6);
      tweenOrSet(earthGroup.scale, EARTH_SCALE[index], 1.8);
      crackLines.forEach(function (l) { tweenOrSet(l.material, { opacity: CRACK_OPACITY[index] }, 1.2); });
      tweenOrSet(sparseNodes.material, { opacity: SPARSE_OPACITY[index] }, 1.4);
      tweenOrSet(fillNodes.material, { opacity: FILL_OPACITY[index] }, 1.4);
      tweenOrSet(hubGlow.material, { opacity: HUB_OPACITY[index] }, 1.4);

      if (index === 2) {
        // One-shot: grow the Thread's arcs, staggered, the first time this scene is reached.
        threadLines.forEach(function (line, i) {
          var proxy = { n: 0 };
          var max = line.geometry.attributes.position.count;
          if (reducedMotion || typeof gsap === "undefined") {
            line.geometry.setDrawRange(0, max);
          } else {
            gsap.to(proxy, {
              n: max, duration: 1.1, delay: i * 0.18, ease: "power1.out",
              onUpdate: function () { line.geometry.setDrawRange(0, Math.floor(proxy.n)); },
            });
          }
        });
      } else {
        threadLines.forEach(function (l) { tweenOrSet(l.material, { opacity: THREAD_OPACITY[index] }, 1.2); });
      }
      if (index === 4) startHubPulse();
      if (index === 7) threadLines.forEach(function (l) { tweenOrSet(l.material, { opacity: 0 }, 1.8); });
    }

    function focus(index) {
      // Re-entering an already-played scene (scrolled back up and down again, in either
      // direction): snap/tween to that scene's resting values without replaying the Thread's own
      // one-shot growth (its drawRange stays fully grown from Scene 2 onward either way) or
      // restarting the hub pulse loop (it just keeps running once begun).
      tweenOrSet(camera.position, CAMERA_POS[index], 1.0);
      tweenOrSet(ambientLight.color, AMBIENT_COLOR[index], 1.0);
      tweenOrSet(glowMat, { opacity: GLOW_OPACITY[index] }, 0.8);
      tweenOrSet(earthMat, { emissiveIntensity: EMISSIVE_INTENSITY[index], opacity: EARTH_OPACITY[index] }, 0.8);
      tweenOrSet(earthGroup.scale, EARTH_SCALE[index], 0.8);
      crackLines.forEach(function (l) { tweenOrSet(l.material, { opacity: CRACK_OPACITY[index] }, 0.8); });
      tweenOrSet(sparseNodes.material, { opacity: SPARSE_OPACITY[index] }, 0.8);
      tweenOrSet(fillNodes.material, { opacity: FILL_OPACITY[index] }, 0.8);
      if (!hubPulseStarted) tweenOrSet(hubGlow.material, { opacity: HUB_OPACITY[index] }, 0.8);
      threadLines.forEach(function (l) { tweenOrSet(l.material, { opacity: THREAD_OPACITY[index] }, 0.8); });
      if (index >= 4) startHubPulse();
    }

    // ==================== Render loop, resize, visibility, pointer parallax, disposal ====================
    function onResize() {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }
    window.addEventListener("resize", onResize);

    var paused = false;
    document.addEventListener("visibilitychange", function () { paused = document.hidden; });

    if (!reducedMotion) {
      window.addEventListener("pointermove", function (e) {
        pointerX = (e.clientX / window.innerWidth - 0.5) * 2;
        pointerY = (e.clientY / window.innerHeight - 0.5) * 2;
      }, { passive: true });
    }

    function animate() {
      if (disposed) return;
      rafId = requestAnimationFrame(animate);
      if (paused) return;
      if (!reducedMotion) {
        earthGroup.rotation.y += 0.0012;
        // Gentle pointer parallax: nudges where the camera looks, never where it sits, so the
        // scene-choreography tweens above (which animate camera.position directly) are never
        // fought over by this per-frame effect.
        camera.lookAt(pointerX * 0.6, pointerY * -0.4, 0);
      } else {
        camera.lookAt(0, 0, 0);
      }
      renderer.render(scene, camera);
    }
    animate();

    function dispose() {
      if (disposed) return;
      disposed = true;
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener("resize", onResize);
      scene.traverse(function (obj) {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
          if (obj.material.map) obj.material.map.dispose();
          obj.material.dispose();
        }
      });
      renderer.dispose();
    }
    window.addEventListener("pagehide", dispose);

    return { play: play, focus: focus, dispose: dispose };
  }
})();
