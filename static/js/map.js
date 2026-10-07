/* World Map: the leaderboard's Quantile Scores drawn as a choropleth.

   Data comes from the same /api/leaderboard response the Leaderboard uses, so
   scores are identical by construction. Countries are matched to geometry by
   ISO 3166-1 numeric id (world-atlas / Natural Earth), never by name. */
(function () {
  "use strict";
  const { el, fmt } = Q;
  const $ = id => document.getElementById(id);
  const SVG = "http://www.w3.org/2000/svg";
  const WIDTH = 960;
  const ANTARCTICA = "010";

  /* One-hue sequential scale (Quantile blue). Light mode runs light → dark;
     on dark surfaces the same hue runs dark → light, so "more favourable"
     always means "more contrast against the page". */
  const RAMP_LIGHT = ["#b7d3f6", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281", "#0d366b"];
  const RAMP_DARK = ["#184f95", "#1c5cab", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"];

  function isDark() {
    const theme = document.documentElement.dataset.theme;
    if (theme) return theme === "dark";
    return matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function ramp() { return isDark() ? RAMP_DARK : RAMP_LIGHT; }
  function rgb(hex) { const n = parseInt(hex.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }

  /* Continuous: 81 and 97 get different colours. Piecewise-linear between ramp steps. */
  function scoreColor(score) {
    const stops = ramp();
    const t = Math.max(0, Math.min(100, score)) / 100 * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(t));
    const a = rgb(stops[i]), b = rgb(stops[i + 1]), f = t - i;
    return "rgb(" + a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",") + ")";
  }

  // ---- state ----
  let sel, options, destinations = [], lastData = null, requestId = 0;
  let pathGen, projection, svg, gCountries, gSupported, gMarkers, highlight;
  const shapes = new Map();   // iso numeric → <path>
  const markers = new Map();  // iso numeric → { mark, hit }
  let pinnedId = null, lastPointerType = "mouse";

  function svgEl(tag, attrs) {
    const n = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  }

  // ---- geometry ----
  function buildMap(topology) {
    const features = topojson.feature(topology, topology.objects.countries).features.filter(f => f.id !== ANTARCTICA);
    const collection = { type: "FeatureCollection", features };
    projection = d3.geoEqualEarth().fitWidth(WIDTH, collection);
    pathGen = d3.geoPath(projection);
    const height = Math.ceil(pathGen.bounds(collection)[1][1]) + 1;

    svg = svgEl("svg", { viewBox: `0 0 ${WIDTH} ${height}`, "aria-hidden": "false" });
    gCountries = svgEl("g");
    gSupported = svgEl("g"); // supported destinations, in rank order (sets keyboard order)
    highlight = svgEl("path", { class: "highlight" });
    gMarkers = svgEl("g");
    for (const f of features) {
      const p = svgEl("path", { class: "country", d: pathGen(f) });
      p.__feature = f;
      p.__name = f.properties.name;
      if (f.id) {
        p.dataset.id = f.id;
        shapes.set(f.id, p);
      }
      gCountries.appendChild(p);
    }
    svg.append(gCountries, gSupported, highlight, gMarkers);
    $("map").replaceChildren(svg);
  }

  function buildMarkers() {
    for (const d of destinations) {
      if (!d.map_point || shapes.has(d.iso_numeric)) continue;
      const [x, y] = projection(d.map_point);
      const mark = svgEl("rect", { class: "marker", x: x - 3.5, y: y - 3.5, width: 7, height: 7 });
      const hit = svgEl("circle", { class: "marker-hit", cx: x, cy: y, r: 11 });
      mark.dataset.id = hit.dataset.id = d.iso_numeric;
      hit.__name = d.country;
      hit.__point = [x, y];
      gMarkers.append(mark, hit);
      markers.set(d.iso_numeric, { mark, hit });
    }
  }

  // ---- data → map ----
  const byId = { entries: new Map(), destinations: new Map() };

  function describe(id, fallbackName) {
    const entry = byId.entries.get(id);
    const dest = entry ? entry.destination : byId.destinations.get(id);
    if (!dest) return { kind: "none", name: fallbackName || "This country" };
    const href = "/country/" + encodeURIComponent(dest.id) + "?" + Q.selectionQuery(sel);
    if (dest.currency_code === sel.base && !entry) return { kind: "home", dest, name: dest.display_name };
    if (!entry) return { kind: "none", name: dest.display_name };
    return { kind: entry.status === "ranked" ? "ranked" : "unranked", dest, entry, href, name: dest.display_name };
  }

  function interactive(node, label) {
    node.setAttribute("tabindex", "0");
    node.setAttribute("role", "link");
    node.setAttribute("aria-label", label);
    node.classList.add("scored");
  }
  function inert(node) {
    node.removeAttribute("tabindex");
    node.removeAttribute("role");
    node.removeAttribute("aria-label");
    node.classList.remove("scored", "home");
    node.style.fill = "";
  }

  function paint(data) {
    lastData = data;
    byId.entries = new Map(data ? data.entries.map(e => [e.destination.iso_numeric, e]) : []);
    while (gSupported.firstChild) gCountries.appendChild(gSupported.firstChild);
    for (const p of shapes.values()) inert(p);
    for (const { mark, hit } of markers.values()) { inert(hit); mark.style.fill = "var(--map-none)"; }

    const avg = data ? data.period.average : "";
    const ordered = data ? data.entries : [];
    for (const d of destinations) {
      if (d.currency_code === sel.base && !byId.entries.has(d.iso_numeric)) {
        const shape = shapes.get(d.iso_numeric);
        if (shape) shape.classList.add("home");
        const m = markers.get(d.iso_numeric);
        if (m) m.mark.style.fill = "var(--map-home)";
      }
    }
    for (const e of ordered) {
      const id = e.destination.iso_numeric;
      const ranked = e.status === "ranked";
      const label = ranked
        ? e.destination.display_name + ": Quantile Score " + fmt.score(e.quantile_score) + " of 100, rank " + e.rank + " of " + data.ranked_count +
          ". " + fmt.buysVs(sel.base, e.destination.currency_code, e.vs_historical_average_pct, avg) + "."
        : e.destination.display_name + ": not ranked. " + e.unavailable_reason;
      const color = ranked ? scoreColor(e.quantile_score) : "";
      const shape = shapes.get(id);
      if (shape) {
        gSupported.appendChild(shape);
        shape.style.fill = color;
        interactive(shape, label);
      }
      const m = markers.get(id);
      if (m) {
        m.mark.style.fill = color || "var(--map-none)";
        interactive(m.hit, label);
      }
    }
    $("legend-bar").style.background = "linear-gradient(to right, " + ramp().join(", ") + ")";
  }

  // ---- tooltip ----
  function tipRow(label, value, cls) {
    return el("div", { class: "tip-row" }, el("span", null, label), el("b", { class: cls || null }, value));
  }

  function tipContent(info) {
    const head = (name, ccy, right) => el("div", { class: "tip-head" },
      el("span", { class: "t-label", style: "color:var(--ink)" }, ccy ? name + " · " + ccy : name),
      right ? el("span", { class: "small muted num" }, right) : null);
    if (info.kind === "none") return [head(info.name), el("p", null, "Quantile data not currently available.")];
    if (info.kind === "home") return [head(info.name, info.dest.currency_code), el("p", null, "Uses " + info.dest.currency_code + ", your home currency.")];
    const e = info.entry, ccy = info.dest.currency_code;
    const link = el("a", { class: "tip-link", href: info.href }, "View " + info.name + " →");
    if (info.kind === "unranked") return [head(info.name, ccy), el("p", null, "Not ranked: " + e.unavailable_reason), link];
    const p = lastData.period;
    return [
      head(info.name, ccy, "Rank " + e.rank + " of " + lastData.ranked_count),
      el("div", { class: "tip-score" }, el("span", { class: "t-figure" }, fmt.score(e.quantile_score)), el("span", { class: "small muted" }, "/ 100")),
      el("div", { class: "tip-rows" },
        tipRow("FX percentile", fmt.ordinal(e.fx_percentile)),
        tipRow("vs " + p.average_short, fmt.signedPct(e.vs_historical_average_pct), fmt.direction(e.vs_historical_average_pct)),
        tipRow("Real purchasing power", fmt.signedPct(e.real_purchasing_power_pct), fmt.direction(e.real_purchasing_power_pct))),
      link,
    ];
  }

  function showTip(id, name, clientX, clientY, pinned) {
    const info = describe(id, name);
    const tip = $("map-tip");
    tip.replaceChildren(...tipContent(info));
    tip.classList.toggle("pinned", !!pinned);
    tip.hidden = false;
    const frame = $("map-frame").getBoundingClientRect();
    let x = clientX - frame.left + 16, y = clientY - frame.top + 16;
    if (x + tip.offsetWidth > frame.width) x = clientX - frame.left - tip.offsetWidth - 16;
    if (y + tip.offsetHeight > frame.height) y = clientY - frame.top - tip.offsetHeight - 16;
    tip.style.left = Math.max(0, x) + "px";
    tip.style.top = Math.max(0, y) + "px";

    const shape = shapes.get(id);
    highlight.setAttribute("d", info.entry && shape ? shape.getAttribute("d") : "");
    for (const { mark } of markers.values()) mark.style.stroke = "";
    if (info.entry && markers.has(id)) markers.get(id).mark.style.stroke = "var(--ink)";
    return info;
  }

  function hideTip() {
    $("map-tip").hidden = true;
    highlight.setAttribute("d", "");
    for (const { mark } of markers.values()) mark.style.stroke = "";
    pinnedId = null;
  }

  function targetOf(ev) {
    const node = ev.target.closest("[data-id]");
    if (node) return { id: node.dataset.id, name: node.__name, node };
    const any = ev.target.closest(".country");
    return any ? { id: null, name: any.__name, node: any } : null;
  }

  function screenPoint(node) {
    const box = svg.getBoundingClientRect();
    const scale = box.width / WIDTH;
    const [cx, cy] = node.__point || pathGen.centroid(node.__feature);
    return [box.left + cx * scale, box.top + cy * scale];
  }

  function wireInteraction() {
    svg.addEventListener("pointerdown", ev => { lastPointerType = ev.pointerType || "mouse"; });
    svg.addEventListener("pointermove", ev => {
      if (ev.pointerType === "touch" || pinnedId) return;
      const t = targetOf(ev);
      if (!t) return hideTip();
      showTip(t.id, t.name, ev.clientX, ev.clientY, false);
    });
    svg.addEventListener("pointerleave", () => { if (!pinnedId) hideTip(); });
    svg.addEventListener("click", ev => {
      const t = targetOf(ev);
      if (!t) return hideTip();
      const info = describe(t.id, t.name);
      if (lastPointerType === "touch" || lastPointerType === "pen") {
        // First tap reveals the numbers; tapping the same country again (or "View") opens it.
        if (pinnedId === (t.id || t.name) && info.href) { location.href = info.href; return; }
        showTip(t.id, t.name, ev.clientX, ev.clientY, true);
        pinnedId = t.id || t.name;
        return;
      }
      if (info.href) location.href = info.href;
    });
    svg.addEventListener("focusin", ev => {
      const node = ev.target.closest("[data-id]");
      if (!node) return;
      const [x, y] = screenPoint(node);
      showTip(node.dataset.id, node.__name, x, y, false);
    });
    svg.addEventListener("focusout", () => hideTip());
    svg.addEventListener("keydown", ev => {
      const node = ev.target.closest("[data-id]");
      if (!node) return;
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        const info = describe(node.dataset.id, node.__name);
        if (info.href) location.href = info.href;
      } else if (ev.key === "Escape") {
        hideTip();
      }
    });
    document.addEventListener("click", ev => { if (pinnedId && !ev.target.closest("#map-frame")) hideTip(); });
  }

  // ---- surrounding UI ----
  function setStatus(title, detail, { progress = false, actions = null } = {}) {
    $("map-status").hidden = false;
    $("map-status-title").textContent = title;
    $("map-status-detail").textContent = detail || "";
    $("map-status-detail").hidden = !detail;
    $("map-status-progress").hidden = !progress;
    $("map-status-actions").hidden = !actions;
    $("map-status-actions").replaceChildren(...(actions || []));
  }

  function renderMeta(data) {
    const unranked = data.entries.length - data.ranked_count;
    $("map-meta").replaceChildren(
      el("span", null, el("strong", null, data.ranked_count + " destinations"), " scored for " + data.base.code +
        (unranked ? " · " + unranked + " can't be scored right now" : "")),
      el("span", null, "Exchange rates through " + fmt.date(data.window_end) + " · compared with " + fmt.date(data.window_start) + " onwards"));
  }

  function renderTop(data) {
    const top = data.entries.filter(e => e.status === "ranked").slice(0, 5);
    $("top-section").hidden = !top.length;
    $("top-sub").textContent = "Highest scores for " + data.base.code + ", " + fmt.lowerFirst(data.period.heading);
    $("top-list").replaceChildren(...top.map(e => el("li", null,
      el("a", { href: "/country/" + encodeURIComponent(e.destination.id) + "?" + Q.selectionQuery(sel) },
        el("span", { class: "top-rank" }, String(e.rank).padStart(2, "0")),
        el("span", { class: "top-name" }, e.destination.display_name),
        el("span", { class: "top-score" }, fmt.score(e.quantile_score))))));
  }

  function syncLinks() {
    $("view-leaderboard").href = "/?" + Q.selectionQuery(sel);
  }

  async function load() {
    const id = ++requestId;
    hideTip();
    syncLinks();
    if (lastData) {
      $("map").classList.add("is-refreshing");
      setStatus("Updating for " + sel.base + " · " + sel.period.toUpperCase() + "…", null, { progress: true });
    } else {
      setStatus("Calculating global travel value…", "The first load fetches up to 10 years of daily rates and can take about 20 seconds.", { progress: true });
    }
    try {
      const data = await Q.fetchJSON("/api/leaderboard?" + Q.selectionQuery(sel));
      if (id !== requestId) return;
      paint(data);
      renderMeta(data);
      renderTop(data);
      $("map").classList.remove("is-refreshing");
      $("map-status").hidden = true;
    } catch (err) {
      if (id !== requestId) return;
      paint(null); // never leave stale or placeholder scores on screen
      $("map").classList.remove("is-refreshing");
      $("map-meta").replaceChildren();
      $("top-section").hidden = true;
      setStatus("Unable to load Quantile scores right now.", err.message,
        { actions: [el("button", { class: "button secondary", type: "button", onclick: () => load() }, "Try again")] });
    }
  }

  window.addEventListener("popstate", () => { sel = Q.readSelection(sel); Q.setControls(sel); Q.syncNav(sel); load(); });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (svg) paint(lastData); });

  (async function init() {
    let topology;
    try {
      [options, destinations, topology] = await Promise.all([
        Q.fetchJSON("/api/options"),
        Q.fetchJSON("/api/destinations"),
        Q.fetchJSON(window.QUANTILE_GEOMETRY),
      ]);
    } catch (err) {
      setStatus("Unable to load the world map right now.", err.message,
        { actions: [el("button", { class: "button secondary", type: "button", onclick: () => location.reload() }, "Try again")] });
      return;
    }
    destinations = destinations.filter(d => d.enabled);
    byId.destinations = new Map(destinations.map(d => [d.iso_numeric, d]));
    buildMap(topology);
    buildMarkers();
    wireInteraction();

    sel = Q.readSelection({ base: options.default_base, period: options.default_period });
    Q.buildControls(options, sel, next => { Q.writeSelection(next); load(); });
    Q.writeSelection(sel, true);
    paint(null);
    load();
  })();
})();
