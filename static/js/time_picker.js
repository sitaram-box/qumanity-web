/**
 * time_picker.js — analog clock-face time picker (QMTimePicker.create).
 *
 * Click the field: pick the hour on the dial, it flips to minutes by itself,
 * pick the minute (any of the 60 positions, drag or tap), choose AM/PM, OK.
 * The visible field shows "07:05 AM"; the hidden field carries the 24-hour
 * "HH:MM" value the backend expects.
 */
(function (global) {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  var C = 120;          // dial centre (viewBox 240x240)
  var R_NUM = 92;       // radius of the number ring
  var R_HAND = 80;      // radius of the hand's knob

  function pad(n) { return n < 10 ? "0" + n : String(n); }

  function svgEl(name, attrs) {
    var el = document.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }

  function create(opts) {
    var display = opts.displayInput;
    var hidden = opts.hiddenInput;
    var trigger = opts.trigger;
    var host = opts.host;

    var st = { h: 6, m: 0, ap: "AM", mode: "hour" };
    var open = false;

    var pop = document.createElement("div");
    pop.className = "qm-tp";
    pop.hidden = true;
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", "Select time of birth");
    pop.innerHTML =
      '<div class="qm-tp-head">' +
        '<div class="qm-tp-time">' +
          '<button type="button" class="qm-tp-seg" data-seg="hour"></button>' +
          '<span class="qm-tp-colon">:</span>' +
          '<button type="button" class="qm-tp-seg" data-seg="minute"></button>' +
        '</div>' +
        '<div class="qm-tp-ampm">' +
          '<button type="button" data-ap="AM">AM</button>' +
          '<button type="button" data-ap="PM">PM</button>' +
        '</div>' +
      '</div>' +
      '<svg class="qm-tp-dial" viewBox="0 0 240 240" aria-hidden="true"></svg>' +
      '<p class="qm-tp-hint"></p>' +
      '<div class="qm-tp-actions">' +
        '<button type="button" class="qm-btn qm-btn-ghost" data-act="cancel">Cancel</button>' +
        '<button type="button" class="qm-btn qm-btn-primary" data-act="ok">OK</button>' +
      '</div>';
    var backdrop = document.createElement("div");
    backdrop.className = "qm-tp-backdrop"; backdrop.hidden = true;
    host.appendChild(backdrop);
    host.appendChild(pop);

    var hourSeg = pop.querySelector('[data-seg="hour"]');
    var minSeg = pop.querySelector('[data-seg="minute"]');
    var apBtns = Array.prototype.slice.call(pop.querySelectorAll("[data-ap]"));
    var dial = pop.querySelector(".qm-tp-dial");
    var hint = pop.querySelector(".qm-tp-hint");

    function to24() {
      var h = st.h % 12;
      if (st.ap === "PM") h += 12;
      return h;
    }

    function pointAt(angleDeg, radius) {
      var a = (angleDeg - 90) * Math.PI / 180;
      return { x: C + radius * Math.cos(a), y: C + radius * Math.sin(a) };
    }

    function renderDial() {
      dial.innerHTML = "";
      dial.appendChild(svgEl("circle", { cx: C, cy: C, r: 114, class: "qm-tp-face" }));

      var selValue = st.mode === "hour" ? st.h : st.m;
      var selAngle = st.mode === "hour" ? (st.h % 12) * 30 : st.m * 6;
      var tip = pointAt(selAngle, R_HAND);
      dial.appendChild(svgEl("line", { x1: C, y1: C, x2: tip.x, y2: tip.y, class: "qm-tp-hand" }));
      dial.appendChild(svgEl("circle", { cx: C, cy: C, r: 4, class: "qm-tp-pivot" }));

      if (st.mode === "minute") {
        for (var t = 0; t < 60; t++) {
          if (t % 5 === 0) continue;
          var p1 = pointAt(t * 6, 108), p2 = pointAt(t * 6, 103);
          dial.appendChild(svgEl("line", { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, class: "qm-tp-tick" }));
        }
      }
      dial.appendChild(svgEl("circle", { cx: tip.x, cy: tip.y, r: 18, class: "qm-tp-knob" }));

      var count = 12;
      for (var i = 0; i < count; i++) {
        var label = st.mode === "hour" ? (i === 0 ? 12 : i) : i * 5;
        var pos = pointAt(i * 30, R_NUM);
        var isSel = st.mode === "hour" ? (label === st.h) : (label === st.m);
        var txt = svgEl("text", { x: pos.x, y: pos.y, class: "qm-tp-num" + (isSel ? " is-sel" : ""), "text-anchor": "middle", "dominant-baseline": "central" });
        txt.textContent = st.mode === "hour" ? String(label) : pad(label);
        dial.appendChild(txt);
      }
      // A minute that isn't a multiple of 5 has no printed number -- show it on the knob.
      if (st.mode === "minute" && selValue % 5 !== 0) {
        var kt = svgEl("text", { x: tip.x, y: tip.y, class: "qm-tp-num is-sel", "text-anchor": "middle", "dominant-baseline": "central" });
        kt.textContent = pad(selValue);
        dial.appendChild(kt);
      }
    }

    function renderHead() {
      hourSeg.textContent = pad(st.h);
      minSeg.textContent = pad(st.m);
      hourSeg.classList.toggle("is-active", st.mode === "hour");
      minSeg.classList.toggle("is-active", st.mode === "minute");
      apBtns.forEach(function (b) { b.classList.toggle("is-active", b.getAttribute("data-ap") === st.ap); });
      hint.textContent = st.mode === "hour" ? "Tap the hour on the clock" : "Tap or drag to the minute";
    }

    function render() { renderHead(); renderDial(); }

    function valueFromEvent(e) {
      var rect = dial.getBoundingClientRect();
      var x = e.clientX - (rect.left + rect.width / 2);
      var y = e.clientY - (rect.top + rect.height / 2);
      var angle = Math.atan2(y, x) * 180 / Math.PI + 90;
      if (angle < 0) angle += 360;
      if (st.mode === "hour") {
        var h = Math.round(angle / 30) % 12;
        return h === 0 ? 12 : h;
      }
      return Math.round(angle / 6) % 60;
    }

    var dragging = false;
    dial.addEventListener("pointerdown", function (e) {
      dragging = true;
      dial.setPointerCapture(e.pointerId);
      apply(e);
    });
    dial.addEventListener("pointermove", function (e) { if (dragging) apply(e); });
    dial.addEventListener("pointerup", function (e) {
      if (!dragging) return;
      dragging = false;
      if (st.mode === "hour") { st.mode = "minute"; render(); }
    });
    function apply(e) {
      var v = valueFromEvent(e);
      if (st.mode === "hour") st.h = v; else st.m = v;
      render();
    }

    hourSeg.addEventListener("click", function () { st.mode = "hour"; render(); });
    minSeg.addEventListener("click", function () { st.mode = "minute"; render(); });
    apBtns.forEach(function (b) {
      b.addEventListener("click", function () { st.ap = b.getAttribute("data-ap"); render(); });
    });

    function commit() {
      hidden.value = pad(to24()) + ":" + pad(st.m);
      display.value = pad(st.h) + ":" + pad(st.m) + " " + st.ap;
      display.dispatchEvent(new Event("change", { bubbles: true }));
    }
    function openPop() {
      var cur = hidden.value;
      if (/^\d{2}:\d{2}$/.test(cur)) {
        var h24 = parseInt(cur.slice(0, 2), 10);
        st.ap = h24 >= 12 ? "PM" : "AM";
        st.h = h24 % 12 === 0 ? 12 : h24 % 12;
        st.m = parseInt(cur.slice(3), 10);
      }
      st.mode = "hour";
      render();
      pop.hidden = false; backdrop.hidden = false;
      open = true;
    }
    function closePop() { pop.hidden = true; backdrop.hidden = true; open = false; }
    backdrop.addEventListener("click", closePop);

    pop.querySelector('[data-act="ok"]').addEventListener("click", function () { commit(); closePop(); });
    pop.querySelector('[data-act="cancel"]').addEventListener("click", closePop);
    display.addEventListener("click", function () { open ? closePop() : openPop(); });
    trigger.addEventListener("click", function () { open ? closePop() : openPop(); });
    document.addEventListener("keydown", function (e) {
      if (!open) return;
      if (e.key === "Escape") closePop();
      if (e.key === "Enter") { commit(); closePop(); }
    });
    document.addEventListener("mousedown", function (e) {
      if (open && !host.contains(e.target)) closePop();
    });

    return { setValue24: function (v) { hidden.value = v; }, getValue24: function () { return hidden.value; } };
  }

  global.QMTimePicker = { create: create };
})(window);
