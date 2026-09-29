/**
 * i18n.js — dashboard language switcher.
 *
 * A user keeps at most 3 languages: mother tongue, English, and an optional daily-use one
 * (QM_LANGS, from the server). The small dot in the top bar switches the dashboard text between them.
 * Text lives in the tables below keyed by data-i18n; a language without a table yet falls back to English.
 */
(function () {
  "use strict";

  var T = {
    en: {},
    bn: {
      dashboard: "ড্যাশবোর্ড", logout: "লগআউট", tab_global: "বৈশ্বিক", tab_public: "সার্বজনীন", tab_personal: "ব্যক্তিগত", tab_private: "গোপনীয়",
      kundali: "কুণ্ডলী", edit_profile: "প্রোফাইল সম্পাদনা", identity: "পরিচয়", private_id: "প্রাইভেট আইডি", account_id: "অ্যাকাউন্ট আইডি",
      locations: "অবস্থান", birth: "জন্মস্থান", present: "বর্তমান", zodiac: "রাশি", sun: "সূর্য", moon: "চন্দ্র", ascendant: "লগ্ন",
      contact: "যোগাযোগ", email: "ইমেইল", phone: "ফোন", languages: "ভাষা", lang_hint: "সর্বোচ্চ ৩টি · উপরের বার থেকে বদলান",
      mother_tongue: "মাতৃভাষা", second_lang: "দ্বিতীয় ভাষা", locked: "নির্ধারিত", daily_lang: "দৈনন্দিন ভাষা (ঐচ্ছিক)", save: "সংরক্ষণ",
      elemental: "পঞ্চতত্ত্ব ভারসাম্য", dominant: "প্রধান", wallet: "কর্ম কয়েন ওয়ালেট", donate: "দান করুন →", activities: "সাম্প্রতিক কার্যকলাপ",
      kundali_title: "আপনার বৈদিক জন্মকুণ্ডলী", planet: "গ্রহ", sign: "রাশি", degree: "অংশ", nakshatra: "নক্ষত্র", lord: "অধিপতি"
    },
    hi: {
      dashboard: "डैशबोर्ड", logout: "लॉगआउट", tab_global: "वैश्विक", tab_public: "सार्वजनिक", tab_personal: "व्यक्तिगत", tab_private: "निजी",
      kundali: "कुंडली", edit_profile: "प्रोफ़ाइल संपादित करें", identity: "पहचान", private_id: "प्राइवेट आईडी", account_id: "अकाउंट आईडी",
      locations: "स्थान", birth: "जन्म स्थान", present: "वर्तमान", zodiac: "राशि", sun: "सूर्य", moon: "चंद्र", ascendant: "लग्न",
      contact: "संपर्क", email: "ईमेल", phone: "फ़ोन", languages: "भाषाएँ", lang_hint: "अधिकतम 3 · ऊपर की पट्टी से बदलें",
      mother_tongue: "मातृभाषा", second_lang: "दूसरी भाषा", locked: "निश्चित", daily_lang: "दैनिक उपयोग की भाषा (वैकल्पिक)", save: "सहेजें",
      elemental: "तत्व संतुलन", dominant: "प्रधान", wallet: "कर्म कॉइन वॉलेट", donate: "दान करें →", activities: "हाल की गतिविधियाँ",
      kundali_title: "आपकी वैदिक जन्म कुंडली", planet: "ग्रह", sign: "राशि", degree: "अंश", nakshatra: "नक्षत्र", lord: "स्वामी"
    }
  };
  window.QM_T = T;

  var KEY = "qm_ui_lang";
  var langs = window.QM_LANGS || [];
  var btn = document.getElementById("ui-lang-btn"), menu = document.getElementById("ui-lang-menu"), wrap = document.getElementById("ui-lang-wrap");
  var current = "en";
  try { current = localStorage.getItem(KEY) || "en"; } catch (e) {}
  if (!langs.some(function (l) { return l.code === current; })) current = "en";

  function tr(key, fallback) { return (T[current] && T[current][key]) || fallback; }
  window.qmTr = tr;

  function apply() {
    document.documentElement.setAttribute("lang", current);
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"), function (el) {
      if (el.__en === undefined) el.__en = el.textContent;
      el.textContent = tr(el.getAttribute("data-i18n"), el.__en);
    });
    var cur = langs.filter(function (l) { return l.code === current; })[0];
    btn.textContent = cur ? cur.native : "English";
    Array.prototype.forEach.call(menu.querySelectorAll("button"), function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-code") === current);
    });
    document.dispatchEvent(new CustomEvent("qm-lang", { detail: current }));
  }

  langs.forEach(function (l) {
    var li = document.createElement("li"), b = document.createElement("button");
    b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("data-code", l.code); b.setAttribute("lang", l.code);
    b.innerHTML = "<span></span><i>✓</i>"; b.firstChild.textContent = l.native + (l.native !== l.name ? " · " + l.name : "");
    b.addEventListener("click", function () {
      current = l.code; try { localStorage.setItem(KEY, current); } catch (e) {}
      close(); apply();
    });
    li.appendChild(b); menu.appendChild(li);
  });
  function close() { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); }
  btn.addEventListener("click", function (e) {
    e.stopPropagation(); var open = menu.hidden; close();
    if (open) { menu.hidden = false; btn.setAttribute("aria-expanded", "true"); }
  });
  document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) close(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  apply();
})();
