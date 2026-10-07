/* Minimal, dependency-free SVG line chart for exchange-rate history.

   One y-axis. A 2px line for the rate, a solid reference line for the
   period average (labelled directly), a ringed marker for today's rate,
   and a crosshair tooltip that follows the pointer (or arrow keys). */
(function () {
  "use strict";
  const SVG = "http://www.w3.org/2000/svg";

  function s(tag, attrs) {
    const n = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  }
  function text(x, y, str, attrs) {
    const t = s("text", Object.assign({ x, y }, attrs || {}));
    t.textContent = str;
    return t;
  }

  function niceTicks(min, max, count) {
    const span = max - min || Math.abs(max) || 1;
    const raw = span / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(st => span / st <= count) || 10 * mag;
    const ticks = [];
    for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) ticks.push(+v.toPrecision(12));
    return ticks;
  }

  function timeTicks(t0, t1, width) {
    const days = (t1 - t0) / 864e5;
    const maxTicks = Math.max(2, Math.floor(width / 90));
    const ticks = [];
    const d0 = new Date(t0);
    if (days > 500) {
      const yearsSpan = days / 365;
      const every = Math.max(1, Math.ceil(yearsSpan / maxTicks));
      for (let y = d0.getUTCFullYear() + 1; Date.UTC(y, 0, 1) <= t1; y++) {
        if ((y - d0.getUTCFullYear() - 1) % every === 0) ticks.push({ t: Date.UTC(y, 0, 1), label: String(y) });
      }
    } else {
      const months = Math.max(1, Math.ceil((days / 30.4) / maxTicks));
      const fmt = new Intl.DateTimeFormat(undefined, { month: "short", year: "2-digit", timeZone: "UTC" });
      let y = d0.getUTCFullYear(), m = d0.getUTCMonth() + 1;
      for (let i = 0; i < 60; i++, m++) {
        if (m > 11) { m = 0; y++; }
        const t = Date.UTC(y, m, 1);
        if (t > t1) break;
        if (i % months === 0) ticks.push({ t, label: fmt.format(new Date(t)) });
      }
    }
    return ticks;
  }

  /* opts: { points:[{date, rate, real_rate}], average, realAverage, showReal, averageLabel,
             formatValue, formatDate, labels:{rate, real, average, realAverage} } */
  function render(container, opts) {
    const fmtV = opts.formatValue, fmtD = opts.formatDate;
    const pts = opts.points.map(p => ({ t: Date.parse(p.date + "T00:00:00Z"), v: p.rate, r: p.real_rate, date: p.date }));
    const showReal = opts.showReal && pts.every(p => p.r != null);

    const width = container.clientWidth;
    const height = container.clientHeight;
    const narrow = width < 520;
    const pad = { top: 16, right: narrow ? 12 : 104, bottom: 28, left: 56 };
    const iw = width - pad.left - pad.right;
    const ih = height - pad.top - pad.bottom;

    const values = pts.map(p => p.v).concat([opts.average]);
    if (showReal) values.push(...pts.map(p => p.r), opts.realAverage);
    let lo = Math.min(...values), hi = Math.max(...values);
    const dataLo = lo, dataHi = hi;
    const padV = (hi - lo) * 0.08 || Math.abs(hi) * 0.01 || 1;
    lo -= padV; hi += padV;
    const ticks = niceTicks(lo, hi, narrow ? 4 : 5);
    const step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
    // extend to a round tick beyond the data on both sides, so the line never runs past the last gridline
    if (ticks[ticks.length - 1] < dataHi) ticks.push(+(ticks[ticks.length - 1] + step).toPrecision(12));
    if (ticks[0] > dataLo) ticks.unshift(+(ticks[0] - step).toPrecision(12));
    lo = ticks[0]; hi = ticks[ticks.length - 1];
    let decimals = 0; // as many as the tick step needs: 10 → 0, 2.5 → 1, 0.05 → 2
    while (decimals < 6 && Math.abs(step * 10 ** decimals - Math.round(step * 10 ** decimals)) > 1e-6) decimals++;
    const tickFmt = new Intl.NumberFormat(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

    const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
    const x = t => pad.left + ((t - t0) / (t1 - t0 || 1)) * iw;
    const y = v => pad.top + (1 - (v - lo) / (hi - lo)) * ih;

    const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "Exchange-rate history" });

    // grid + y labels
    const grid = s("g", { class: "grid" });
    for (const v of ticks) {
      const yy = Math.round(y(v)) + 0.5;
      grid.appendChild(s("line", { x1: pad.left, x2: pad.left + iw, y1: yy, y2: yy }));
      svg.appendChild(text(pad.left - 8, yy + 4, tickFmt.format(v), { "text-anchor": "end" }));
    }
    svg.insertBefore(grid, svg.firstChild);
    // x labels + baseline
    for (const tk of timeTicks(t0, t1, iw)) {
      const xx = x(tk.t);
      if (xx < pad.left + 16 || xx > pad.left + iw - 16) continue;
      svg.appendChild(s("line", { class: "baseline", x1: xx, x2: xx, y1: pad.top + ih, y2: pad.top + ih + 4 }));
      svg.appendChild(text(xx, pad.top + ih + 18, tk.label, { "text-anchor": "middle" }));
    }
    svg.appendChild(s("line", { class: "baseline", x1: pad.left, x2: pad.left + iw, y1: pad.top + ih + 0.5, y2: pad.top + ih + 0.5 }));

    const path = key => pts.map((p, i) => (i ? "L" : "M") + x(p.t).toFixed(1) + " " + y(p[key]).toFixed(1)).join("");
    const refLine = (v, color, w) => s("line", { x1: pad.left, x2: pad.left + iw, y1: y(v), y2: y(v), stroke: color, "stroke-width": w });

    // reference lines under the data
    svg.appendChild(refLine(opts.average, "var(--reference)", 1.5));
    if (showReal) svg.appendChild(refLine(opts.realAverage, "var(--series-2)", 1.5));

    if (showReal) svg.appendChild(s("path", { d: path("r"), fill: "none", stroke: "var(--series-2)", "stroke-width": 2, "stroke-linejoin": "miter", "stroke-linecap": "butt" }));
    svg.appendChild(s("path", { d: path("v"), fill: "none", stroke: "var(--series-1)", "stroke-width": 2, "stroke-linejoin": "miter", "stroke-linecap": "butt" }));

    // today marker: 8px+ dot with a 2px surface ring
    const last = pts[pts.length - 1];
    svg.appendChild(s("rect", { x: x(last.t) - 5, y: y(last.v) - 5, width: 10, height: 10, fill: "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2 }));

    // direct labels in the right gutter (wide screens); avoid collisions by nudging
    if (!narrow) {
      const labels = [
        { v: last.v, lines: [opts.labels.today, fmtV(last.v)], cls: "now-label" },
        { v: opts.average, lines: [opts.labels.average, fmtV(opts.average)], cls: "ref-label" },
      ];
      if (showReal) labels.push({ v: opts.realAverage, lines: [opts.labels.realAverage, fmtV(opts.realAverage)], cls: "ref-label" });
      labels.sort((a, b) => y(a.v) - y(b.v));
      let prevBottom = -Infinity;
      for (const l of labels) {
        let top = Math.max(y(l.v) - 10, prevBottom + 4);
        top = Math.min(top, pad.top + ih - 26);
        prevBottom = top + 28;
        const g = s("g");
        g.appendChild(text(pad.left + iw + 10, top + 10, l.lines[0], { class: "small-label" }));
        g.appendChild(text(pad.left + iw + 10, top + 25, l.lines[1], { class: l.cls }));
        svg.appendChild(g);
      }
    }

    // crosshair
    const cross = s("g", { visibility: "hidden" });
    const vline = s("line", { y1: pad.top, y2: pad.top + ih, stroke: "var(--axis)", "stroke-width": 1 });
    const dotV = s("rect", { width: 8, height: 8, fill: "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2 });
    const dotR = s("rect", { width: 8, height: 8, fill: "var(--series-2)", stroke: "var(--surface)", "stroke-width": 2 });
    cross.append(vline, dotV);
    if (showReal) cross.appendChild(dotR);
    svg.appendChild(cross);

    // hit area covers the whole plot so the pointer only needs the right x
    const hit = s("rect", { x: pad.left, y: pad.top, width: iw, height: ih, fill: "transparent" });
    svg.appendChild(hit);

    container.replaceChildren(svg);
    const tip = document.createElement("div");
    tip.className = "chart-tip";
    tip.hidden = true;
    container.appendChild(tip);

    function tipRow(color, label, value) {
      const row = document.createElement("div");
      row.className = "tip-row";
      const name = document.createElement("span");
      if (color) {
        const key = document.createElement("i");
        key.className = "key-line";
        key.style.background = color;
        name.appendChild(key);
      }
      name.appendChild(document.createTextNode(label));
      const val = document.createElement("b");
      val.textContent = value;
      row.append(name, val);
      return row;
    }

    let current = -1;
    function show(i) {
      current = i;
      const p = pts[i];
      const px = x(p.t);
      vline.setAttribute("x1", px); vline.setAttribute("x2", px);
      dotV.setAttribute("x", px - 4); dotV.setAttribute("y", y(p.v) - 4);
      if (showReal) { dotR.setAttribute("x", px - 4); dotR.setAttribute("y", y(p.r) - 4); }
      cross.setAttribute("visibility", "visible");

      const head = document.createElement("div");
      head.className = "tip-date";
      head.textContent = fmtD(p.date);
      tip.replaceChildren(head, tipRow("var(--series-1)", opts.labels.rate, fmtV(p.v)));
      if (showReal) tip.appendChild(tipRow("var(--series-2)", opts.labels.real, fmtV(p.r)));
      tip.appendChild(tipRow("var(--reference)", opts.labels.average, fmtV(opts.average)));
      const diff = (p.v / opts.average - 1) * 100;
      const deltaRow = tipRow(null, opts.labels.vsAverage || "vs average", (diff >= 0.05 ? "+" : diff <= -0.05 ? "−" : "") + Math.abs(diff).toFixed(1) + "%");
      deltaRow.classList.add("tip-delta");
      if (Math.abs(diff) >= 0.05) deltaRow.querySelector("b").className = diff > 0 ? "up" : "down";
      tip.appendChild(deltaRow);
      tip.hidden = false;
      const tw = tip.offsetWidth;
      let left = px + 14;
      if (left + tw > width) left = px - tw - 14;
      tip.style.left = Math.max(0, left) + "px";
      tip.style.top = pad.top + 4 + "px";
    }
    function hide() { cross.setAttribute("visibility", "hidden"); tip.hidden = true; }
    function nearest(clientX) {
      const rect = svg.getBoundingClientRect();
      const t = t0 + ((clientX - rect.left - pad.left) / iw) * (t1 - t0);
      let lo2 = 0, hi2 = pts.length - 1;
      while (hi2 - lo2 > 1) { const mid = (lo2 + hi2) >> 1; if (pts[mid].t < t) lo2 = mid; else hi2 = mid; }
      return Math.abs(pts[lo2].t - t) <= Math.abs(pts[hi2].t - t) ? lo2 : hi2;
    }
    svg.addEventListener("pointermove", e => show(nearest(e.clientX)));
    svg.addEventListener("pointerdown", e => show(nearest(e.clientX)));
    svg.addEventListener("pointerleave", hide);

    // keyboard: focus the chart, arrows move the crosshair
    container.tabIndex = 0;
    container.onkeydown = e => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight" && e.key !== "Home" && e.key !== "End") return;
      e.preventDefault();
      const step = e.shiftKey ? 20 : 1;
      let i = current < 0 ? pts.length - 1 : current;
      if (e.key === "ArrowLeft") i = Math.max(0, i - step);
      if (e.key === "ArrowRight") i = Math.min(pts.length - 1, i + step);
      if (e.key === "Home") i = 0;
      if (e.key === "End") i = pts.length - 1;
      show(i);
    };
    container.onblur = hide;
  }

  function mount(container, opts) {
    let frame = 0;
    const draw = () => render(container, opts);
    draw();
    const ro = new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(draw); });
    ro.observe(container);
    return {
      update(next) { Object.assign(opts, next); draw(); },
      destroy() { ro.disconnect(); },
    };
  }

  window.QChart = { mount };
})();
