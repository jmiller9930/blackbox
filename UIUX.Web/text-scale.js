/**
 * BLACK BOX — whole-page size control (− / +) with persisted zoom %.
 * Scales the entire view (including px-based layouts) via root zoom where supported.
 * Mounts on every page that loads this script; optional styles.css rules refine appearance.
 */
(function () {
  "use strict";

  var LS_PCT = "blackbox_page_zoom_pct";
  var LS_LEGACY = "blackbox_text_scale_v1";
  var MIN = 70;
  var MAX = 200;
  var STEP = 5;
  var DEFAULT_PCT = 100;

  var LEGACY_MAP = { "100": 100, "115": 115, "130": 130, "145": 145 };

  function clamp(n) {
    if (n < MIN) return MIN;
    if (n > MAX) return MAX;
    return n;
  }

  function readPct() {
    var raw = localStorage.getItem(LS_PCT);
    if (raw != null && raw !== "") {
      var n = parseInt(raw, 10);
      if (!isNaN(n)) return clamp(n);
    }
    var leg = localStorage.getItem(LS_LEGACY);
    if (leg && LEGACY_MAP.hasOwnProperty(leg)) {
      var m = LEGACY_MAP[leg];
      localStorage.setItem(LS_PCT, String(m));
      return m;
    }
    return DEFAULT_PCT;
  }

  function setPct(n) {
    n = clamp(n);
    localStorage.setItem(LS_PCT, String(n));
    return n;
  }

  function apply() {
    var pct = readPct();
    var html = document.documentElement;
    html.classList.remove("bb-text-scale-115", "bb-text-scale-130", "bb-text-scale-145");
    html.style.fontSize = "";
    var z = pct / 100;
    if (typeof html.style.zoom !== "undefined" && html.style.zoom !== null) {
      try {
        html.style.zoom = z;
        notifyScaleChange(pct);
        return;
      } catch (e) {}
    }
    html.style.fontSize = pct + "%";
    notifyScaleChange(pct);
  }

  /** Let layouts with sticky/scroll regions re-measure (zoom may not always fire resize). */
  function notifyScaleChange(pct) {
    try {
      window.dispatchEvent(new Event("resize"));
      window.dispatchEvent(new CustomEvent("bb:text-scale", { detail: { pct: pct } }));
    } catch (e) {}
  }

  function injectBaseStyles() {
    if (document.getElementById("bb-text-scale-injected-css")) return;
    var css =
      "#bb-text-scale-widget{position:fixed;top:max(10px,env(safe-area-inset-top));right:max(10px,env(safe-area-inset-right));z-index:2147483647;display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;max-width:min(100vw - 20px,20rem);padding:8px 10px;border-radius:12px;border:1px solid rgba(15,23,42,0.15);background:rgba(255,255,255,0.97);box-shadow:0 6px 24px rgba(15,23,42,0.12);font-family:system-ui,-apple-system,sans-serif;font-size:14px}" +
      "#bb-text-scale-widget .bb-ts-label{font-weight:700;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;width:100%;margin:0}" +
      "#bb-text-scale-widget .bb-ts-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px;width:100%}" +
      "#bb-text-scale-widget button.bb-ts-icon{min-width:40px;height:36px;padding:0 10px;border-radius:8px;border:1px solid #cbd5e1;background:#f1f5f9;color:#0f172a;font-size:18px;font-weight:700;line-height:1;cursor:pointer;font-family:inherit}" +
      "#bb-text-scale-widget button.bb-ts-icon:hover{background:#e2e8f0}" +
      "#bb-text-scale-widget button.bb-ts-reset{font-size:12px;padding:6px 10px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;color:#334155;cursor:pointer;font-family:inherit;font-weight:600}" +
      "#bb-text-scale-widget .bb-ts-readout{min-width:3.2rem;text-align:center;font-weight:800;font-variant-numeric:tabular-nums;color:#0f172a;font-size:13px}";
    var s = document.createElement("style");
    s.id = "bb-text-scale-injected-css";
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  }

  function mount() {
    if (!document.body) return;
    if (document.getElementById("bb-text-scale-widget")) return;

    injectBaseStyles();

    var pct = readPct();
    var wrap = document.createElement("div");
    wrap.id = "bb-text-scale-widget";
    wrap.className = "bb-text-scale-widget";
    wrap.setAttribute("role", "group");
    wrap.setAttribute(
      "aria-label",
      "Page size — whole-page zoom; use 100 percent for best alignment on dense grids"
    );
    wrap.setAttribute(
      "title",
      "Whole-page zoom (layout and text). Dense tables and sticky columns align most cleanly at 100%. If edges look off, choose Reset, then hard refresh."
    );

    var lab = document.createElement("span");
    lab.className = "bb-ts-label";
    lab.textContent = "Page size";
    wrap.appendChild(lab);

    var row = document.createElement("div");
    row.className = "bb-ts-row";

    var btnMinus = document.createElement("button");
    btnMinus.type = "button";
    btnMinus.className = "bb-ts-icon";
    btnMinus.setAttribute("aria-label", "Decrease page size");
    btnMinus.title = "Smaller";
    btnMinus.textContent = "−";

    var readout = document.createElement("span");
    readout.className = "bb-ts-readout";
    readout.setAttribute("aria-live", "polite");

    var btnPlus = document.createElement("button");
    btnPlus.type = "button";
    btnPlus.className = "bb-ts-icon";
    btnPlus.setAttribute("aria-label", "Increase page size");
    btnPlus.title = "Larger";
    btnPlus.textContent = "+";

    var btnReset = document.createElement("button");
    btnReset.type = "button";
    btnReset.className = "bb-ts-reset";
    btnReset.textContent = "Reset";
    btnReset.title = "Back to 100%";
    btnReset.setAttribute("aria-label", "Reset page size to default");

    function syncReadout() {
      pct = readPct();
      readout.textContent = pct + "%";
      btnMinus.disabled = pct <= MIN;
      btnPlus.disabled = pct >= MAX;
    }

    btnMinus.addEventListener("click", function () {
      setPct(readPct() - STEP);
      apply();
      syncReadout();
    });
    btnPlus.addEventListener("click", function () {
      setPct(readPct() + STEP);
      apply();
      syncReadout();
    });
    btnReset.addEventListener("click", function () {
      setPct(DEFAULT_PCT);
      apply();
      syncReadout();
    });

    row.appendChild(btnMinus);
    row.appendChild(readout);
    row.appendChild(btnPlus);
    row.appendChild(btnReset);
    wrap.appendChild(row);

    document.body.appendChild(wrap);
    syncReadout();
  }

  apply();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
