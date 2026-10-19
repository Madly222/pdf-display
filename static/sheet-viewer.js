(function () {
  var tabs = document.querySelectorAll(".sv-tab");
  var sheets = document.querySelectorAll(".sv-sheet");
  var box = document.querySelector(".sv-sheets");

  function show(index) {
    for (var i = 0; i < sheets.length; i++) sheets[i].hidden = i !== index;
    for (var j = 0; j < tabs.length; j++) tabs[j].classList.toggle("active", j === index);
    box.scrollTop = 0;
    box.scrollLeft = 0;
  }

  for (var k = 0; k < tabs.length; k++) {
    tabs[k].addEventListener("click", function (e) {
      show(Number(e.currentTarget.getAttribute("data-index")));
    });
  }
})();
