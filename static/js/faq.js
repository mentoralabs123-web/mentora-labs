/* Accessible, dependency-free FAQ search, category filtering and disclosure controls. */
(function () {
  "use strict";
  var search = document.getElementById("faqSearch");
  var clear = document.getElementById("faqClear");
  var categories = document.getElementById("faqCategories");
  var list = document.getElementById("faqList");
  if (!search || !categories || !list) return;

  var buttons = Array.prototype.slice.call(categories.querySelectorAll("[data-category]"));
  var groups = Array.prototype.slice.call(list.querySelectorAll("[data-category-group]"));
  var empty = document.getElementById("faqEmpty");
  var count = document.getElementById("faqResultCount");
  var activeCategory = "all";

  function update() {
    var term = search.value.trim().toLocaleLowerCase();
    var visible = 0;
    var visibleGroups = 0;
    groups.forEach(function (group) {
      var categoryMatch = activeCategory === "all" || group.getAttribute("data-category-group") === activeCategory;
      var groupCount = 0;
      Array.prototype.forEach.call(group.querySelectorAll("[data-faq-item]"), function (item) {
        var matches = categoryMatch && (!term || (item.getAttribute("data-search") || "").indexOf(term) !== -1);
        item.hidden = !matches;
        if (matches) { groupCount += 1; visible += 1; }
      });
      group.hidden = groupCount === 0;
      if (groupCount) visibleGroups += 1;
    });
    empty.hidden = visible !== 0;
    count.textContent = visible + (visible === 1 ? " answer" : " answers") + " in " + visibleGroups + (visibleGroups === 1 ? " topic" : " topics");
    clear.hidden = !search.value;
  }

  categories.addEventListener("click", function (event) {
    var button = event.target.closest("[data-category]");
    if (!button) return;
    activeCategory = button.getAttribute("data-category");
    buttons.forEach(function (item) {
      var selected = item === button;
      item.classList.toggle("is-active", selected);
      item.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    update();
  });
  search.addEventListener("input", update);
  function reset() {
    search.value = "";
    activeCategory = "all";
    buttons.forEach(function (button) {
      var selected = button.getAttribute("data-category") === "all";
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    update();
    search.focus();
  }
  clear.addEventListener("click", reset);
  document.getElementById("faqEmptyClear").addEventListener("click", reset);
  document.getElementById("faqExpand").addEventListener("click", function () {
    list.querySelectorAll(".faq-item:not([hidden])").forEach(function (item) { item.open = true; });
  });
  document.getElementById("faqCollapse").addEventListener("click", function () {
    list.querySelectorAll(".faq-item").forEach(function (item) { item.open = false; });
  });
  update();
}());
