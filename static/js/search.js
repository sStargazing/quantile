/* Destination search: "/" or ⌘K / Ctrl+K anywhere, or the header button.
   Enter opens the destination's analysis with the current home currency and period. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const palette = $("palette"), input = $("palette-input"), list = $("palette-list"), trigger = $("search-trigger");
  if (!palette) return;

  let destinations = null, results = [], active = 0, returnFocus = null;

  // "Türkiye" → "turkiye", so typing without accents still matches.
  const norm = s => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

  function prepare(list) {
    return list.filter(d => d.enabled).map(d => ({
      d,
      name: norm(d.display_name),
      country: norm(d.country),
      words: norm(d.display_name + " " + d.country).split(/[\s()\-]+/).filter(Boolean),
      aliases: (d.aliases || []).map(norm),
      codes: [norm(d.currency_code), norm(d.iso2)],
      currency: norm(d.currency_name),
      slug: d.id.replace(/-/g, " "),
    }));
  }

  /* Higher is better; 0 means no match. Exact codes first ("jpy", "jp"), then names that start with the query. */
  function score(item, q) {
    if (!q) return 1;
    if (item.codes.includes(q) || item.aliases.includes(q)) return 100;
    if (item.name.startsWith(q) || item.country.startsWith(q)) return 80;
    if (item.words.some(w => w.startsWith(q))) return 60;
    if (item.aliases.some(a => a.startsWith(q)) || item.slug.startsWith(q)) return 55;
    if (item.codes.some(c => c.startsWith(q))) return 50;
    if (item.currency.split(" ").some(w => w.startsWith(q))) return 40;
    if (q.length >= 2 && (item.name.includes(q) || item.currency.includes(q))) return 20; // mid-word, 2+ letters only
    return 0;
  }

  function href(d) {
    const sel = Q.readSelection({ base: "AUD", period: "5y" });
    return "/country/" + encodeURIComponent(d.id) + "?" + Q.selectionQuery(sel);
  }

  function render() {
    const q = norm(input.value);
    const home = Q.readSelection({ base: "AUD", period: "5y" }).base;
    results = destinations
      .map(item => ({ item, s: score(item, q) }))
      .filter(r => r.s > 0)
      .sort((a, b) => b.s - a.s || a.item.d.display_name.localeCompare(b.item.d.display_name))
      .map(r => r.item.d);
    active = Math.min(active, Math.max(0, results.length - 1));

    if (!results.length) {
      list.replaceChildren(Q.el("li", { class: "p-empty", role: "presentation" },
        "No destinations match “" + input.value.trim() + "”. Quantile covers " + destinations.length + " destinations."));
      input.removeAttribute("aria-activedescendant");
      return;
    }
    list.replaceChildren(...results.map((d, i) => Q.el("li", {
      id: "palette-opt-" + i, role: "option", "aria-selected": String(i === active), "data-index": String(i),
    },
      Q.el("span", { "aria-hidden": "true" }, d.flag),
      Q.el("span", null, Q.el("span", { class: "p-name" }, d.display_name),
        d.currency_code === home ? Q.el("span", { class: "p-note" }, "your home currency") : null),
      Q.el("span", { class: "p-code" }, d.currency_code))));
    input.setAttribute("aria-activedescendant", "palette-opt-" + active);
  }

  function move(delta) {
    if (!results.length) return;
    active = (active + delta + results.length) % results.length;
    for (const li of list.children) li.setAttribute("aria-selected", String(li.dataset.index === String(active)));
    input.setAttribute("aria-activedescendant", "palette-opt-" + active);
    const node = list.children[active];
    if (node) node.scrollIntoView({ block: "nearest" });
  }

  function go(i) {
    const d = results[i];
    if (d) location.href = href(d);
  }

  async function open() {
    if (!palette.hidden) return;
    returnFocus = document.activeElement;
    palette.hidden = false;
    input.value = "";
    active = 0;
    input.focus();
    if (!destinations) {
      list.replaceChildren(Q.el("li", { class: "p-empty", role: "presentation" }, "Loading destinations…"));
      try {
        destinations = prepare(await Q.fetchJSON("/api/destinations"));
      } catch (e) {
        list.replaceChildren(Q.el("li", { class: "p-empty", role: "presentation" }, "Destinations couldn't be loaded: " + e.message));
        return;
      }
    }
    render();
  }

  function close() {
    if (palette.hidden) return;
    palette.hidden = true;
    if (returnFocus && returnFocus.focus) returnFocus.focus();
  }

  function typingInField(target) {
    return target.closest("input, textarea, select, [contenteditable='true']");
  }

  document.addEventListener("keydown", e => {
    if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      palette.hidden ? open() : close();
    } else if (e.key === "/" && palette.hidden && !typingInField(e.target) && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      open();
    }
  });

  input.addEventListener("input", () => { active = 0; if (destinations) render(); });
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") { e.preventDefault(); go(active); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Tab") { e.preventDefault(); move(e.shiftKey ? -1 : 1); } // keep focus inside the dialog
  });
  list.addEventListener("mousemove", e => {
    const li = e.target.closest("li[data-index]");
    if (li && Number(li.dataset.index) !== active) move(Number(li.dataset.index) - active);
  });
  list.addEventListener("click", e => {
    const li = e.target.closest("li[data-index]");
    if (li) go(Number(li.dataset.index));
  });
  palette.addEventListener("click", e => { if (e.target.hasAttribute("data-close")) close(); });
  trigger.addEventListener("click", open);
})();
