import { h, clear, icon, fmtNum, fmtAxis, fmtDur, statusChip, verdictChip, store } from "../dom.js";
import { api } from "../api.js";
import { ChartCard, SLOTS } from "../chart.js";
import { selected } from "./runs.js";
import { emptyIcon } from "../parts.js";
import { t } from "../i18n.js";

const slotOf = new Map();
const KIND_ORDER = { score: 0, loss: 1, lr: 2, other: 3, aux: 4 };

function slotFor(id, ids) {
  for (const key of [...slotOf.keys()]) if (!ids.includes(key)) slotOf.delete(key);
  if (!slotOf.has(id)) {
    const used = new Set(slotOf.values());
    slotOf.set(id, [0, 1, 2, 3, 4, 5, 6, 7].find((i) => !used.has(i)) ?? 0);
  }
  return slotOf.get(id);
}

function flatten(obj, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    if (v && typeof v === "object" && !Array.isArray(v)) flatten(v, `${prefix}${k}.`, out);
    else out[prefix + k] = v;
  }
  return out;
}

export function mount(root, ctx) {
  const ids = (ctx.query.get("ids") || "").split(",").filter(Boolean).slice(0, 8);
  const view = store.get("compare-view", { smooth: 0.6, log: false, onlyDiff: true });
  const cards = new Map();
  let runs = [], metrics = {}, loaded = false, destroyed = false;

  root.append(h("div", { class: "page-head" },
    h("div", null, h("h1", null, t("Сравнение запусков")), h("div", { class: "sub" }, t("Одни и те же метрики разных запусков на общих графиках")))));

  if (ids.length < 2) {
    root.append(h("div", { class: "card empty" }, emptyIcon("compare"), h("h3", null, t("Выберите запуски для сравнения")),
      h("div", null, t("Отметьте галочками два и более запусков в списке и нажмите «Сравнить».")),
      h("div", { class: "row" }, h("a", { class: "btn primary", href: "#/runs" }, t("К списку запусков")))));
    return {};
  }
  ids.forEach((id) => selected.add(id));

  const legend = h("div", { class: "tags", style: { marginBottom: "16px" } });
  const summary = h("div");
  const grid = h("div", { class: "grid charts" });
  const params = h("div");
  const smoothInput = h("input", { type: "range", min: 0, max: 0.95, step: 0.05, value: view.smooth, oninput: () => { view.smooth = +smoothInput.value; apply(); } });
  const logInput = h("input", { type: "checkbox", checked: view.log, onchange: () => { view.log = logInput.checked; apply(); } });
  root.append(legend, summary,
    h("div", { class: "section" }, h("h2", null, t("Графики")),
      h("div", { class: "filters", style: { marginTop: "10px" } }, h("label", null, t("Сглаживание"), smoothInput), h("label", null, logInput, t("Логарифмическая шкала"))),
      grid),
    h("div", { class: "section" }, h("h2", null, t("Параметры")), params));

  function apply() {
    store.set("compare-view", view);
    for (const card of cards.values()) card.chart.set({ smooth: view.smooth, log: view.log });
  }

  const swatch = (run) => h("i", { class: "swatch", style: { background: `var(${SLOTS[slotFor(run.id, ids)]})` } });

  function renderLegend() {
    clear(legend, runs.map((r) => h("span", { class: "chip" }, swatch(r), h("a", { href: `#/run/${r.id}` }, r.name),
      h("button", { class: "btn ghost sm", style: { padding: "0 4px" }, title: t("Убрать из сравнения"), "aria-label": t("Убрать {0} из сравнения", [r.name]),
        onclick: () => { selected.delete(r.id); ctx.navigate(`#/compare?ids=${ids.filter((x) => x !== r.id).join(",")}`); } }, "×"))));
  }

  function renderSummary() {
    const mains = [...new Set(runs.map((r) => r.summary.main_key).filter(Boolean))];
    const key = mains.sort((a, b) => runs.filter((r) => r.summary.main_key === b).length - runs.filter((r) => r.summary.main_key === a).length)[0];
    const values = runs.map((r) => (key && r.summary.keys[key] ? r.summary.keys[key].best : null));
    const dir = key && runs.map((r) => r.summary.keys[key]).find(Boolean)?.direction;
    const real = values.filter((v) => v != null);
    const best = real.length ? (dir === "min" ? Math.min(...real) : Math.max(...real)) : null;
    clear(summary, h("div", { class: "card table-card" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, t("Запуск")), h("th", null, t("Статус")), h("th", null, t("Диагноз")), h("th", { class: "n" }, t("Здоровье")),
        h("th", { class: "n" }, key ? t("{0}, лучшее", [key]) : t("Главная метрика")), h("th", { class: "n" }, t("Шагов")), h("th", { class: "n" }, t("Длительность")))),
      h("tbody", null, runs.map((r, i) => h("tr", null,
        h("td", null, h("div", { class: "row", style: { flexWrap: "nowrap" } }, swatch(r), h("a", { class: "name", href: `#/run/${r.id}` }, r.name))),
        h("td", null, statusChip(r.status)), h("td", null, verdictChip(r.summary.diagnosis)),
        h("td", { class: "n" }, r.summary.diagnosis.health ?? "—"),
        h("td", { class: "n" }, values[i] == null ? "—" : [fmtNum(values[i]), values[i] === best && real.length > 1 ? h("span", { class: "chip ok", style: { marginLeft: "8px" } }, icon("check"), t("лучший")) : null]),
        h("td", { class: "n" }, r.summary.max_step == null ? "—" : fmtNum(r.summary.max_step, 0)),
        h("td", { class: "n nowrap" }, fmtDur(r.summary.duration))))))));
  }

  function renderCharts() {
    const keys = new Map();
    for (const r of runs) for (const [key, info] of Object.entries(r.summary.keys)) if (!keys.has(key)) keys.set(key, info);
    const main = runs[0] && runs[0].summary.main_key;
    const order = [...keys].sort((a, b) => (b[0] === main) - (a[0] === main) || (KIND_ORDER[a[1].kind] ?? 9) - (KIND_ORDER[b[1].kind] ?? 9) || a[0].localeCompare(b[0]));
    for (const [key, info] of order) {
      const series = runs.filter((r) => metrics[r.id] && metrics[r.id][key]).map((r) => ({
        name: r.name, color: SLOTS[slotFor(r.id, ids)], x: metrics[r.id][key].steps, y: metrics[r.id][key].values }));
      if (!series.length) continue;
      if (!cards.has(key)) {
        const card = new ChartCard({ title: key, what: info.hint ? (info.title === info.label ? "" : info.title + ". ") + info.hint : "",
          chart: { smooth: view.smooth, log: view.log, sync: "compare", xFormat: fmtAxis } });
        cards.set(key, card);
        grid.append(card.el);
      }
      cards.get(key).setData(series);
    }
  }

  function renderParams() {
    const flat = runs.map((r) => flatten(r.config));
    const names = [...new Set(flat.flatMap((f) => Object.keys(f)))].sort();
    const rows = names.map((name) => {
      const vals = flat.map((f) => (name in f ? JSON.stringify(f[name]) : null));
      return { name, vals, diff: new Set(vals).size > 1 };
    });
    const shown = view.onlyDiff ? rows.filter((r) => r.diff) : rows;
    const toggle = h("input", { type: "checkbox", checked: view.onlyDiff, onchange: () => { view.onlyDiff = toggle.checked; store.set("compare-view", view); renderParams(); } });
    clear(params,
      h("div", { class: "filters", style: { marginTop: "10px" } }, h("label", null, toggle, t("Только различающиеся")),
        h("span", { class: "muted" }, t("{0} из {1} параметров отличаются", [rows.filter((r) => r.diff).length, rows.length]))),
      !names.length ? h("div", { class: "note-box" }, t("У этих запусков нет параметров. Передавайте их через config={...} в mlogger.init()."))
        : !shown.length ? h("div", { class: "note-box" }, t("Параметры запусков совпадают."))
        : h("div", { class: "card table-card" }, h("table", null,
          h("thead", null, h("tr", null, h("th", null, t("Параметр")), runs.map((r) => h("th", null, h("div", { class: "row", style: { flexWrap: "nowrap" } }, swatch(r), r.name))))),
          h("tbody", null, shown.map((row) => h("tr", { class: row.diff && !view.onlyDiff ? "diff" : "" },
            h("td", { class: "dim" }, row.name), row.vals.map((v) => h("td", { class: "mono" }, v == null ? "—" : v.replace(/^"|"$/g, "")))))))));
  }

  async function refresh() {
    if (destroyed || (loaded && !runs.some((r) => r.status === "running"))) return;
    const results = await Promise.all(ids.map((id) => api.run(id).catch(() => null)));
    runs = results.filter(Boolean);
    const data = await Promise.all(runs.map((r) => api.metrics(r.id, 500)));
    if (destroyed) return;
    runs.forEach((r, i) => (metrics[r.id] = data[i].series));
    loaded = true;
    renderLegend();
    renderSummary();
    renderCharts();
    renderParams();
  }

  return { refresh, destroy() { destroyed = true; for (const c of cards.values()) c.destroy(); } };
}
