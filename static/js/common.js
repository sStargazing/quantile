/* Quantile — shared helpers: API access, URL state, formatting, safe DOM building. */
(function () {
  "use strict";

  const STORE_KEY = "quantile:selection";

  /* Errors carry `status` (0 = network) so pages can decide whether a retry makes sense. */
  async function fetchJSON(url) {
    let response;
    try {
      response = await fetch(url, { headers: { Accept: "application/json" } });
    } catch (e) {
      throw Object.assign(new Error("The Quantile server isn't responding. Check that it's running, then retry."), { status: 0 });
    }
    let body = null;
    try { body = await response.json(); } catch (e) { /* non-JSON error page */ }
    if (!response.ok) {
      let message = "The server returned an unexpected error (" + response.status + ").";
      if (body && typeof body.detail === "string") message = body.detail;
      else if (response.status === 422) message = "Check the values you entered.";
      throw Object.assign(new Error(message), { status: response.status });
    }
    return body;
  }

  /* Selection lives in the URL (?base=AUD&period=5y) so links are shareable;
     the last choice is also remembered per browser as a convenience. */
  function readSelection(defaults) {
    const params = new URLSearchParams(location.search);
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); } catch (e) { saved = {}; }
    return {
      base: (params.get("base") || saved.base || defaults.base).toUpperCase(),
      period: (params.get("period") || saved.period || defaults.period).toLowerCase(),
    };
  }

  function writeSelection(sel, replace) {
    const params = new URLSearchParams(location.search);
    params.set("base", sel.base);
    params.set("period", sel.period);
    const url = location.pathname + "?" + params.toString();
    (replace ? history.replaceState : history.pushState).call(history, sel, "", url);
    try { localStorage.setItem(STORE_KEY, JSON.stringify(sel)); } catch (e) { /* storage unavailable */ }
    syncNav(sel);
  }

  function selectionQuery(sel) {
    return "base=" + encodeURIComponent(sel.base) + "&period=" + encodeURIComponent(sel.period);
  }

  /* Leaderboard and World Map links carry the current selection, so switching keeps it. */
  function syncNav(sel) {
    for (const [id, path] of [["nav-leaderboard", "/"], ["nav-map", "/map"]]) {
      const link = document.getElementById(id);
      if (link) link.href = path + "?" + selectionQuery(sel);
    }
  }

  /* Segmented controls for home currency (AUD USD …) and period (1Y 3Y 5Y 10Y).
     A page may show the same control in more than one place (e.g. the period
     above the chart); every [data-control] copy stays in sync. */
  function segmented(kind, items, sel, onChange) {
    for (const container of document.querySelectorAll('[data-control="' + kind + '"]')) {
      container.replaceChildren();
      for (const item of items) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = item.text;
        b.title = item.title;
        b.dataset.value = item.value;
        b.addEventListener("click", () => {
          if (sel[kind] === item.value) return;
          sel[kind] = item.value;
          setControls(sel);
          onChange(sel);
        });
        container.appendChild(b);
      }
    }
  }

  function buildControls(options, sel, onChange) {
    if (!options.home_currencies.some(h => h.code === sel.base)) sel.base = options.default_base;
    if (!options.periods.some(p => p.key === sel.period)) sel.period = options.default_period;
    segmented("base", options.home_currencies.map(h => ({ value: h.code, text: h.code, title: h.currency_name + " (" + h.country + ")" })), sel, onChange);
    segmented("period", options.periods.map(p => ({ value: p.key, text: p.key.toUpperCase(), title: p.label })), sel, onChange);
    setControls(sel);
  }

  function setControls(sel) {
    for (const kind of ["base", "period"]) {
      for (const b of document.querySelectorAll('[data-control="' + kind + '"] button')) {
        b.setAttribute("aria-pressed", String(b.dataset.value === sel[kind]));
      }
    }
  }

  /* ---- formatting ---- */
  const nf = (min, max) => new Intl.NumberFormat(undefined, { minimumFractionDigits: min, maximumFractionDigits: max });
  const fmt0 = nf(0, 0), fmt1 = nf(1, 1), fmt2 = nf(2, 2), fmt4 = nf(4, 4);

  function rate(v) {
    if (v == null) return "—";
    const a = Math.abs(v);
    if (a >= 1000) return fmt0.format(v);
    if (a >= 10) return fmt2.format(v);
    return fmt4.format(v);
  }
  /* An amount in a currency with its own symbol: ¥109.36, Rp12,465, €0.6199 (same precision as rate()). */
  function money(v, code) {
    if (v == null) return "—";
    const a = Math.abs(v);
    const digits = a >= 1000 ? 0 : a >= 10 ? 2 : 4;
    try {
      return new Intl.NumberFormat("en", {
        style: "currency", currency: code, currencyDisplay: "narrowSymbol",
        minimumFractionDigits: digits, maximumFractionDigits: digits,
      }).format(v);
    } catch (e) {
      return rate(v) + " " + code;
    }
  }
  function signedPct(v, digits) {
    if (v == null) return "—";
    const f = digits === 0 ? fmt0 : fmt1;
    const s = f.format(Math.abs(v));
    if (s === f.format(0)) return s + "%";
    return (v > 0 ? "+" : "−") + s + "%";
  }
  function signedPts(v) {
    if (v == null) return "—";
    const s = fmt1.format(Math.abs(v));
    if (s === fmt1.format(0)) return "0.0 pts";
    return (v > 0 ? "+" : "−") + s + " pts";
  }
  function pct(v) { return v == null ? "—" : fmt1.format(v) + "%"; }
  function score(v) { return v == null ? "—" : fmt0.format(v); }
  function ordinal(v) {
    if (v == null) return "—";
    const n = Math.floor(v);
    const s = (n % 100 >= 11 && n % 100 <= 13) ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th");
    return n + s;
  }
  /* "AUD buys 13.5% more JPY than its 5-year average" */
  function buysVs(base, quote, pct, reference) {
    if (pct == null) return "";
    if (Math.abs(pct) < 0.05) return base + " buys about the same " + quote + " as its " + reference;
    return base + " buys " + fmt1.format(Math.abs(pct)) + "% " + (pct > 0 ? "more " : "less ") + quote + " than its " + reference;
  }
  /* Period wording comes from the API (period.average, period.heading, …) because
     MAX is described by its actual start date. These only adjust case. */
  function cap(s) { return s ? s[0].toUpperCase() + s.slice(1) : s; }
  function lowerFirst(s) { return s ? s[0].toLowerCase() + s.slice(1) : s; }
  /* For loading messages, before the window is known: "past 5 years" / "full history" */
  function loadingSpan(p) { return p && p.years ? p.label.toLowerCase() : "full history"; }
  function direction(v) { return v == null || Math.abs(v) < 0.05 ? "" : (v > 0 ? "up" : "down"); }

  /* Dates are always day-month-year with fixed English month names ("7 Oct 2026"),
     matching the sentences the server writes, whatever the browser's locale. */
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  function date(iso) {
    if (!iso) return "—";
    const [y, m, d] = iso.split("-").map(Number);
    return d + " " + MONTHS[m - 1] + " " + y;
  }
  function month(isoOrYm) {
    if (!isoOrYm) return "—";
    const [y, m] = isoOrYm.split("-").map(Number);
    return MONTHS_LONG[m - 1] + " " + y;
  }
  /* "2026-M06" / "2026-Q2" → "Jun 2026" / "Q2 2026" */
  function cpiPeriod(label) {
    const m = /^(\d{4})-M(\d{2})$/.exec(label || "");
    if (m) return MONTHS[+m[2] - 1] + " " + m[1];
    const q = /^(\d{4})-Q([1-4])$/.exec(label || "");
    return q ? "Q" + q[2] + " " + q[1] : (label || "—");
  }

  /* ---- DOM: build nodes with textContent only, never innerHTML with data ---- */
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k === "style") node.setAttribute("style", v);
        else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    }
    return node;
  }

  /* Percentile band ("Exceptionally strong"): green when your money buys more than usual,
     red when less, grey when typical. The label always accompanies the colour. */
  const BAND_CLASS = { exceptionally_strong: "up", strong: "up", typical: "muted", weak: "down", exceptionally_weak: "down" };
  function band(b, extraClass) {
    if (!b) return null;
    return el("span", { class: "band " + BAND_CLASS[b.key] + (extraClass ? " " + extraClass : "") }, b.label);
  }

  function notice(kind, title, items) {
    return el("div", { class: "notice " + kind, role: kind === "error" ? "alert" : "status" },
      title ? el("strong", null, title) : null,
      items && items.length ? el("ul", null, items.map(t => el("li", null, t))) : null);
  }

  window.Q = {
    fetchJSON, readSelection, writeSelection, selectionQuery, syncNav, buildControls, setControls,
    MONTHS,
    fmt: { rate, money, signedPct, signedPts, pct, score, ordinal, direction, date, month, cpiPeriod, buysVs, cap, lowerFirst, loadingSpan },
    el, notice, band,
  };
})();
