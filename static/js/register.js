/**
 * register.js — registration wizard orchestration (4 steps).
 *
 * Step 1 (Private Account): personal details + contact info + password —
 * everything /api/auth/register needs is collected up front now.
 * Step 2 (Global Account): Birth Location + Present Location, both on one
 * screen, Continent -> Country dropdowns (worldwide). The map is the Indian
 * Sub-continent as ONE highlighted region (no inner borders, no whole-Earth
 * view — see subcontinent.js); its 9 countries are also offered as quick-pick
 * chips under the map.
 * Step 3 (Public Account, conditional on the present location being in the
 * Indian Sub-continent: India, Nepal, Bhutan, Bangladesh, Myanmar, Sri Lanka,
 * Pakistan, Balochistan, Afghanistan): Birth/Present tabs, Zone/State/
 * District/Tehsil/Village dropdowns for whichever of the 9 countries is
 * selected. India additionally gets its clickable state map; the other 8 show
 * the Sub-continent map.
 * Step 4 (Review & Submit): shows everything collected, then POSTs the
 * whole thing to /api/auth/register in one call (which also sets the
 * session), and reveals the real Private ID / Account ID in place of the
 * Submit button. No Kundali screen here — that now lives on /dashboard.
 */
(function () {
  "use strict";

  var STEP_ORDER = ["private", "global", "public", "review"];
  var state = {
    currentStep: "private",
    maxStepIndex: 0,
    form: null,
    birthLocation: null,
    presentLocation: null,
    birthPublic: { zone: null, state: null, district: null, tehsil: null, village: null },
    presentPublic: { zone: null, state: null, district: null, tehsil: null, village: null },
    registeredResult: null,
  };

  var worldData = null;
  var indiaStates = null; // { zones: [...all 9 countries' zones, each tagged with country_id] }
  var indiaDistricts = null; // { states: { <stateId>: { districts: [...] } } } for all 9 countries
  var countryLabels = {}; // country id -> tier names (Zone/State/District/Tehsil/Village for India, each country's own for the rest)

  var screens = {
    private: document.getElementById("screen-private"),
    global: document.getElementById("screen-global"),
    public: document.getElementById("screen-public"),
    review: document.getElementById("screen-review"),
  };
  var stepEls = Array.prototype.slice.call(document.querySelectorAll(".qm-step"));

  var modal = document.getElementById("reg-modal");
  var modalText = document.getElementById("reg-modal-text");
  var modalDismiss = document.getElementById("reg-modal-dismiss");
  function showModal(text) { modalText.textContent = text; modal.hidden = false; }
  modalDismiss.addEventListener("click", function () { modal.hidden = true; });

  // ---- Shared lookups ----
  function findWorldEntry(qmCountryId) {
    if (!worldData || !qmCountryId) return null;
    for (var i = 0; i < worldData.continents.length; i++) {
      var c = worldData.continents[i];
      for (var j = 0; j < c.countries.length; j++) {
        if (c.countries[j].id === qmCountryId) return { continent: c, country: c.countries[j] };
      }
    }
    return null;
  }
  function findWorldEntryByCode(countryCode) {
    if (!worldData) return null;
    for (var i = 0; i < worldData.continents.length; i++) {
      var c = worldData.continents[i];
      for (var j = 0; j < c.countries.length; j++) {
        if (c.countries[j].code === countryCode) return { continent: c, country: c.countries[j] };
      }
    }
    return null;
  }
  function findContinentByCode(code) {
    if (!worldData) return null;
    for (var i = 0; i < worldData.continents.length; i++) {
      if (worldData.continents[i].code === code) return worldData.continents[i];
    }
    return null;
  }
  function findZoneById(id) {
    if (!indiaStates || !id) return null;
    return indiaStates.zones.filter(function (z) { return z.id === id; })[0] || null;
  }
  function findStateById(id) {
    if (!indiaStates || !id) return null;
    for (var i = 0; i < indiaStates.zones.length; i++) {
      var z = indiaStates.zones[i];
      for (var j = 0; j < z.states.length; j++) {
        if (z.states[j].id === id) return z.states[j];
      }
    }
    return null;
  }
  function findDistrictInState(stateId, districtId) {
    var stateData = indiaDistricts && indiaDistricts.states[stateId];
    if (!stateData || !districtId) return null;
    return stateData.districts.filter(function (d) { return d.id === districtId; })[0] || null;
  }
  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text);
  }

  // ---- Step navigation ----
  function goToStep(stepName) {
    state.currentStep = stepName;
    var idx = STEP_ORDER.indexOf(stepName);
    if (idx > state.maxStepIndex) state.maxStepIndex = idx;

    Object.keys(screens).forEach(function (name) {
      screens[name].classList.toggle("is-active", name === stepName);
    });
    stepEls.forEach(function (el) {
      var s = el.getAttribute("data-step");
      var sIdx = STEP_ORDER.indexOf(s);
      el.classList.toggle("is-active", s === stepName);
      el.classList.toggle("is-done", sIdx < idx);
    });

    if (stepName === "global") enterGlobalStep();
    if (stepName === "public") enterPublicStep();
    if (stepName === "review") renderReview();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  stepEls.forEach(function (el) {
    el.addEventListener("click", function () {
      var s = el.getAttribute("data-step");
      var sIdx = STEP_ORDER.indexOf(s);
      if (sIdx <= state.maxStepIndex) goToStep(s);
    });
  });

  // ==================== Step 1: Private Account ====================
  var privateForm = document.getElementById("private-form");
  var privateFormError = document.getElementById("private-form-error");

  // ---- Combined Date of Birth (Day/Month/Year selects, kept in sync with
  // a hidden field-dob) + a native date input behind a calendar icon for
  // people who'd rather pick from a calendar than scroll selects. ----
  var dobDaySelect = document.getElementById("field-dob-day");
  var dobMonthSelect = document.getElementById("field-dob-month");
  var dobYearSelect = document.getElementById("field-dob-year");
  var dobHidden = document.getElementById("field-dob");
  var dobNative = document.getElementById("field-dob-native");
  var dobCalendarBtn = document.getElementById("field-dob-calendar-btn");
  var MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  var todayISO = new Date().toISOString().slice(0, 10);
  var currentYear = new Date().getFullYear();
  dobNative.max = todayISO;

  MONTH_NAMES.forEach(function (name, i) {
    var opt = document.createElement("option");
    opt.value = String(i + 1); opt.textContent = name;
    dobMonthSelect.appendChild(opt);
  });
  for (var dobYear = currentYear; dobYear >= currentYear - 120; dobYear--) {
    var yearOpt = document.createElement("option");
    yearOpt.value = String(dobYear); yearOpt.textContent = String(dobYear);
    dobYearSelect.appendChild(yearOpt);
  }

  function populateDobDays() {
    var month = parseInt(dobMonthSelect.value, 10);
    var year = parseInt(dobYearSelect.value, 10);
    var daysInMonth = (month && year) ? new Date(year, month, 0).getDate() : 31;
    var currentDay = dobDaySelect.value;
    dobDaySelect.innerHTML = '<option value="">Day</option>';
    for (var d = 1; d <= daysInMonth; d++) {
      var opt = document.createElement("option");
      opt.value = String(d); opt.textContent = String(d);
      dobDaySelect.appendChild(opt);
    }
    if (currentDay && parseInt(currentDay, 10) <= daysInMonth) dobDaySelect.value = currentDay;
  }
  populateDobDays();

  function syncDobHidden() {
    var d = dobDaySelect.value, m = dobMonthSelect.value, y = dobYearSelect.value;
    dobHidden.value = (d && m && y) ? (y + "-" + m.padStart(2, "0") + "-" + d.padStart(2, "0")) : "";
  }
  dobMonthSelect.addEventListener("change", function () { populateDobDays(); syncDobHidden(); });
  dobYearSelect.addEventListener("change", function () { populateDobDays(); syncDobHidden(); });
  dobDaySelect.addEventListener("change", syncDobHidden);

  dobCalendarBtn.addEventListener("click", function () {
    if (typeof dobNative.showPicker === "function") dobNative.showPicker();
    else dobNative.focus();
  });
  dobNative.addEventListener("change", function () {
    if (!dobNative.value) return;
    var parts = dobNative.value.split("-");
    dobYearSelect.value = parts[0];
    dobMonthSelect.value = String(parseInt(parts[1], 10));
    populateDobDays();
    dobDaySelect.value = String(parseInt(parts[2], 10));
    syncDobHidden();
  });

  QMTimePicker.create({
    displayInput: document.getElementById("field-tob-display"),
    hiddenInput: document.getElementById("field-tob"),
    trigger: document.getElementById("field-tob-btn"),
    host: document.getElementById("tob-field"),
  });

  var genderInput = document.getElementById("field-gender");
  var genderButtons = Array.prototype.slice.call(document.querySelectorAll(".qm-gender-btn"));
  genderButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      genderInput.value = btn.getAttribute("data-gender");
      genderButtons.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
    });
  });

  // ---- Keep what was typed: a draft of Step 1 survives a page refresh (passwords are never stored) ----
  var DRAFT_KEY = "qm_reg_draft";
  var draftFields = ["field-first-name", "field-last-name", "field-language", "field-email", "field-phone"];
  function saveDraft() {
    try {
      var d = { gender: genderInput.value, dob: [dobDaySelect.value, dobMonthSelect.value, dobYearSelect.value], tob: document.getElementById("field-tob").value };
      draftFields.forEach(function (id) { d[id] = document.getElementById(id).value; });
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(d));
    } catch (e) {}
  }
  function restoreDraft() {
    var d = null;
    try { d = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || "null"); } catch (e) {}
    if (!d) return;
    draftFields.forEach(function (id) { if (d[id]) document.getElementById(id).value = d[id]; });
    if (d.gender) genderButtons.forEach(function (b) { if (b.getAttribute("data-gender") === d.gender) b.click(); });
    if (d.dob && d.dob[1] && d.dob[2]) {
      dobYearSelect.value = d.dob[2]; dobMonthSelect.value = d.dob[1]; populateDobDays(); dobDaySelect.value = d.dob[0]; syncDobHidden();
    }
    if (/^\d{2}:\d{2}$/.test(d.tob || "")) {
      var h = parseInt(d.tob.slice(0, 2), 10);
      document.getElementById("field-tob").value = d.tob;
      document.getElementById("field-tob-display").value =
        String(h % 12 === 0 ? 12 : h % 12).padStart(2, "0") + ":" + d.tob.slice(3) + " " + (h >= 12 ? "PM" : "AM");
    }
  }
  restoreDraft();
  privateForm.addEventListener("input", saveDraft);
  privateForm.addEventListener("change", saveDraft);
  genderButtons.forEach(function (b) { b.addEventListener("click", saveDraft); });

  var testPwBtn = document.getElementById("use-test-password");
  if (testPwBtn) testPwBtn.addEventListener("click", function () {
    document.getElementById("field-password").value = testPwBtn.getAttribute("data-pw");
    document.getElementById("field-password-confirm").value = testPwBtn.getAttribute("data-pw");
  });

  function validatePassword(password) {
    if (!/^\d{5}$/.test(password)) return { valid: false, message: "Your PIN must be exactly 5 digits" };
    return { valid: true, message: "PIN is valid" };
  }

  privateForm.addEventListener("submit", function (e) {
    e.preventDefault();
    privateFormError.hidden = true;

    var firstName = document.getElementById("field-first-name").value.trim();
    var lastName = document.getElementById("field-last-name").value.trim();
    var email = document.getElementById("field-email").value.trim();
    var password = document.getElementById("field-password").value;
    var confirmPassword = document.getElementById("field-password-confirm").value;

    if (!genderInput.value) {
      privateFormError.textContent = "Please select a gender";
      privateFormError.hidden = false;
      return;
    }
    if (!dobDaySelect.value || !dobMonthSelect.value || !dobYearSelect.value) {
      privateFormError.textContent = "Please select your full date of birth";
      privateFormError.hidden = false;
      return;
    }
    if (!document.getElementById("field-language").value) {
      privateFormError.textContent = "Please select your mother tongue";
      privateFormError.hidden = false;
      return;
    }
    if (!document.getElementById("field-tob").value) {
      privateFormError.textContent = "Please select your time of birth on the clock";
      privateFormError.hidden = false;
      return;
    }
    if (dobHidden.value > todayISO) {
      privateFormError.textContent = "Date of birth cannot be in the future";
      privateFormError.hidden = false;
      return;
    }
    if (password !== confirmPassword) {
      privateFormError.textContent = "The two PINs do not match";
      privateFormError.hidden = false;
      return;
    }
    var check = validatePassword(password);
    if (!check.valid) {
      privateFormError.textContent = check.message;
      privateFormError.hidden = false;
      return;
    }
    if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      privateFormError.textContent = "Invalid email address";
      privateFormError.hidden = false;
      return;
    }

    state.form = {
      name: firstName + " " + lastName,
      gender: document.getElementById("field-gender").value,
      dob: document.getElementById("field-dob").value,
      tob: document.getElementById("field-tob").value,
      language: document.getElementById("field-language").value.trim(),
      email: email,
      phone: document.getElementById("field-phone").value.trim(),
      pin: password,
    };
    state.zodiacPreview = null;
    fetch("/api/zodiac/preview?dob=" + encodeURIComponent(state.form.dob))
      .then(function (r) { return r.json(); })
      .then(function (data) { state.zodiacPreview = data; })
      .catch(function (err) { console.error("Failed to load zodiac preview", err); });
    goToStep("global");
  });

  // ==================== Step 2: Global Account ====================
  var globalTarget = "birth";
  var targetBirthBtn = document.getElementById("target-birth-btn");
  var targetPresentBtn = document.getElementById("target-present-btn");
  function setGlobalTarget(target) {
    globalTarget = target;
    targetBirthBtn.classList.toggle("is-active", target === "birth");
    targetPresentBtn.classList.toggle("is-active", target === "present");
    syncGlobalGlobeToTarget();
  }
  targetBirthBtn.addEventListener("click", function () { setGlobalTarget("birth"); });
  targetPresentBtn.addEventListener("click", function () { setGlobalTarget("present"); });

  var activeContinentCode = null;
  var globalBreadcrumb = document.getElementById("global-breadcrumb");
  var globalTooltip = document.getElementById("global-tooltip");
  var countryChipsEl = document.getElementById("global-country-chips");

  var globalGlobe = QMEarthGlobe.create(document.getElementById("global-earth-canvas"),
    QMSubcontinent.globeOptions({ tooltipEl: globalTooltip, onCountryPick: handleGlobalCountryPick }));

  function breadcrumbFor(loc) {
    if (!loc) return QMSubcontinent.NAME;
    if (QMSubcontinent.isMember(loc.country.code)) return QMSubcontinent.NAME + " › " + loc.country.name;
    return loc.continent.name + " › " + loc.country.name;
  }
  function setGlobalBreadcrumb(loc) { globalBreadcrumb.textContent = breadcrumbFor(loc); }

  function updateCountryChips() {
    var loc = globalTarget === "birth" ? state.birthLocation : state.presentLocation;
    Array.prototype.forEach.call(countryChipsEl.querySelectorAll("button"), function (btn) {
      btn.classList.toggle("is-active", !!loc && btn.getAttribute("data-country-id") === loc.country.id);
    });
  }

  function buildCountryChips() {
    countryChipsEl.innerHTML = "";
    QMSubcontinent.CODES.forEach(function (code) {
      var entry = findWorldEntryByCode(code);
      if (!entry) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "qm-subcontinent-chip";
      btn.setAttribute("data-country-id", entry.country.id);
      btn.textContent = entry.country.name;
      btn.addEventListener("click", function () { applyLocationSelection(globalTarget, entry); });
      countryChipsEl.appendChild(btn);
    });
  }

  // The map only ever shows the Sub-continent as one region -- choosing a
  // country changes the dropdowns, chips and breadcrumb, never the map.
  function focusContinentOnGlobe(code) {
    var continent = findContinentByCode(code);
    if (!continent) return null;
    activeContinentCode = code;
    return continent;
  }

  function syncGlobalGlobeToTarget() {
    var loc = globalTarget === "birth" ? state.birthLocation : state.presentLocation;
    setGlobalBreadcrumb(loc);
    updateCountryChips();
  }

  document.getElementById("global-reset-view-btn").addEventListener("click", function () {
    globalGlobe.resetView();
  });

  function handleGlobalCountryPick(feature) {
    if (feature && feature.properties.qm_country_id === "SUBCONTINENT") {
      showModal("Choose your country from the Indian Sub-continent list under the map, or from the dropdowns.");
    }
  }

  var birthContinentSelect = document.getElementById("birth-continent-select");
  var birthCountrySelect = document.getElementById("birth-country-select");
  var presentContinentSelect = document.getElementById("present-continent-select");
  var presentCountrySelect = document.getElementById("present-country-select");
  QMSearchableSelect.enhance(birthContinentSelect, { placeholder: "Select a continent…" });
  QMSearchableSelect.enhance(birthCountrySelect, { placeholder: "Select a country…" });
  QMSearchableSelect.enhance(presentContinentSelect, { placeholder: "Select a continent…" });
  QMSearchableSelect.enhance(presentCountrySelect, { placeholder: "Select a country…" });

  // Birth Location: anywhere on Earth (people are born everywhere), Asia
  // pre-selected. Present Location: Asia only, and only the 10 Sub-continent
  // countries -- Qumanity's Public timeline lives there.
  function populateContinentDropdown(select, onlyCode) {
    select.innerHTML = onlyCode ? "" : '<option value="">Select a continent…</option>';
    worldData.continents.filter(function (c) { return !onlyCode || c.code === onlyCode; }).forEach(function (c) {
      var opt = document.createElement("option");
      opt.value = c.code; opt.textContent = c.name;
      select.appendChild(opt);
    });
    if (onlyCode) { select.value = onlyCode; select.disabled = true; }
    QMSearchableSelect.refresh(select);
  }
  function countriesFor(continent, target) {
    var list = continent.countries.slice();
    var codes = QMSubcontinent.CODES;
    if (target === "present") {
      return codes.map(function (code) {
        return list.filter(function (co) { return co.code === code; })[0];
      }).filter(Boolean);
    }
    list.sort(function (a, b) {
      var ia = codes.indexOf(a.code), ib = codes.indexOf(b.code);
      if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      return a.name.localeCompare(b.name);
    });
    return list;
  }
  function populateCountryDropdown(select, continent, target) {
    select.innerHTML = '<option value="">Select a country…</option>';
    if (!continent) { select.disabled = true; QMSearchableSelect.refresh(select); return; }
    countriesFor(continent, target).forEach(function (co) {
      var opt = document.createElement("option");
      opt.value = co.id; opt.textContent = co.name;
      select.appendChild(opt);
    });
    select.disabled = false;
    QMSearchableSelect.refresh(select);
  }

  function applyLocationSelection(target, entry) {
    if (target === "present" && !QMSubcontinent.isMember(entry.country.code)) {
      showModal("Your present location must be in the Indian Sub-continent.");
      presentCountrySelect.value = state.presentLocation ? state.presentLocation.country.id : "";
      QMSearchableSelect.refreshAll();
      return;
    }
    var loc = { continent: entry.continent, country: entry.country };
    if (target === "birth") {
      state.birthLocation = loc;
      document.getElementById("selected-birth-location").textContent = entry.continent.name + " → " + entry.country.name;
      birthContinentSelect.value = entry.continent.code;
      populateCountryDropdown(birthCountrySelect, entry.continent, "birth");
      birthCountrySelect.value = entry.country.id;
    } else {
      state.presentLocation = loc;
      document.getElementById("selected-present-location").textContent = entry.continent.name + " → " + entry.country.name;
      presentCountrySelect.value = entry.country.id;
    }
    QMSearchableSelect.refreshAll();
    updatePublicAccountEligibility();

    if (target === globalTarget) {
      focusContinentOnGlobe(entry.continent.code);
      setGlobalBreadcrumb(loc);
      updateCountryChips();
    }

    if (target === "birth" && !state.presentLocation) setGlobalTarget("present");
  }

  birthContinentSelect.addEventListener("change", function () {
    setGlobalTarget("birth");
    var code = birthContinentSelect.value;
    if (!code) {
      birthCountrySelect.disabled = true;
      birthCountrySelect.innerHTML = '<option value="">Select a country…</option>';
      QMSearchableSelect.refresh(birthCountrySelect);
      return;
    }
    focusContinentOnGlobe(code);
    populateCountryDropdown(birthCountrySelect, findContinentByCode(code), "birth");
  });
  birthCountrySelect.addEventListener("change", function () {
    setGlobalTarget("birth");
    var entry = findWorldEntry(birthCountrySelect.value);
    if (entry) applyLocationSelection("birth", entry);
  });
  presentCountrySelect.addEventListener("change", function () {
    setGlobalTarget("present");
    var entry = findWorldEntry(presentCountrySelect.value);
    if (entry) applyLocationSelection("present", entry);
  });

  // The present location is always in the Sub-continent (enforced above), so
  // once it is set the Public account step is available.
  function updatePublicAccountEligibility() {
    var eligible = !!(state.presentLocation && QMSubcontinent.isMember(state.presentLocation.country.code));
    document.getElementById("public-account-cta").hidden = !eligible;
    document.getElementById("global-next-btn").hidden = eligible;
    return eligible;
  }

  function enterGlobalStep() {
    globalGlobe.resize();
  }

  function requireBothLocations() {
    var errorEl = document.getElementById("global-form-error");
    errorEl.hidden = true;
    if (!state.birthLocation || !state.presentLocation) {
      errorEl.textContent = "Please select both Birth Location and Present Location.";
      errorEl.hidden = false;
      return false;
    }
    return true;
  }

  document.getElementById("global-back-btn").addEventListener("click", function () { goToStep("private"); });
  document.getElementById("public-account-btn").addEventListener("click", function () {
    if (requireBothLocations()) goToStep("public");
  });
  document.getElementById("global-next-btn").addEventListener("click", function () {
    if (!requireBothLocations()) return;
    goToStep(updatePublicAccountEligibility() ? "public" : "review");
  });

  // ==================== Step 3: Public Account (conditional) ====================
  var activePublicTab = "birth";
  var publicBirthApplicable = false;
  var indiaMap = null;
  var publicTabBirthBtn = document.getElementById("public-tab-birth");
  var publicTabPresentBtn = document.getElementById("public-tab-present");
  var publicPanelBirth = document.getElementById("public-panel-birth");
  var publicPanelPresent = document.getElementById("public-panel-present");

  var publicCountryIds = { birth: null, present: null };
  var subGlobe = null;

  function locOfTarget(target) { return target === "birth" ? state.birthLocation : state.presentLocation; }
  function isIndiaTarget(target) {
    var loc = locOfTarget(target);
    return !!(loc && loc.country.code === "IND");
  }
  function indiaMapActiveFor(target) {
    return !!indiaMap && activePublicTab === target && isIndiaTarget(target);
  }

  // India keeps its clickable state map (state selection needs the state
  // borders); the other 8 countries show the Sub-continent as one region.
  // One map per tab, re-synced whenever the active tab changes.
  function syncPublicMapToActiveTab() {
    var india = isIndiaTarget(activePublicTab);
    document.getElementById("public-india-map-wrap").hidden = !india;
    document.getElementById("public-subcontinent-stage").hidden = india;
    if (india) {
      ensureIndiaMapPublic();
      indiaMap.resize();
      var bucket = activePublicTab === "birth" ? state.birthPublic : state.presentPublic;
      if (bucket.state) {
        indiaMap.zoomToState(bucket.state.id);
        if (bucket.district) indiaMap.highlightDistrictByName(bucket.district.name);
      } else if (bucket.zone) {
        indiaMap.setZoneFilter(bucket.zone.id);
      } else {
        indiaMap.reset();
      }
    } else {
      ensureSubGlobe();
      subGlobe.resize();
      var loc = locOfTarget(activePublicTab);
      document.getElementById("public-subcontinent-breadcrumb").textContent = breadcrumbFor(loc);
    }
  }

  function ensureSubGlobe() {
    if (subGlobe) return;
    subGlobe = QMEarthGlobe.create(document.getElementById("public-subcontinent-canvas"),
      QMSubcontinent.globeOptions({ onCountryPick: function () {} }));
    QMSubcontinent.loadData().then(function (data) { QMSubcontinent.apply(subGlobe, data); });
  }

  function setActivePublicTab(tab) {
    activePublicTab = tab;
    publicTabBirthBtn.classList.toggle("is-active", tab === "birth");
    publicTabPresentBtn.classList.toggle("is-active", tab === "present");
    publicPanelBirth.hidden = tab !== "birth";
    publicPanelPresent.hidden = tab !== "present";
    syncPublicMapToActiveTab();
  }
  publicTabBirthBtn.addEventListener("click", function () { setActivePublicTab("birth"); });
  publicTabPresentBtn.addEventListener("click", function () { setActivePublicTab("present"); });

  // Once Birth's Zone + State (the minimum meaningful selection) are both
  // set, auto-advance to the Present tab -- District/Tehsil/Village stay
  // editable by clicking back to the Birth tab.
  function maybeAutoAdvanceToPresent(target) {
    if (target !== "birth" || activePublicTab !== "birth") return;
    if (state.birthPublic.zone && state.birthPublic.state) setActivePublicTab("present");
  }

  function ensureIndiaMapPublic() {
    if (indiaMap) return;
    indiaMap = QMIndiaMap.create(document.getElementById("public-india-map"), {
      onStateConfirm: function (stateProps) { applyPublicStateSelection(activePublicTab, stateProps); },
    });
  }

  // Placeholder text for a public-step select, in the country's own tier name.
  function ph(select, level) {
    var target = select.id.split("-")[0];
    var labels = countryLabels[publicCountryIds[target]] || {};
    return "Select a " + (labels[level] || level).toLowerCase() + "…";
  }

  // Zone/State/District/Tehsil/Village for India; each other country uses its
  // own tier names (Province / District / Local Level / Ward ...) and hides
  // tiers it doesn't have (the single zone, Afghanistan's tehsil).
  function applyTierLabels(target, countryId) {
    var labels = countryLabels[countryId] || {};
    ["zone", "state", "district", "tehsil", "village"].forEach(function (level) {
      var select = document.getElementById(target + "-" + level + "-select");
      var row = select.closest("label");
      var text = labels[level];
      row.hidden = !text;
      var span = row.querySelector(":scope > span");
      if (span && text) span.textContent = text;
    });
  }

  function zonesForCountry(countryId) {
    return indiaStates.zones.filter(function (z) { return z.country_id === countryId; });
  }
  function populateZoneDropdown(select, countryId) {
    select.innerHTML = '<option value="">' + ph(select, "zone") + '</option>';
    zonesForCountry(countryId).forEach(function (z) {
      var opt = document.createElement("option");
      opt.value = z.id; opt.textContent = z.name;
      select.appendChild(opt);
    });
    QMSearchableSelect.refresh(select);
  }
  function populateStateDropdown(select, zone) {
    select.innerHTML = '<option value="">' + ph(select, "state") + '</option>';
    if (!zone) { select.disabled = true; QMSearchableSelect.refresh(select); return; }
    zone.states.slice().sort(function (a, b) { return a.name.localeCompare(b.name); }).forEach(function (s) {
      var opt = document.createElement("option");
      opt.value = s.id; opt.textContent = s.name;
      select.appendChild(opt);
    });
    select.disabled = false;
    QMSearchableSelect.refresh(select);
  }
  function populateDistrictDropdown(select, stateEntry) {
    select.innerHTML = '<option value="">' + ph(select, "district") + '</option>';
    var stateData = stateEntry && indiaDistricts.states[stateEntry.id];
    if (!stateData) { select.disabled = true; QMSearchableSelect.refresh(select); return; }
    stateData.districts.forEach(function (d) {
      var opt = document.createElement("option");
      opt.value = d.id; opt.textContent = d.name;
      select.appendChild(opt);
    });
    select.disabled = false;
    QMSearchableSelect.refresh(select);
  }
  function populateTehsilDropdown(select, district) {
    select.innerHTML = '<option value="">' + ph(select, "tehsil") + '</option>';
    if (!district) { select.disabled = true; QMSearchableSelect.refresh(select); return; }
    if (!district.tehsils.length) {
      select.innerHTML = '<option value="">No tehsils in this district</option>';
      select.disabled = true;
      QMSearchableSelect.refresh(select);
      return;
    }
    district.tehsils.forEach(function (t) {
      var opt = document.createElement("option");
      opt.value = t.id; opt.textContent = t.name;
      select.appendChild(opt);
    });
    select.disabled = false;
    QMSearchableSelect.refresh(select);
  }

  // "Maldives → Maldives → Haa Dhaalu Atoll" reads better as "Maldives → Haa Dhaalu Atoll".
  function dedupe(parts) {
    return parts.filter(function (p, i) { return i === 0 || p !== parts[i - 1]; });
  }

  function recordPublicSelection(target, partial) {
    var bucket = target === "birth" ? state.birthPublic : state.presentPublic;
    Object.assign(bucket, partial);
    updatePublicSummary(target);
  }
  function updatePublicSummary(target) {
    var bucket = target === "birth" ? state.birthPublic : state.presentPublic;
    var el = document.getElementById(target === "birth" ? "selected-birth-zone-state" : "selected-present-zone-state");
    if (!bucket.zone) { el.textContent = "—"; return; }
    var parts = [bucket.zone.name];
    if (bucket.state) parts.push(bucket.state.name);
    if (bucket.district) parts.push(bucket.district.name);
    if (bucket.tehsil) parts.push(bucket.tehsil.name);
    if (bucket.village) parts.push(bucket.village.name);
    el.textContent = dedupe(parts).join(" → ");
  }

  function populateVillageDropdown(select, tehsilId) {
    select.innerHTML = '<option value="">' + ph(select, "village") + '</option>';
    select.disabled = true;
    QMSearchableSelect.refresh(select);
    if (!tehsilId) return;
    fetch("/api/india-villages/" + encodeURIComponent(tehsilId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        (data.villages || []).forEach(function (v) {
          var opt = document.createElement("option");
          opt.value = v.id; opt.textContent = v.name;
          select.appendChild(opt);
        });
        select.disabled = false;
        QMSearchableSelect.refresh(select);
      })
      .catch(function (err) { console.error("Failed to load villages", err); });
  }

  function applyPublicStateSelection(target, stateProps) {
    var prefix = target === "birth" ? "birth" : "present";
    var zoneSelect = document.getElementById(prefix + "-zone-select");
    var stateSelect = document.getElementById(prefix + "-state-select");
    var districtSelect = document.getElementById(prefix + "-district-select");
    var tehsilSelect = document.getElementById(prefix + "-tehsil-select");
    var villageSelect = document.getElementById(prefix + "-village-select");

    var zone = { id: stateProps.qm_zone_id, name: stateProps.qm_zone_name };
    var st = { id: stateProps.qm_state_id, name: stateProps.name };

    zoneSelect.value = zone.id;
    populateStateDropdown(stateSelect, findZoneById(zone.id));
    stateSelect.value = st.id;
    populateDistrictDropdown(districtSelect, st);
    tehsilSelect.innerHTML = '<option value="">' + ph(tehsilSelect, "tehsil") + '</option>';
    tehsilSelect.disabled = true;
    populateVillageDropdown(villageSelect, null);

    recordPublicSelection(target, { zone: zone, state: st, district: null, tehsil: null, village: null });
    QMSearchableSelect.refreshAll();
    if (indiaMapActiveFor(target)) indiaMap.zoomToState(st.id);
    maybeAutoAdvanceToPresent(target);
  }

  function wirePublicDropdowns(target) {
    var prefix = target === "birth" ? "birth" : "present";
    var zoneSelect = document.getElementById(prefix + "-zone-select");
    var stateSelect = document.getElementById(prefix + "-state-select");
    var districtSelect = document.getElementById(prefix + "-district-select");
    var tehsilSelect = document.getElementById(prefix + "-tehsil-select");
    var villageSelect = document.getElementById(prefix + "-village-select");

    zoneSelect.addEventListener("change", function () {
      var zone = findZoneById(zoneSelect.value);
      populateStateDropdown(stateSelect, zone);
      districtSelect.innerHTML = '<option value="">' + ph(districtSelect, "district") + '</option>'; districtSelect.disabled = true;
      tehsilSelect.innerHTML = '<option value="">' + ph(tehsilSelect, "tehsil") + '</option>'; tehsilSelect.disabled = true;
      populateVillageDropdown(villageSelect, null);
      recordPublicSelection(target, { zone: zone, state: null, district: null, tehsil: null, village: null });
      if (indiaMapActiveFor(target)) indiaMap.setZoneFilter(zone ? zone.id : null);
    });
    stateSelect.addEventListener("change", function () {
      var st = findStateById(stateSelect.value);
      populateDistrictDropdown(districtSelect, st);
      tehsilSelect.innerHTML = '<option value="">' + ph(tehsilSelect, "tehsil") + '</option>'; tehsilSelect.disabled = true;
      populateVillageDropdown(villageSelect, null);
      recordPublicSelection(target, { state: st, district: null, tehsil: null, village: null });
      if (st && indiaMapActiveFor(target)) indiaMap.zoomToState(st.id);
      maybeAutoAdvanceToPresent(target);
    });
    districtSelect.addEventListener("change", function () {
      var st = findStateById(stateSelect.value);
      var district = st && findDistrictInState(st.id, districtSelect.value);
      populateTehsilDropdown(tehsilSelect, district);
      populateVillageDropdown(villageSelect, district && district.direct_villages ? district.id : null);
      recordPublicSelection(target, { district: district, tehsil: null, village: null });
      if (district && indiaMapActiveFor(target)) indiaMap.highlightDistrictByName(district.name);
    });
    tehsilSelect.addEventListener("change", function () {
      var st = findStateById(stateSelect.value);
      var district = st && findDistrictInState(st.id, districtSelect.value);
      var tehsil = district && district.tehsils.filter(function (t) { return t.id === tehsilSelect.value; })[0];
      var villageParent = tehsil ? tehsil.id : (district && district.direct_villages ? district.id : null);
      populateVillageDropdown(villageSelect, villageParent);
      recordPublicSelection(target, { tehsil: tehsil || null, village: null });
    });
    villageSelect.addEventListener("change", function () {
      var village = villageSelect.value ? { id: villageSelect.value, name: villageSelect.options[villageSelect.selectedIndex].textContent } : null;
      recordPublicSelection(target, { village: village });
    });
  }
  wirePublicDropdowns("birth");
  wirePublicDropdowns("present");
  ["birth", "present"].forEach(function (prefix) {
    QMSearchableSelect.enhance(document.getElementById(prefix + "-zone-select"), { placeholder: "Select a zone…" });
    QMSearchableSelect.enhance(document.getElementById(prefix + "-state-select"), { placeholder: "Select a state…" });
    QMSearchableSelect.enhance(document.getElementById(prefix + "-district-select"), { placeholder: "Select a district…" });
    QMSearchableSelect.enhance(document.getElementById(prefix + "-tehsil-select"), { placeholder: "Select a tehsil…" });
    QMSearchableSelect.enhance(document.getElementById(prefix + "-village-select"), { placeholder: "Select a village…" });
  });

  function resetPublicTarget(target, countryId) {
    var prefix = target;
    var zoneSelect = document.getElementById(prefix + "-zone-select");
    var stateSelect = document.getElementById(prefix + "-state-select");
    var districtSelect = document.getElementById(prefix + "-district-select");
    var tehsilSelect = document.getElementById(prefix + "-tehsil-select");
    var villageSelect = document.getElementById(prefix + "-village-select");
    var blank = { zone: null, state: null, district: null, tehsil: null, village: null };

    Object.assign(target === "birth" ? state.birthPublic : state.presentPublic, blank);
    applyTierLabels(target, countryId);
    populateZoneDropdown(zoneSelect, countryId);
    populateStateDropdown(stateSelect, null);
    districtSelect.innerHTML = '<option value="">' + ph(districtSelect, "district") + '</option>'; districtSelect.disabled = true;
    tehsilSelect.innerHTML = '<option value="">' + ph(tehsilSelect, "tehsil") + '</option>'; tehsilSelect.disabled = true;
    populateVillageDropdown(villageSelect, null);

    // Every country except India has a single zone -- select it for them.
    var zones = zonesForCountry(countryId);
    if (zones.length === 1) {
      zoneSelect.value = zones[0].id;
      populateStateDropdown(stateSelect, zones[0]);
      recordPublicSelection(target, { zone: zones[0] });
      // ...and a country with a single state (Balochistan, Maldives) likewise.
      if (zones[0].states.length === 1) {
        var onlyState = zones[0].states[0];
        stateSelect.value = onlyState.id;
        populateDistrictDropdown(districtSelect, onlyState);
        recordPublicSelection(target, { state: onlyState });
      }
    }
    updatePublicSummary(target);
    QMSearchableSelect.refreshAll();
  }

  function enterPublicStep() {
    ["birth", "present"].forEach(function (target) {
      var loc = locOfTarget(target);
      var applicable = !!(loc && QMSubcontinent.isMember(loc.country.code));
      if (!applicable) {
        publicCountryIds[target] = null;
        Object.assign(target === "birth" ? state.birthPublic : state.presentPublic,
          { zone: null, state: null, district: null, tehsil: null, village: null });
        return;
      }
      if (publicCountryIds[target] !== loc.country.id) {
        publicCountryIds[target] = loc.country.id;
        resetPublicTarget(target, loc.country.id);
      }
      document.getElementById("public-" + target + "-heading").textContent =
        (target === "birth" ? "Birth" : "Present") + " Location (" + loc.country.name + ")";
    });

    publicBirthApplicable = !!publicCountryIds.birth;
    document.getElementById("public-birth-dropdowns").hidden = !publicBirthApplicable;
    document.getElementById("public-birth-not-applicable").hidden = publicBirthApplicable;
    document.getElementById("public-birth-summary-row").hidden = !publicBirthApplicable;
    publicTabBirthBtn.hidden = !publicBirthApplicable;
    setActivePublicTab(publicBirthApplicable ? "birth" : "present");
    updatePublicSummary("present");
    if (publicBirthApplicable) updatePublicSummary("birth");
  }

  document.getElementById("public-back-btn").addEventListener("click", function () { goToStep("global"); });
  document.getElementById("public-next-btn").addEventListener("click", function () {
    var errorEl = document.getElementById("public-form-error");
    errorEl.hidden = true;
    if (!state.presentPublic.state) {
      errorEl.textContent = "Please select at least a Zone and State for your present location.";
      errorEl.hidden = false;
      return;
    }
    goToStep("review");
  });

  // ==================== Step 4: Review & Submit ====================
  function renderList(id, rows) {
    var el = document.getElementById(id);
    el.innerHTML = "";
    rows.forEach(function (r) {
      var div = document.createElement("div");
      var dt = document.createElement("dt"); dt.textContent = r[0];
      var dd = document.createElement("dd"); dd.textContent = r[1] || "—";
      div.appendChild(dt); div.appendChild(dd);
      el.appendChild(div);
    });
  }
  function publicLocationLabel(bucket) {
    if (!bucket || !bucket.zone) return "Not applicable";
    var parts = [bucket.zone.name];
    if (bucket.state) parts.push(bucket.state.name);
    if (bucket.district) parts.push(bucket.district.name);
    if (bucket.tehsil) parts.push(bucket.tehsil.name);
    if (bucket.village) parts.push(bucket.village.name);
    return dedupe(parts).join(" → ");
  }

  function formatDobTimeDisplay(dobISO, tob24h) {
    var dobParts = (dobISO || "").split("-"); // YYYY-MM-DD
    var dobDisplay = dobParts.length === 3 ? (dobParts[2] + "/" + dobParts[1] + "/" + dobParts[0]) : "—";
    var timeParts = (tob24h || "").split(":");
    var timeDisplay = "—";
    if (timeParts.length === 2) {
      var hour = parseInt(timeParts[0], 10);
      var suffix = hour >= 12 ? "PM" : "AM";
      var hour12 = hour % 12 || 12;
      timeDisplay = (hour12 < 10 ? "0" + hour12 : hour12) + ":" + timeParts[1] + " " + suffix;
    }
    return dobDisplay + "  —  Time: " + timeDisplay;
  }

  function renderReview() {
    var f = state.form;
    if (!state.zodiacPreview) {
      fetch("/api/zodiac/preview?dob=" + encodeURIComponent(f.dob))
        .then(function (r) { return r.json(); })
        .then(function (data) { state.zodiacPreview = data; renderReview(); })
        .catch(function (err) { console.error("Failed to load zodiac preview", err); });
    }
    var zp = state.zodiacPreview;
    renderList("review-personal-list", [
      ["👤 Name", f.name], ["⚧️ Gender", f.gender],
      ["📅 Date & Time of Birth", formatDobTimeDisplay(f.dob, f.tob)],
      ["🎂 Age Category", zp ? (zp.age_code + " (" + zp.age_name + " – " + zp.age_range + ")") : "—"],
      ["✨ Zodiac", zp ? ("Sun in " + zp.sign + " (" + zp.element + ")") : "—"],
      ["🌐 Mother tongue", f.language], ["📧 Email", f.email || "—"], ["📱 Phone", f.phone || "—"],
    ]);
    renderList("review-global-list", [
      ["🌍 Birth Location", state.birthLocation ? state.birthLocation.continent.name + " → " + state.birthLocation.country.name : "—"],
      ["📍 Present Location", state.presentLocation ? state.presentLocation.continent.name + " → " + state.presentLocation.country.name : "—"],
    ]);
    if (updatePublicAccountEligibility()) {
      renderList("review-public-list", [
        ["🗺️ Birth Zone → State → District → Tehsil → Village", publicLocationLabel(state.birthPublic)],
        ["🗺️ Present Zone → State → District → Tehsil → Village", publicLocationLabel(state.presentPublic)],
      ]);
    } else {
      renderList("review-public-list", [["🗺️ Public Account", "Not applicable"]]);
    }
    document.getElementById("review-result").hidden = true;
    document.getElementById("review-submit-actions").hidden = false;
  }

  document.getElementById("review-back-btn").addEventListener("click", function () {
    goToStep(updatePublicAccountEligibility() ? "public" : "global");
  });

  function buildLocationPayload(base, publicBucket) {
    var loc = { continent: base.continent, country: base.country };
    if (publicBucket && publicBucket.zone) {
      loc.zone = publicBucket.zone;
      loc.state = publicBucket.state;
      if (publicBucket.district) loc.district = publicBucket.district;
      if (publicBucket.tehsil) loc.tehsil = publicBucket.tehsil;
      if (publicBucket.village) loc.village = publicBucket.village;
    }
    return loc;
  }

  var reviewSubmitBtn = document.getElementById("review-submit-btn");
  reviewSubmitBtn.addEventListener("click", function () {
    var errorEl = document.getElementById("review-error");
    errorEl.hidden = true;
    reviewSubmitBtn.disabled = true;
    reviewSubmitBtn.textContent = "Creating your account…";

    var payload = {
      name: state.form.name, gender: state.form.gender, dob: state.form.dob, tob: state.form.tob,
      language: state.form.language, email: state.form.email, phone: state.form.phone, pin: state.form.pin,
      birth_location: buildLocationPayload(state.birthLocation, state.birthPublic),
      present_location: buildLocationPayload(state.presentLocation, state.presentPublic),
      donation_amount: donateState.amount, referral_code: donateState.code, referrer_pin: donateState.pin,
      assisted: new URLSearchParams(location.search).get("assist") === "1",
    };

    fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
      .then(function (result) {
        if (!result.ok) throw new Error(result.body.error || "Registration failed");
        state.registeredResult = result.body;
        try { sessionStorage.removeItem("qm_reg_draft"); } catch (e) {}
        document.getElementById("review-private-id").textContent = result.body.private_code.replace(/(\d{3})(\d{3})(\d{3})/, "$1 $2 $3");
        document.getElementById("review-account-id").textContent = result.body.account_id;
        document.getElementById("review-submit-actions").hidden = true;
        document.getElementById("review-result").hidden = false;
      })
      .catch(function (err) {
        errorEl.textContent = "Could not complete registration: " + err.message;
        errorEl.hidden = false;
      })
      .finally(function () {
        reviewSubmitBtn.disabled = false;
        reviewSubmitBtn.textContent = "Submit →";
      });
  });

  document.getElementById("review-copy-private-btn").addEventListener("click", function () {
    if (state.registeredResult) copyToClipboard(state.registeredResult.private_code);
  });
  document.getElementById("review-copy-account-btn").addEventListener("click", function () {
    if (state.registeredResult) copyToClipboard(state.registeredResult.account_id);
  });
  document.getElementById("review-go-dashboard-btn").addEventListener("click", function () {
    if (state.registeredResult && state.registeredResult.assisted) { window.location.href = "/register"; return; }
    window.location.href = (state.registeredResult && state.registeredResult.redirect) || "/dashboard";
  });

  // ==================== Registration donation (optional) ====================
  var donateState = { amount: 0, code: "", pin: "" };
  var donateToggleEl = document.getElementById("donate-toggle");
  var donateBody = document.querySelector(".qm-donate-body");
  var donateAmounts = document.getElementById("donate-amounts");
  var donateCustom = document.getElementById("donate-custom");
  var donateCodeEl = document.getElementById("donate-referral-code");
  var donateConfirm = document.getElementById("donate-referrer-confirm");
  var donatePinEl = document.getElementById("donate-referrer-pin");
  var donatePreview = document.getElementById("donate-preview");
  var donatePreviewTimer = null;

  if (donateToggleEl) {
    donateToggleEl.addEventListener("change", function () {
      donateBody.hidden = !donateToggleEl.checked;
      if (!donateToggleEl.checked) { donateState.amount = 0; refreshDonatePreview(); }
    });
    donateAmounts.addEventListener("click", function (e) {
      var b = e.target.closest("[data-amt]"); if (!b) return;
      donateCustom.value = ""; setDonateAmount(parseInt(b.getAttribute("data-amt"), 10));
      Array.prototype.forEach.call(donateAmounts.querySelectorAll("button"), function (x) { x.classList.toggle("is-active", x === b); });
    });
    donateCustom.addEventListener("input", function () {
      Array.prototype.forEach.call(donateAmounts.querySelectorAll("button"), function (x) { x.classList.remove("is-active"); });
      setDonateAmount(Math.max(0, Math.min(200, parseInt(donateCustom.value, 10) || 0)));
    });
    donateCodeEl.addEventListener("input", function () {
      donateState.code = donateCodeEl.value.trim().toUpperCase();
      donateConfirm.hidden = !(donateState.code && donateState.amount > 0);
      refreshDonatePreview();
    });
    donatePinEl.addEventListener("input", function () { donateState.pin = donatePinEl.value.trim(); });
  }

  function setDonateAmount(n) {
    donateState.amount = n;
    donateConfirm.hidden = !(donateState.code && n > 0);
    refreshDonatePreview();
  }

  var DONATE_ICON = { earth: "🌍", continent: "🌎", country: "🌏", zone: "🗺️", state: "🏛️", district: "🏙️", tehsil: "🏘️", village: "🌳", referrer: "🤝", new_user: "🎁", village_wallet: "🌳" };
  function refreshDonatePreview() {
    clearTimeout(donatePreviewTimer);
    donatePreviewTimer = setTimeout(function () {
      var hasReferrer = !!donateState.code;
      fetch("/api/registration/donation-preview?amount=" + donateState.amount + "&referrer=" + (hasReferrer ? "1" : "0"))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          donatePreview.innerHTML = "";
          if (!d.rows) return;
          var unit = d.unit === "paisa" ? "p" : "₹";
          d.rows.forEach(function (row) {
            if (!row[1]) return;
            var key = row[0] === "village" && d.unit === "rupees" && !hasReferrer ? "village_wallet" : row[0];
            var div = document.createElement("div"); div.className = "qm-donate-row";
            var label = key === "new_user" ? "You" : key === "referrer" ? "Referrer (volunteer)" : key === "village_wallet" ? "Village" : key.charAt(0).toUpperCase() + key.slice(1);
            div.innerHTML = "<span>" + (DONATE_ICON[key] || "•") + " " + label + "</span><b>" + unit + row[1] + "</b>";
            donatePreview.appendChild(div);
          });
          if (d.note) { var n = document.createElement("p"); n.className = "qm-timeline-note"; n.textContent = d.note; donatePreview.appendChild(n); }
        })
        .catch(function () {});
    }, 150);
  }

  // ---- "Register New Member" assisted flow: a logged-in member is filling this in for someone else ----
  if (new URLSearchParams(location.search).get("assist") === "1") {
    var banner = document.createElement("p");
    banner.className = "qm-timeline-note";
    banner.style.cssText = "margin:0 0 16px;padding:10px 14px;border-radius:10px;background:rgba(255,153,51,0.12);border:1px solid rgba(255,210,74,0.4);";
    banner.textContent = "🧑\u200d🤝\u200d🧑 You're registering this account for someone else. Your own Account ID will be their referral, and you'll stay signed in to your own account afterward.";
    var intro = document.querySelector("#screen-private .qm-intro-card");
    if (intro) intro.parentNode.insertBefore(banner, intro.nextSibling);
    var goBtn = document.getElementById("review-go-dashboard-btn");
    if (goBtn) goBtn.textContent = "Register another member →";
  }

  // ==================== Init ====================
  function loadData() {
    return Promise.all([
      fetch("/api/world-data").then(function (r) { return r.json(); }),
      fetch("/api/subcontinent").then(function (r) { return r.json(); }),
      fetch("/api/subcontinent/districts").then(function (r) { return r.json(); }),
      QMSubcontinent.loadData(),
    ]).then(function (results) {
      worldData = results[0];
      indiaStates = { zones: [] };
      results[1].countries.forEach(function (country) {
        countryLabels[country.id] = country.labels;
        country.zones.forEach(function (zone) {
          indiaStates.zones.push(Object.assign({ country_id: country.id }, zone));
        });
      });
      indiaDistricts = results[2];
      QMSubcontinent.apply(globalGlobe, results[3]);
      populateContinentDropdown(birthContinentSelect);
      birthContinentSelect.value = "AS";
      populateCountryDropdown(birthCountrySelect, findContinentByCode("AS"), "birth");
      populateContinentDropdown(presentContinentSelect, "AS");
      populateCountryDropdown(presentCountrySelect, findContinentByCode("AS"), "present");
      QMSearchableSelect.refreshAll();
      buildCountryChips();
    });
  }

  loadData().then(function () {
    goToStep("private");
  }).catch(function (err) {
    console.error("Failed to load registration data", err);
  });
})();
