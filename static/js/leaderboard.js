/* Travel Value Leaderboard page. */
(function () {
  "use strict";
  const { el, fmt } = Q;
  const $ = id => document.getElementById(id);
  const SVG = "http://www.w3.org/2000/svg";

  let sel, options, requestId = 0;

  function countryHref(entry) {
    return "/country/" + encodeURIComponent(entry.destination.id) + "?" + Q.selectionQuery(sel);
  }

  function delta(value) {
    return el("span", { class: fmt.direction(value) }, fmt.signedPct(value));
  }

  function bar(score) {
    const w = Math.max(0, Math.min(100, score || 0));
    return el("span", { class: "bar", "aria-hidden": "true" }, el("i", { style: "width:" + w + "%" }));
  }

  /* Period sparkline: neutral line, hairline at the period average, square marker for today. */
  function sparkline(values, average) {
    const w = 104, h = 26, pad = 3;
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "spark");
    svg.setAttribute("width", w);
    svg.setAttribute("height", h);
    svg.setAttribute("aria-hidden", "true");
    if (!values || values.length < 2) return svg;
    const lo = Math.min(...values, average), hi = Math.max(...values, average);
    const x = i => (i / (values.length - 1)) * (w - pad * 2) + pad;
    const y = v => h - pad - ((v - lo) / (hi - lo || 1)) * (h - pad * 2);
    const add = (tag, attrs) => {
      const n = document.createElementNS(SVG, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
      svg.appendChild(n);
    };
    add("line", { x1: pad, x2: w - pad, y1: y(average), y2: y(average), stroke: "var(--hairline)", "stroke-width": 1, "shape-rendering": "crispEdges" });
    add("path", { d: values.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join(""), fill: "none", stroke: "var(--spark)", "stroke-width": 1.25 });
    const lx = x(values.length - 1), ly = y(values[values.length - 1]);
    add("rect", { x: lx - 2.5, y: ly - 2.5, width: 5, height: 5, fill: "var(--accent)" });
    return svg;
  }

  function noteMarks(entry, notes) {
    const marks = (entry.data_quality ? entry.data_quality.warnings : []).map(w => {
      if (!notes.has(w)) notes.set(w, notes.size + 1);
      return notes.get(w);
    });
    if (!marks.length) return null;
    return el("span", { class: "note-mark", title: entry.data_quality.warnings.join(" ") }, marks.join(","));
  }

  function subline(entry) {
    const d = entry.destination;
    const rate = entry.current_rate != null ? "1 " + sel.base + " = " + fmt.rate(entry.current_rate) + " " + d.currency_code : d.currency_code;
    const n = entry.shares_currency_with.length;
    return n ? rate + " · shared with " + n + " other destination" + (n > 1 ? "s" : "") : rate;
  }

  function tableRow(entry, notes, pw) {
    const d = entry.destination;
    const ranked = entry.status === "ranked";
    const dest = el("td", { class: "left" },
      el("div", { class: "dest" },
        el("span", { class: "flag", "aria-hidden": "true" }, d.flag),
        el("div", { class: "dest-text" },
          el("a", { class: "dest-name", href: countryHref(entry) }, d.display_name), noteMarks(entry, notes),
          el("div", { class: "dest-sub", title: entry.shares_currency_with.length ? "Same currency as " + entry.shares_currency_with.join(", ") : null }, subline(entry)),
          ranked ? null : el("div", { class: "dest-reason" }, entry.unavailable_reason))));
    return el("tr", { class: "row-link" + (ranked ? "" : " unavailable"), "data-href": countryHref(entry) },
      el("td", { class: "left rank" }, ranked ? String(entry.rank) : "–"),
      dest,
      el("td", null, ranked
        ? el("div", { class: "score-cell" }, bar(entry.quantile_score), el("span", { class: "score-num" }, fmt.score(entry.quantile_score)))
        : "Not ranked"),
      el("td", null, sparkline(entry.sparkline, entry.historical_average)),
      el("td", null, fmt.ordinal(entry.fx_percentile)),
      el("td", { title: fmt.buysVs(sel.base, d.currency_code, entry.vs_historical_average_pct, pw + " average") }, delta(entry.vs_historical_average_pct)),
      el("td", { title: ranked ? fmt.buysVs(sel.base, d.currency_code, entry.real_purchasing_power_pct, pw + " average") + ", after inflation" : null },
        ranked ? delta(entry.real_purchasing_power_pct) : "—"));
  }

  function card(entry) {
    const d = entry.destination;
    const ranked = entry.status === "ranked";
    return el("li", null,
      el("a", { href: countryHref(entry) },
        el("span", { class: "rank" }, ranked ? String(entry.rank) : "–"),
        el("span", { class: "dest" },
          el("span", { class: "flag", "aria-hidden": "true" }, d.flag),
          el("span", { class: "dest-text" }, el("span", { class: "dest-name" }, d.display_name),
            el("div", { class: "dest-sub" }, subline(entry)))),
        el("span", { class: "score-num num" }, ranked ? fmt.score(entry.quantile_score) : "—"),
        ranked
          ? el("span", { class: "card-metrics" },
              el("span", null, "Real ", el("b", { class: fmt.direction(entry.real_purchasing_power_pct) }, fmt.signedPct(entry.real_purchasing_power_pct))),
              el("span", null, "vs avg ", el("b", { class: fmt.direction(entry.vs_historical_average_pct) }, fmt.signedPct(entry.vs_historical_average_pct))),
              el("span", null, el("b", null, fmt.ordinal(entry.fx_percentile)), " percentile"))
          : el("span", { class: "card-metrics" }, entry.unavailable_reason)));
  }

  function render(data) {
    const notes = new Map();
    const pw = fmt.periodWord(data.period);
    $("board-rows").replaceChildren(...data.entries.map(e => tableRow(e, notes, pw)));
    $("board-cards").replaceChildren(...data.entries.map(card));
    $("spark-head").textContent = data.period.label;

    $("board-notes").replaceChildren(notes.size
      ? el("ol", { style: "margin:0;padding-left:18px" }, [...notes.keys()].map(t => el("li", null, t)))
      : "");

    const unranked = data.entries.length - data.ranked_count;
    $("board-meta").replaceChildren(
      el("span", null, el("strong", null, data.ranked_count + " destinations"),
        " ranked for " + data.base.code + (unranked ? " · " + unranked + " can't be ranked right now" : "")),
      el("span", null, "Rates as of " + fmt.date(data.window_end) + " · compared with " + fmt.date(data.window_start) + " onwards"));

    $("board-alert").replaceChildren(data.warnings.length
      ? el("div", { class: "alert", role: "status" }, el("strong", null, "Some exchange-rate data is out of date"),
          el("ul", null, data.warnings.map(w => el("li", null, w))))
      : "");

    $("board-state").hidden = true;
    $("board-body").hidden = false;
    $("board-body").classList.remove("is-refreshing");
  }

  function showLoading() {
    const period = options.periods.find(p => p.key === sel.period);
    $("board-state-title").textContent = "Loading " + period.label.toLowerCase() + " of " + sel.base + " exchange rates…";
    $("board-state-detail").textContent = "The first load fetches daily history from central-bank sources and takes about 20 seconds.";
    $("board-state").querySelector(".progress").hidden = false;
    for (const b of $("board-state").querySelectorAll(".actions")) b.remove();
    $("board-state").hidden = false;
  }

  function showError(err) {
    $("board-body").hidden = true;
    const state = $("board-state");
    state.hidden = false;
    $("board-state-title").textContent = "Rankings unavailable";
    $("board-state-detail").textContent = err.message;
    state.querySelector(".progress").hidden = true;
    for (const b of state.querySelectorAll(".actions")) b.remove();
    state.appendChild(el("div", { class: "actions" }, el("button", { class: "button secondary", type: "button", onclick: () => load() }, "Retry")));
  }

  async function load() {
    const id = ++requestId;
    $("board-meta").replaceChildren();
    if ($("board-body").hidden) showLoading();
    else $("board-body").classList.add("is-refreshing"); // keep the current ranking visible while refetching
    try {
      const data = await Q.fetchJSON("/api/leaderboard?" + Q.selectionQuery(sel));
      if (id === requestId) render(data);
    } catch (e) {
      if (id === requestId) showError(e);
    }
  }

  $("board-rows").addEventListener("click", ev => {
    if (ev.target.closest("a")) return;
    const row = ev.target.closest("tr[data-href]");
    if (row) location.href = row.dataset.href;
  });

  window.addEventListener("popstate", () => {
    sel = Q.readSelection(sel);
    Q.setControls(sel);
    Q.syncNav(sel);
    load();
  });

  (async function init() {
    try {
      options = await Q.fetchJSON("/api/options");
    } catch (e) {
      sel = { base: "AUD", period: "5y" };
      options = { periods: [{ key: "5y", label: "Past 5 years" }] };
      showError(e);
      return;
    }
    sel = Q.readSelection({ base: options.default_base, period: options.default_period });
    Q.buildControls(options, sel, next => { Q.writeSelection(next); load(); });
    Q.writeSelection(sel, true);
    load();
  })();
})();
