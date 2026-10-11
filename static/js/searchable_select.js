/**
 * searchable_select.js — wraps a plain <select> with a searchable, clearable
 * dropdown UI (search-as-you-type, keyboard nav, clear button), while the
 * original <select> stays in the DOM (hidden) as the actual form-state
 * holder. Existing code that reads `select.value` or listens for `change`
 * on the select keeps working unmodified — this only changes how the user
 * picks a value, not where that value lives.
 *
 * Since callers often repopulate a select's <option>s or set `.value`/
 * `.disabled` programmatically (which fires no native event), call
 * QMSearchableSelect.refresh(selectEl) — or refreshAll() to refresh every
 * enhanced select on the page — right after doing so.
 *
 * Usage:
 *   QMSearchableSelect.enhance(selectEl, { placeholder: "Select a country…" });
 *   QMSearchableSelect.refresh(selectEl);   // after repopulating options / .value
 *   QMSearchableSelect.refreshAll();        // refresh every enhanced select
 */
(function (global) {
  "use strict";

  var registry = [];

  function enhance(selectEl, opts) {
    opts = opts || {};
    var placeholder = opts.placeholder || "Select…";

    var wrapper = document.createElement("div");
    wrapper.className = "qm-ss";
    selectEl.parentNode.insertBefore(wrapper, selectEl);
    selectEl.style.display = "none";
    wrapper.appendChild(selectEl);

    var display = document.createElement("button");
    display.type = "button";
    display.className = "qm-ss-display";
    var displayLabel = document.createElement("span");
    displayLabel.className = "qm-ss-display-label";
    display.appendChild(displayLabel);
    wrapper.appendChild(display);

    var clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "qm-ss-clear";
    clearBtn.textContent = "✕";
    clearBtn.setAttribute("aria-label", "Clear selection");
    wrapper.appendChild(clearBtn);

    var panel = document.createElement("div");
    panel.className = "qm-ss-panel";
    var searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.className = "qm-ss-search";
    searchInput.placeholder = "Search…";
    searchInput.autocomplete = "off";
    var optionsList = document.createElement("div");
    optionsList.className = "qm-ss-options";
    var resultsCount = document.createElement("div");
    resultsCount.className = "qm-ss-results-count";
    panel.appendChild(searchInput);
    panel.appendChild(optionsList);
    panel.appendChild(resultsCount);
    wrapper.appendChild(panel);

    var allOptions = []; // [{value, label}], placeholder option excluded
    var filtered = [];
    var highlightIndex = -1;
    var searchTimer = null;
    var isOpen = false;

    function readOptionsFromSelect() {
      allOptions = [];
      Array.prototype.forEach.call(selectEl.options, function (o) {
        if (o.value === "") return;
        allOptions.push({ value: o.value, label: o.textContent });
      });
    }

    function currentLabel() {
      var opt = allOptions.filter(function (o) { return o.value === selectEl.value; })[0];
      return opt ? opt.label : "";
    }

    function renderDisplay() {
      var label = currentLabel();
      var first = selectEl.options[0];
      var shownPlaceholder = first && first.value === "" && first.textContent ? first.textContent : placeholder;
      displayLabel.textContent = label || shownPlaceholder;
      displayLabel.classList.toggle("qm-ss-placeholder", !label);
      clearBtn.classList.toggle("visible", !!label);
      display.disabled = selectEl.disabled;
      wrapper.classList.toggle("is-disabled", selectEl.disabled);
    }

    function scrollHighlightedIntoView() {
      var el = optionsList.children[highlightIndex];
      if (el) el.scrollIntoView({ block: "nearest" });
    }

    var RENDER_CAP = 100;

    function renderOptions() {
      optionsList.innerHTML = "";
      if (!filtered.length) {
        var empty = document.createElement("div");
        empty.className = "qm-ss-empty";
        empty.textContent = "No matches";
        optionsList.appendChild(empty);
        resultsCount.textContent = "";
        return;
      }
      var shown = filtered.slice(0, RENDER_CAP);
      shown.forEach(function (o, i) {
        var item = document.createElement("div");
        item.className = "qm-ss-option"
          + (o.value === selectEl.value ? " selected" : "")
          + (i === highlightIndex ? " highlighted" : "");
        item.textContent = o.label;
        item.addEventListener("mousedown", function (e) {
          e.preventDefault();
          selectValue(o.value);
        });
        optionsList.appendChild(item);
      });
      resultsCount.textContent = filtered.length > RENDER_CAP
        ? "Showing " + RENDER_CAP + " of " + filtered.length + ". Type more to narrow."
        : filtered.length + (filtered.length === 1 ? " option" : " options");
    }

    function filterOptions(term) {
      term = term.trim().toLowerCase();
      filtered = term ? allOptions.filter(function (o) { return o.label.toLowerCase().indexOf(term) !== -1; }) : allOptions.slice();
      highlightIndex = filtered.length ? 0 : -1;
      renderOptions();
    }

    function selectValue(value) {
      selectEl.value = value;
      selectEl.dispatchEvent(new Event("change", { bubbles: true }));
      closePanel();
      renderDisplay();
    }

    function openPanel() {
      if (selectEl.disabled) return;
      isOpen = true;
      panel.classList.add("show");
      searchInput.value = "";
      filterOptions("");
      searchInput.focus();
    }
    function closePanel() {
      isOpen = false;
      panel.classList.remove("show");
    }

    display.addEventListener("click", function () {
      if (isOpen) closePanel(); else openPanel();
    });
    clearBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      selectValue("");
    });
    searchInput.addEventListener("input", function () {
      var term = searchInput.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () { filterOptions(term); }, 150);
    });
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        highlightIndex = Math.min(highlightIndex + 1, Math.min(filtered.length, RENDER_CAP) - 1);
        renderOptions();
        scrollHighlightedIntoView();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        highlightIndex = Math.max(highlightIndex - 1, 0);
        renderOptions();
        scrollHighlightedIntoView();
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (highlightIndex >= 0 && filtered[highlightIndex]) selectValue(filtered[highlightIndex].value);
      } else if (e.key === "Escape") {
        closePanel();
      }
    });
    document.addEventListener("click", function (e) {
      if (isOpen && !wrapper.contains(e.target)) closePanel();
    });

    function refresh() {
      readOptionsFromSelect();
      renderDisplay();
      if (isOpen) filterOptions(searchInput.value);
    }
    selectEl.addEventListener("qm:refresh", refresh);
    // Also self-refresh on a plain native "change" -- covers any value
    // change that didn't go through this widget's own selectValue() (e.g.
    // another script, or a test harness, setting .value directly).
    selectEl.addEventListener("change", refresh);

    refresh();
    var instance = { refresh: refresh };
    registry.push(instance);
    return instance;
  }

  function refresh(selectEl) {
    selectEl.dispatchEvent(new Event("qm:refresh"));
  }
  function refreshAll() {
    registry.forEach(function (inst) { inst.refresh(); });
  }

  global.QMSearchableSelect = { enhance: enhance, refresh: refresh, refreshAll: refreshAll };
})(window);
