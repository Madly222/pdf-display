(function () {
  var theme = "light";
  try {
    theme = localStorage.getItem("pd-theme") === "dark" ? "dark" : "light";
  } catch (e) {}
  document.documentElement.setAttribute("data-theme", theme);
})();
