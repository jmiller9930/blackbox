/**
 * BLACK BOX — root text scale for readability (persists in localStorage).
 * Load in <head> so the scale applies before first paint when possible.
 */
(function () {
  "use strict";

  var LS_KEY = "blackbox_text_scale_v1";
  var CLASSES = ["bb-text-scale-115", "bb-text-scale-130", "bb-text-scale-145"];

  function currentLevel() {
    var v = localStorage.getItem(LS_KEY);
    if (v === "115" || v === "130" || v === "145") return v;
    return "100";
  }

  function apply() {
    var html = document.documentElement;
    var level = currentLevel();
    var i;
    for (i = 0; i < CLASSES.length; i++) {
      html.classList.remove(CLASSES[i]);
    }
    if (level === "115") html.classList.add("bb-text-scale-115");
    else if (level === "130") html.classList.add("bb-text-scale-130");
    else if (level === "145") html.classList.add("bb-text-scale-145");
  }

  function mount() {
    if (!document.body || !document.body.hasAttribute("data-bb-text-scale")) return;
    if (document.getElementById("bb-text-scale-widget")) return;

    var levels = [
      { id: "100", label: "Default" },
      { id: "115", label: "Larger" },
      { id: "130", label: "Large" },
      { id: "145", label: "Largest" },
    ];

    var wrap = document.createElement("div");
    wrap.id = "bb-text-scale-widget";
    wrap.className = "bb-text-scale-widget";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", "Text size");

    var lab = document.createElement("span");
    lab.className = "bb-text-scale-widget__label";
    lab.textContent = "Text size";
    wrap.appendChild(lab);

    var cur = currentLevel();

    function setPressed() {
      var buttons = wrap.querySelectorAll(".bb-text-scale-widget__btn");
      var j;
      for (j = 0; j < buttons.length; j++) {
        var b = buttons[j];
        var on = b.getAttribute("data-level") === cur;
        b.setAttribute("aria-pressed", on ? "true" : "false");
      }
    }

    var k;
    for (k = 0; k < levels.length; k++) {
      (function (L) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "bb-text-scale-widget__btn";
        btn.setAttribute("data-level", L.id);
        btn.textContent = L.label;
        btn.title = "Set text size to " + L.label.toLowerCase();
        btn.addEventListener("click", function () {
          localStorage.setItem(LS_KEY, L.id);
          cur = L.id;
          apply();
          setPressed();
        });
        wrap.appendChild(btn);
      })(levels[k]);
    }

    document.body.appendChild(wrap);
    setPressed();
  }

  apply();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
