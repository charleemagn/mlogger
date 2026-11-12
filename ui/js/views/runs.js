import { h, clear, icon, ask, toast, fmtNum, fmtDur, fmtDate, plural, statusChip, verdictChip, tagEl, store } from "../dom.js";
import { api } from "../api.js";
import { lang, t } from "../i18n.js";
import { mainMetric, importDialog, emptyIcon } from "../parts.js";
import { sparkline } from "../chart.js";

export const selected = new Set();

const STATUSES = [["", t("Любой статус")], ["running", t("Идёт")], ["finished", t("Завершён")], ["failed", t("Ошибка")], ["stopped", t("Остановлен")], ["crashed", t("Прерван")]];
const SORTS = [["new", t("Сначала новые")], ["best", t("По главной метрике")], ["health", t("По индексу здоровья")]];

export function mount(root, ctx) {
  const filter = store.get("runs-filter", { text: "", project: "", status: "", sort: "new" });
  const tags = new Set();
  let runs = [], projects = [], sig = "";

  const search = h("input", { class: "input", type: "search", placeholder: t("Поиск по имени, метке, параметру"), value: filter.text,
    style: { width: "280px" }, "aria-label": t("Поиск"), oninput: () => { filter.text = search.value; changed(); } });
  const projectSel = h("select", { class: "input", "aria-label": t("Проект"), onchange: () => { filter.project = projectSel.value; changed(); } });
  const statusSel = h("select", { class: "input", "aria-label": t("Статус"), onchange: () => { filter.status = statusSel.value; changed(); } },
    STATUSES.map(([v, l]) => h("option", { value: v, selected: v === filter.status }, l)));
  const sortSel = h("select", { class: "input", "aria-label": t("Сортировка"), onchange: () => { filter.sort = sortSel.value; changed(); } },
    SORTS.map(([v, l]) => h("option", { value: v, selected: v === filter.sort }, l)));
  const tagRow = h("div", { class: "tags", style: { marginBottom: "12px" } });
  const table = h("div");
  const bulk = h("div", { class: "bulk", hidden: true });

  root.append(
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, t("Запуски")), h("div", { class: "sub" }, t("Все обучения: идущие, завершённые и импортированные"))),
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => importDialog(() => refresh()) }, icon("upload", "sm"), t("Импорт логов")))),
    h("div", { class: "filters" }, search, projectSel, statusSel, sortSel),
    tagRow, table, bulk);

  function changed() { store.set("runs-filter", filter); render(); }

  function visible() {
    const text = filter.text.trim().toLowerCase();
    let out = runs.filter((r) => {
      if (filter.project && r.project !== filter.project) return false;
      if (filter.status && r.status !== filter.status) return false;
      for (const t of tags) if (!r.tags.includes(t)) return false;
      if (!text) return true;
      const hay = [r.name, r.project, r.notes, ...r.tags, JSON.stringify(r.config)].join(" ").toLowerCase();
      return text.split(/\s+/).every((word) => hay.includes(word));
    });
    if (filter.sort === "health") {
      out = [...out].sort((a, b) => (b.summary.diagnosis.health ?? -1) - (a.summary.diagnosis.health ?? -1));
    } else if (filter.sort === "best") {
      const score = (r) => { const m = mainMetric(r); return m && m.info.direction ? (m.info.direction === "min" ? -m.info.best : m.info.best) : -Infinity; };
      out = [...out].sort((a, b) => score(b) - score(a));
    }
    return out;
  }

  function render() {
    clear(projectSel, h("option", { value: "" }, t("Все проекты")), projects.map((p) => h("option", { value: p, selected: p === filter.project }, p)));
    const allTags = [...new Set(runs.flatMap((r) => r.tags))].sort((a, b) => a.localeCompare(b, lang));
    for (const t of [...tags]) if (!allTags.includes(t)) tags.delete(t);
    clear(tagRow, allTags.length ? h("span", { class: "muted", style: { fontSize: "13px" } }, t("Метки:")) : null,
      allTags.map((t) => tagEl(t, { pressed: tags.has(t), onClick: () => { tags.has(t) ? tags.delete(t) : tags.add(t); render(); } })));

    const rows = visible();
    for (const id of [...selected]) if (!runs.some((r) => r.id === id)) selected.delete(id);
    if (!runs.length) {
      clear(table, h("div", { class: "card empty" }, emptyIcon("runs"), h("h3", null, t("Запусков пока нет")),
        h("div", null, t("Подключите своё обучение или загляните в демо-данные.")),
        h("div", { class: "row" }, h("a", { class: "btn primary", href: "#/connect" }, t("Как подключить")),
          h("button", { class: "btn", onclick: async () => { await api.demo(); refresh(); } }, icon("spark", "sm"), t("Демо-данные")))));
    } else if (!rows.length) {
      clear(table, h("div", { class: "card empty" }, h("h3", null, t("Ничего не найдено")), h("div", null, t("Попробуйте изменить поиск или сбросить фильтры.")),
        h("div", { class: "row" }, h("button", { class: "btn", onclick: () => { Object.assign(filter, { text: "", project: "", status: "" }); search.value = ""; statusSel.value = ""; tags.clear(); changed(); } }, t("Сбросить фильтры")))));
    } else {
      const allOn = rows.every((r) => selected.has(r.id));
      clear(table, h("div", { class: "card table-card" }, h("table", null,
        h("thead", null, h("tr", null,
          h("th", null, h("input", { type: "checkbox", checked: allOn, "aria-label": t("Выбрать все"), onchange: (e) => { rows.forEach((r) => (e.target.checked ? selected.add(r.id) : selected.delete(r.id))); render(); } })),
          h("th", null, t("Запуск")), h("th", null, t("Статус")), h("th", null, t("Диагноз")), h("th", { class: "n" }, t("Здоровье")),
          h("th", null, t("Главная метрика")), h("th", null, t("Динамика")), h("th", { class: "n" }, t("Шагов")), h("th", { class: "n" }, t("Длительность")))),
        h("tbody", null, rows.map(row)))));
    }
    renderBulk();
  }

  function row(r) {
    const s = r.summary, main = mainMetric(r);
    return h("tr", { class: "click", onclick: (e) => { if (!e.target.closest("input, .tag, a")) ctx.navigate(`#/run/${r.id}`); } },
      h("td", null, h("input", { type: "checkbox", checked: selected.has(r.id), "aria-label": t("Выбрать {0}", [r.name]),
        onchange: (e) => { e.target.checked ? selected.add(r.id) : selected.delete(r.id); renderBulk(); } })),
      h("td", null,
        h("a", { class: "name", href: `#/run/${r.id}` }, r.name),
        h("div", { class: "sub" }, `${r.project} · ${fmtDate(r.created_at)}`),
        r.tags.length ? h("div", { class: "tags", style: { marginTop: "5px" } }, r.tags.map((t) => tagEl(t, { pressed: tags.has(t), onClick: () => { tags.has(t) ? tags.delete(t) : tags.add(t); render(); } }))) : null),
      h("td", null, statusChip(r.status),
        r.status === "running" && s.progress != null ? h("div", { class: "sub nowrap", style: { marginTop: "4px" } }, `${Math.round(s.progress * 100)}%${s.eta != null ? ` · ≈ ${fmtDur(s.eta)}` : ""}`) : null),
      h("td", null, verdictChip(s.diagnosis)),
      h("td", { class: "n" }, s.diagnosis.health == null ? h("span", { class: "muted" }, "—") : String(s.diagnosis.health)),
      h("td", null, main ? [h("div", { class: "num", style: { fontWeight: 600 } }, fmtNum(main.info.best)), h("div", { class: "sub mono" }, main.key)] : h("span", { class: "muted" }, "—")),
      h("td", { style: { width: "130px" } }, main ? sparkline(main.info.spark, { height: 28 }) : null),
      h("td", { class: "n" }, s.max_step == null ? "—" : fmtNum(s.max_step, 0)),
      h("td", { class: "n nowrap" }, fmtDur(s.duration)));
  }

  function renderBulk() {
    bulk.hidden = !selected.size;
    if (!selected.size) return;
    clear(bulk,
      h("span", null, t("Выбрано: {0}", [plural(selected.size, t("запуск"), t("запуска"), t("запусков"))])), h("span", { class: "spacer" }),
      h("button", { class: "btn primary", disabled: selected.size < 2, title: selected.size < 2 ? t("Выберите хотя бы два запуска") : "",
        onclick: () => ctx.navigate(`#/compare?ids=${[...selected].slice(0, 8).join(",")}`) }, icon("compare", "sm"), t("Сравнить")),
      h("button", { class: "btn", onclick: removeSelected }, icon("trash", "sm"), t("Удалить")),
      h("button", { class: "btn", onclick: () => { selected.clear(); render(); } }, t("Снять выбор")));
  }

  async function removeSelected() {
    const n = selected.size;
    const ok = await ask({ title: t("Удалить {0}?", [plural(n, t("запуск"), t("запуска"), t("запусков"))]), text: t("Метрики и параметры этих запусков будут удалены без возможности восстановления."), ok: t("Удалить"), danger: true });
    if (!ok) return;
    try {
      await Promise.all([...selected].map((id) => api.deleteRun(id)));
      toast(t("Удалено: {0}", [n]), "ok");
    } catch (e) { toast(e.message, "crit"); }
    selected.clear();
    refresh();
  }

  async function refresh() {
    const data = await api.runs();
    ctx.setRunning(data.runs.filter((r) => r.status === "running").length);
    const next = JSON.stringify(data.runs.map((r) => [r.id, r.name, r.status, r.tags, r.project, r.summary.max_step, r.summary.diagnosis.verdict.code,
      r.summary.diagnosis.health, Math.round((r.summary.progress || 0) * 100), r.status === "running" ? Math.round(r.summary.duration / 5) : 0]));
    runs = data.runs;
    projects = data.projects;
    if (next !== sig) { sig = next; render(); }
  }

  return { refresh };
}
