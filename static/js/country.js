/* Country detail page. */
(function () {
  "use strict";
  const { el, fmt } = Q;
  const slug = window.QUANTILE_DESTINATION.id;
  const quoteCode = window.QUANTILE_DESTINATION.currency;
  const $ = id => document.getElementById(id);

  let sel, options, chart = null, lastData = null, requestId = 0;

  function signed(v) { return el("span", { class: fmt.direction(v) }, fmt.signedPct(v)); }

  /* "Goes 15.8% further than the inflation-adjusted average" */
  function goesFurther(pct, reference) {
    if (Math.abs(pct) < 0.05) return "Goes about as far as the " + reference;
    return "Goes " + Math.abs(pct).toFixed(1) + "% " + (pct > 0 ? "further" : "less far") + " than the " + reference;
  }

  function figure(label, value, unit, note, cls) {
    return el("div", { class: "figure" },
      el("div", { class: "t-label" }, label),
      el("div", { class: "t-figure" + (cls ? " " + cls : "") }, value, unit ? el("span", { class: "unit" }, unit) : null),
      note ? el("div", { class: "t-small" }, note) : null);
  }

  function statRow(label, value, extra) {
    return el("tr", null, el("th", { scope: "row" }, label),
      el("td", null, value, extra ? el("span", { class: "muted" }, " " + extra) : null));
  }
  function groupRow(label) {
    return el("tr", { class: "group" }, el("th", { colspan: "2", scope: "rowgroup" }, el("span", { class: "t-label" }, label)));
  }

  function render(d) {
    lastData = d;
    const base = d.base.code, quote = d.destination.currency_code;
    const pw = fmt.periodWord(d.period);

    $("shared-note").textContent = d.shares_currency_with.length
      ? " · same currency as " + d.shares_currency_with.join(", ") + " (identical exchange-rate figures; inflation differs)"
      : "";

    if (d.score) {
      $("score-block").hidden = false;
      $("score-value").textContent = fmt.score(d.score.quantile_score);
      $("score-rank").textContent = "Rank " + d.rank + " of " + d.ranked_count + " for " + base;
    } else {
      $("score-block").hidden = true;
    }

    $("headline").textContent = d.headline || "";
    $("explanation").textContent = d.explanation || "";

    const alerts = [];
    if (d.status !== "ranked") alerts.push(el("div", { class: "alert note" }, el("strong", null, "Not ranked. "), d.unavailable_reason));
    if (d.data_quality && d.data_quality.warnings.length) {
      alerts.push(el("div", { class: "alert note" }, el("strong", null, "Data note"),
        el("ul", null, d.data_quality.warnings.map(w => el("li", null, w)))));
    }
    $("country-alert").replaceChildren(...alerts);

    if (!d.fx) {
      for (const id of ["figures", "stats", "bridge", "inflation-table", "components", "chart"]) $(id).replaceChildren();
      showBody();
      renderFacts(d);
      return;
    }
    const fx = d.fx, inf = d.inflation;

    $("figures").replaceChildren(
      figure("1 " + base + " buys", fmt.rate(fx.current_rate), quote, "Reference rate, " + fmt.date(fx.current_date)),
      figure(pw + " average", fmt.rate(fx.average), quote, fmt.buysVs(base, quote, fx.vs_average_pct, pw + " average")),
      figure("FX percentile", fmt.ordinal(fx.percentile), null, fx.share_equal_pct >= 50
        ? "Unchanged on " + Math.floor(fx.share_equal_pct) + "% of " + fx.observations.toLocaleString() + " trading days"
        : "Better than " + Math.floor(fx.share_below_pct) + "% of " + fx.observations.toLocaleString() + " trading days"),
      inf
        ? figure("After inflation", fmt.signedPct(inf.real_vs_average_pct), null,
            goesFurther(inf.real_vs_average_pct, "inflation-adjusted " + pw + " average"), fmt.direction(inf.real_vs_average_pct))
        : figure("After inflation", "—", null, "No inflation data for this period"));

    $("chart-title").textContent = base + "/" + quote + ", " + d.period.label.toLowerCase();
    $("chart-note").textContent = quote + " per 1 " + base + " · higher is better for you";
    $("chart-count").textContent = d.chart.downsampled
      ? "Showing " + d.chart.points.length + " of " + d.chart.total_observations.toLocaleString() + " daily rates; all are used in the calculations"
      : d.chart.total_observations.toLocaleString() + " daily rates";
    $("show-real").disabled = !inf;
    renderChart();
    renderChartTable(d);

    $("stats-sub").textContent = fmt.date(fx.first_date) + " – " + fmt.date(fx.current_date) + " · " + fx.observations.toLocaleString() + " weekdays";
    const rows = [
      groupRow(quote + " per " + base),
      statRow("Today", fmt.rate(fx.current_rate)),
      statRow(pw[0].toUpperCase() + pw.slice(1) + " average", fmt.rate(fx.average)),
      statRow("Median", fmt.rate(fx.median)),
      statRow("High", fmt.rate(fx.high), fmt.date(fx.high_date)),
      statRow("Low", fmt.rate(fx.low), fmt.date(fx.low_date)),
      statRow("FX percentile", fmt.ordinal(fx.percentile)),
      statRow("Today vs average", signed(fx.vs_average_pct)),
      statRow("Today vs median", signed(fx.vs_median_pct)),
      statRow("Change over 1 year", fx.one_year_change_pct == null ? "—" : signed(fx.one_year_change_pct)),
      statRow("Volatility, annualised", fx.volatility_pct == null ? "—" : fmt.pct(fx.volatility_pct)),
    ];
    if (inf) {
      rows.push(
        groupRow("After inflation"),
        statRow(inf.home.country + " inflation", fmt.signedPct(inf.home.cumulative_pct)),
        statRow(inf.destination.country + " inflation", fmt.signedPct(inf.destination.cumulative_pct)),
        statRow("Inflation adjustment", el("span", { class: fmt.direction(inf.inflation_adjustment_pts) }, fmt.signedPts(inf.inflation_adjustment_pts))),
        statRow("Real purchasing-power change", signed(inf.real_vs_average_pct)),
        statRow("Inflation-adjusted percentile", fmt.ordinal(inf.real_percentile)));
    }
    $("stats").replaceChildren(...rows);

    renderInflation(d);
    renderScore(d);
    renderFacts(d);
    showBody();
  }

  function renderChart() {
    const d = lastData;
    if (!d || !d.chart) return;
    const showReal = $("show-real").checked && !!d.inflation;
    const pw = fmt.periodWord(d.period);
    const legend = [el("span", null, el("i", { class: "key-line", style: "background:var(--series-1)" }), "Exchange rate")];
    if (showReal) legend.push(el("span", null, el("i", { class: "key-line", style: "background:var(--series-2)" }), "Past rates in today's prices"));
    legend.push(el("span", null, el("i", { class: "key-line", style: "background:var(--reference)" }), pw + " average"));
    if (showReal) legend.push(el("span", null, el("i", { class: "key-line", style: "background:var(--series-2);height:1px" }), "Inflation-adjusted average"));
    legend.push(el("span", null, el("i", { class: "key-square" }), "Today"));
    $("chart-legend").replaceChildren(...legend);

    const opts = {
      points: d.chart.points,
      average: d.chart.average,
      realAverage: d.chart.real_average,
      showReal,
      formatValue: fmt.rate,
      formatDate: fmt.date,
      ariaLabel: "Line chart of " + d.fx.pair + ", " + d.period.label.toLowerCase() + ". " + (d.headline || ""),
      labels: { rate: "Rate", real: "In today's prices", average: pw + " avg", realAverage: "Adjusted avg", today: "Today", vsAverage: "vs " + pw + " avg" },
    };
    if (chart) chart.update(opts);
    else chart = QChart.mount($("chart"), opts);
  }

  function renderChartTable(d) {
    const hasReal = d.chart.points.some(p => p.real_rate != null);
    const head = el("thead", null, el("tr", null, el("th", null, "Date"), el("th", null, "Rate"), hasReal ? el("th", null, "In today's prices") : null));
    const body = el("tbody", null, d.chart.points.slice().reverse().map(p =>
      el("tr", null, el("td", null, fmt.date(p.date)), el("td", null, fmt.rate(p.rate)), hasReal ? el("td", null, fmt.rate(p.real_rate)) : null)));
    $("chart-table").replaceChildren(head, body);
  }

  function renderInflation(d) {
    const section = $("inflation-section");
    if (!d.inflation) { section.hidden = true; return; }
    section.hidden = false;
    const inf = d.inflation, pw = fmt.periodWord(d.period);
    $("infl-sub").textContent = "CPI to " + fmt.month(inf.cpi_cutoff.slice(0, 7));
    $("bridge").replaceChildren(
      el("div", { class: "bridge-row" }, el("span", null, "Currency advantage vs " + pw + " average"), signed(inf.nominal_vs_average_pct)),
      el("div", { class: "bridge-row" }, el("span", null, "Relative inflation adjustment"),
        el("span", { class: fmt.direction(inf.inflation_adjustment_pts) }, fmt.signedPts(inf.inflation_adjustment_pts))),
      el("div", { class: "bridge-row total" }, el("span", null, "Real advantage"), signed(inf.real_vs_average_pct)));

    const row = c => el("tr", null,
      el("th", { scope: "row" }, c.country,
        el("div", { class: "muted small" }, c.index_type + ", " + c.frequency + " · " + fmt.cpiPeriod(c.start_period) + " – " + fmt.cpiPeriod(c.end_period))),
      el("td", null, fmt.signedPct(c.cumulative_pct), el("span", { class: "muted" }, " · " + fmt.signedPct(c.annualised_pct) + "/yr")));
    $("inflation-table").replaceChildren(
      groupRow("Price-level change"),
      row(inf.home), row(inf.destination),
      statRow("Relative inflation factor", inf.relative_inflation_factor.toFixed(3), "destination ÷ home"));

    const faster = inf.destination.cumulative_pct > inf.home.cumulative_pct;
    const pts = Math.abs(inf.inflation_adjustment_pts).toFixed(1) + " points";
    $("inflation-note").textContent =
      "Prices rose " + (faster ? "faster" : "more slowly") + " in " + inf.destination.country + " than in " + inf.home.country +
      ", so inflation " + (inf.inflation_adjustment_pts < 0 ? "takes " + pts + " off" : "adds " + pts + " to") +
      " the currency advantage. Because today is compared with the whole period's average rather than its first day, " +
      "the adjustment differs from the cumulative inflation gap.";
  }

  function renderScore(d) {
    const section = $("score-section");
    if (!d.score) { section.hidden = true; return; }
    section.hidden = false;
    $("score-method").textContent = "50% rarity + 50% size of the inflation-adjusted advantage";
    const describe = c => c.key === "real_percentile"
      ? "Today's inflation-adjusted rate beats " + Math.floor(c.input_value) + "% of days in the period"
      : "Today is " + fmt.signedPct(c.input_value) + " vs the inflation-adjusted average (0% = 50 pts, +20% or more = 100)";
    $("components").replaceChildren(
      ...d.score.components.map(c => el("div", { class: "comp-row" },
        el("div", null, el("div", null, c.label), el("div", { class: "muted small" }, describe(c))),
        el("div", { class: "num", style: "text-align:right" },
          el("div", null, fmt.score(c.points) + " pts"),
          el("div", { class: "muted small" }, "× " + Math.round(c.weight * 100) + "% = " + c.contribution.toFixed(1))),
        el("span", { class: "bar", "aria-hidden": "true" }, el("i", { style: "width:" + Math.max(0, Math.min(100, c.points)) + "%" })))),
      el("div", { class: "comp-row comp-total" }, el("span", null, "Quantile Score"), el("span", { class: "num" }, d.score.quantile_score.toFixed(1))));
  }

  function renderFacts(d) {
    const dq = d.data_quality || {};
    const facts = [];
    const add = (k, v) => facts.push(el("dt", null, k), el("dd", null, v));
    for (const src of d.sources) add(src.used_for, el("a", { href: src.url, rel: "noopener" }, src.name));
    add("Latest rate", fmt.date(dq.fx_latest_date));
    add("Period", fmt.date(dq.fx_first_date) + " – " + fmt.date(dq.fx_latest_date));
    add("Observations", dq.fx_observations ? dq.fx_observations.toLocaleString() + " weekdays" : "—");
    add("Inflation data to", dq.inflation_latest_date ? fmt.month(dq.inflation_latest_date) : "—");
    if (dq.cpi_frequency_home) add("CPI frequency", d.base.country + " " + dq.cpi_frequency_home + ", " + d.destination.country + " " + dq.cpi_frequency_destination);
    add("Complete", dq.complete ? "Yes" : "No — see the data note above");
    $("data-facts").replaceChildren(...facts);
    $("assumptions").replaceChildren(...d.assumptions.map(a => el("li", null, a)));
  }

  function showBody() {
    $("country-state").hidden = true;
    $("country-body").hidden = false;
    $("country-body").classList.remove("is-refreshing");
    if (chart) renderChart(); // size may have changed while hidden
  }

  function showState(title, detail, loading, actions) {
    $("country-body").hidden = true;
    $("country-state").hidden = false;
    $("state-title").textContent = title;
    $("state-detail").textContent = detail;
    $("state-progress").hidden = !loading;
    $("state-actions").hidden = !actions;
    $("state-actions").replaceChildren(...(actions || []));
  }

  function showError(err) {
    const back = el("a", { class: "button secondary", href: "/?" + Q.selectionQuery(sel) }, "Back to leaderboard");
    $("score-block").hidden = true;
    if (err.status === 404) {
      // e.g. "Australia uses AUD, the same currency as your home currency." Retrying won't help.
      showState("Nothing to compare", err.message + " Choose a different home currency above.", false, [back]);
      return;
    }
    const retry = el("button", { class: "button", type: "button", onclick: () => load() }, "Retry");
    showState(sel.base + "/" + quoteCode + " analysis unavailable", err.message, false, [retry, back]);
  }

  async function load() {
    const id = ++requestId;
    if ($("country-body").hidden) {
      const period = options && options.periods ? options.periods.find(p => p.key === sel.period) : null;
      showState("Loading " + (period ? period.label.toLowerCase() + " of " : "") + sel.base + "/" + quoteCode + " history…",
        "The first load fetches daily history from central-bank sources and takes about 20 seconds.", true, null);
    } else {
      $("country-body").classList.add("is-refreshing");
    }
    try {
      const d = await Q.fetchJSON("/api/country/" + encodeURIComponent(slug) + "?" + Q.selectionQuery(sel));
      if (id === requestId) render(d);
    } catch (e) {
      if (id === requestId) showError(e);
    }
  }

  $("show-real").addEventListener("change", renderChart);
  window.addEventListener("popstate", () => { sel = Q.readSelection(sel); Q.setControls(sel); Q.syncNav(sel); load(); });

  (async function init() {
    try { options = await Q.fetchJSON("/api/options"); }
    catch (e) { sel = { base: "AUD", period: "5y" }; showError(e); return; }
    sel = Q.readSelection({ base: options.default_base, period: options.default_period });
    Q.buildControls(options, sel, next => { Q.writeSelection(next); load(); });
    Q.writeSelection(sel, true);
    load();
  })();
})();
