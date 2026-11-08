/**
 * future.js — Qumanity 3D Future Vision Experience (templates/future.html, 2026-11-08).
 *
 * Four scenes, driven by normal document scroll (never hijacked -- this script only reads scroll
 * position via IntersectionObserver, it never calls preventDefault on wheel/touch events):
 *   0. The Present   -- a fragmented Earth, fine luminous crack lines across the globe.
 *   1. The Thread    -- the Qumanity Tree: golden lines grow across the fractures, branching.
 *   2. The Future    -- cracks fade, the network brightens, small lit nodes (people/communities)
 *                       appear across the globe -- an illustrated vision, not live data.
 *   3. The Action    -- the globe recedes behind a CTA panel (plain HTML/CSS, not 3D -- no
 *                       fabricated statistics) inviting the visitor to register or sign in.
 *
 * One shared Three.js scene/camera/renderer persists across all four scenes; each scene only
 * changes material opacities, camera position, and which line/point groups are visible or
 * growing. No scene is ever rebuilt from scratch.
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

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var isMobile = window.innerWidth < 640;

  // ==================== Skip control (works even if Three.js/WebGL never loads) ====================
  // Fixed destination per the product brief: always the sign-in page, regardless of how far the
  // visitor has scrolled or whether they're already signed in (the authenticated-specific action
  // lives only in Scene 4's own CTA, rendered server-side in future.html).
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

  var playedScene = [false, false, false, false];

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
    var crackLines = [], threadLines = [], nodePoints;
    var rafId = null;
    var disposed = false;
    var pointerX = 0, pointerY = 0;
    var EARTH_R = 2.6;

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

    scene.add(new THREE.AmbientLight(0x4a4a72, 1.15));
    var sun = new THREE.DirectionalLight(0xfff2cc, 1.0);
    sun.position.set(5, 3, 5);
    scene.add(sun);

    // ---- Fractures (Scene 1): fine jagged crack lines, present from the start, dim reddish-gold. ----
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

    // ---- Nodes (Scene 3): small lit points representing people/communities, not live data. ----
    var NODE_COUNT = isMobile ? 90 : 180;
    var nodePositions = new Float32Array(NODE_COUNT * 3);
    for (var ni = 0; ni < NODE_COUNT; ni++) {
      var nlat = rng() * 160 - 80, nlng = rng() * 360 - 180;
      var v2 = latLngToVector3(nlat, nlng, EARTH_R * 1.015);
      nodePositions[ni * 3] = v2.x; nodePositions[ni * 3 + 1] = v2.y; nodePositions[ni * 3 + 2] = v2.z;
    }
    var nodeGeo = new THREE.BufferGeometry();
    nodeGeo.setAttribute("position", new THREE.BufferAttribute(nodePositions, 3));
    var nodeSpriteTex = (function () {
      var c = document.createElement("canvas"); c.width = c.height = 32;
      var g = c.getContext("2d");
      var grad = g.createRadialGradient(16, 16, 0, 16, 16, 16);
      grad.addColorStop(0, "rgba(255,245,210,1)");
      grad.addColorStop(0.5, "rgba(245,222,130,0.55)");
      grad.addColorStop(1, "rgba(245,222,130,0)");
      g.fillStyle = grad; g.fillRect(0, 0, 32, 32);
      return new THREE.CanvasTexture(c);
    })();
    var nodeMat = new THREE.PointsMaterial({
      size: isMobile ? 0.09 : 0.07, map: nodeSpriteTex, transparent: true, opacity: 0,
      depthWrite: false, blending: THREE.AdditiveBlending,
    });
    nodePoints = new THREE.Points(nodeGeo, nodeMat);
    earthGroup.add(nodePoints);

    // ==================== GSAP scene choreography ====================
    var tl = {}; // one timeline per scene index, built lazily on first play

    function tweenOrSet(target, props, duration) {
      if (reducedMotion || typeof gsap === "undefined") {
        Object.keys(props).forEach(function (k) { if (k !== "ease" && k !== "onUpdate" && k !== "stagger" && k !== "delay") target[k] = props[k]; });
        if (props.onUpdate) props.onUpdate();
        return;
      }
      gsap.to(target, Object.assign({ duration: duration }, props));
    }

    function play(index) {
      if (index === 0) {
        tweenOrSet(camera.position, { x: 0, y: 0.1, z: 7.4 }, 1.6);
        crackLines.forEach(function (l) { tweenOrSet(l.material, { opacity: 0.55 }, 1.2); });
      } else if (index === 1) {
        tweenOrSet(camera.position, { x: 0.6, y: 0.2, z: 6.4 }, 1.8);
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
      } else if (index === 2) {
        tweenOrSet(camera.position, { x: -0.4, y: 0.05, z: 5.6 }, 1.8);
        crackLines.forEach(function (l) { tweenOrSet(l.material, { opacity: 0 }, 1.4); });
        tweenOrSet(glowMat, { opacity: 0.16 }, 1.6);
        tweenOrSet(earthMat, { emissiveIntensity: 1.1 }, 1.6);
        threadLines.forEach(function (l) { tweenOrSet(l.material, { opacity: 1 }, 1.2); });
        tweenOrSet(nodeMat, { opacity: 0.9 }, 1.8);
      } else if (index === 3) {
        tweenOrSet(camera.position, { x: 0, y: 0, z: 10.5 }, 1.6);
        tweenOrSet(earthGroup.scale, { x: 0.4, y: 0.4, z: 0.4 }, 1.8);
        tweenOrSet(earthMat, { opacity: 0 }, 1.8);
        tweenOrSet(glowMat, { opacity: 0 }, 1.8);
        threadLines.forEach(function (l) { tweenOrSet(l.material, { opacity: 0 }, 1.8); });
        tweenOrSet(nodeMat, { opacity: 0 }, 1.8);
      }
    }

    function focus(index) {
      // Re-entering an already-played scene (scrolled back up and down again, in either
      // direction): snap camera and material state back to that scene's resting values without
      // replaying the one-shot growth animations (the thread lines' own drawRange stays as it
      // was -- already fully grown from scene 1 onward, which is correct either way).
      var positions = [
        { x: 0, y: 0.1, z: 7.4 }, { x: 0.6, y: 0.2, z: 6.4 }, { x: -0.4, y: 0.05, z: 5.6 }, { x: 0, y: 0, z: 10.5 },
      ];
      tweenOrSet(camera.position, positions[index], 1.0);
      if (index < 3) {
        tweenOrSet(earthGroup.scale, { x: 1, y: 1, z: 1 }, 0.8);
        tweenOrSet(earthMat, { opacity: 1 }, 0.8);
        tweenOrSet(glowMat, { opacity: index === 2 ? 0.16 : 0.05 }, 0.8);
        tweenOrSet(nodeMat, { opacity: index === 2 ? 0.9 : 0 }, 0.8);
        crackLines.forEach(function (l) { tweenOrSet(l.material, { opacity: index === 2 ? 0 : 0.55 }, 0.8); });
        threadLines.forEach(function (l) { tweenOrSet(l.material, { opacity: index === 0 ? 0.85 : 1 }, 0.8); });
      }
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
