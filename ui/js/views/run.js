import { h, clear, icon, ask, toast, fmtNum, fmtAxis, fmtDur, fmtDate, fmtClock, fmtGb, statusChip, tagEl, store } from "../dom.js";
import { api } from "../api.js";
import { ChartCard, SLOTS, healthRing, sparkline } from "../chart.js";
import { selected } from "./runs.js";

const SECTIONS = [
  ["score", "Качество", "Насколько хорошо модель решает задачу. Чем выше линия, тем лучше."],
  ["loss", "Потери", "Насколько модель ошибается. Хорошее обучение — линии идут вниз и не расходятся друг с другом."],
  ["lr", "Настройки обучения", "Как менялся шаг обучения."],
  ["other", "Прочее", "Остальные числа, которые записывал код обучения."],
];
const SPLIT_ORDER = { train: 0, val: 1, test: 2 };
const SPLIT_NAME = { train: "обучение", val: "проверка", test: "тест" };

function flatten(obj, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    if (v && typeof v === "object" && !Array.isArray(v)) flatten(v, `${prefix}${k}.`, out);
    else out[prefix + k] = v;
  }
  return out;
}

const show = (v) => (v == null ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));

export function mount(root, ctx) {
  const id = ctx.params[0];
  const view = store.get("chart-view", { smooth: 0.6, axis: "step", log: false });
  let run = null, series = {}, built = false, lastSystem = 0, healthSig = "", destroyed = false;
  const cards = new Map();
  const grids = new Map();
  const hwCards = new Map();

  const head = h("div");
  const statusRow = h("div", { class: "row", style: { marginBottom: "14px" } });
  const tagsRow = h("div", { class: "tags", style: { marginBottom: "18px" } });
  const healthCard = h("div", { class: "card" });
  const tiles = h("div", { class: "grid pair", style: { alignContent: "start" } });
  const chartsBox = h("div");
  const hwBox = h("div");
  const paramsBox = h("div", { class: "grid two" });
  const notes = h("textarea", { class: "input", placeholder: "Что проверяли в этом запуске, что получилось, что попробовать дальше…",
    onchange: async () => { try { await api.patchRun(id, { notes: notes.value }); toast("Заметка сохранена", "ok"); } catch (e) { toast(e.message, "crit"); } } });

  root.append(h("a", { class: "back", href: "#/runs" }, icon("back", "sm"), "Все запуски"), head);

  function build() {
    built = true;
    const smoothInput = h("input", { type: "range", min: 0, max: 0.95, step: 0.05, value: view.smooth,
      oninput: () => { view.smooth = +smoothInput.value; applyView(); } });
    const axisBtn = (mode, label) => h("button", { type: "button", "aria-pressed": String(view.axis === mode),
      onclick: (e) => { view.axis = mode; for (const b of e.target.parentNode.children) b.setAttribute("aria-pressed", String(b === e.target)); applyView(true); } }, label);
    const logInput = h("input", { type: "checkbox", checked: view.log, onchange: () => { view.log = logInput.checked; applyView(); } });
    root.append(
      statusRow, tagsRow,
      h("div", { class: "grid split" }, healthCard, tiles),
      h("div", { class: "section" },
        h("h2", null, "Графики"),
        h("div", { class: "filters", style: { marginTop: "10px" } },
          h("label", null, "Сглаживание", smoothInput),
          h("div", { class: "seg", role: "group", "aria-label": "Ось X" }, axisBtn("step", "По шагам"), axisBtn("time", "По времени")),
          h("label", null, logInput, "Логарифмическая шкала")),
        chartsBox),
      h("div", { class: "section" }, h("h2", null, "Железо во время обучения"), hwBox),
      h("div", { class: "section" }, h("h2", null, "Параметры и окружение"), paramsBox),
      h("div", { class: "section" }, h("h2", null, "Заметки"), notes));
  }

  function renderHead() {
    const s = run.summary;
    clear(head, h("div", { class: "page-head", style: { marginBottom: "12px" } },
      h("div", null,
        h("h1", null, run.name),
        h("div", { class: "sub" }, `Проект «${run.project}» · начат ${fmtDate(run.created_at)}${run.host ? ` · ${run.host}` : ""}`)),
      h("div", { class: "actions" },
        h("button", { class: "btn", onclick: rename }, icon("edit", "sm"), "Переименовать"),
        h("button", { class: "btn", title: "Добавить к сравнению и открыть его", onclick: () => { selected.add(id); ctx.navigate(`#/compare?ids=${[...selected].slice(0, 8).join(",")}`); } }, icon("compare", "sm"), "Сравнить"),
        h("button", { class: "btn danger", onclick: remove }, icon("trash", "sm"), "Удалить"))));
    clear(statusRow,
      statusChip(run.status),
      h("span", { class: "dim" }, icon("clock", "sm")), h("span", { class: "dim", style: { marginLeft: "-4px" } }, fmtDur(s.duration)),
      s.max_step != null ? h("span", { class: "dim" }, `шаг ${fmtNum(s.max_step, 0)}${run.total_steps ? ` из ${fmtNum(run.total_steps, 0)}` : ""}`) : null,
      s.progress != null && run.status === "running"
        ? [h("div", { class: "progress", style: { width: "180px" }, role: "progressbar", "aria-valuenow": Math.round(s.progress * 100), "aria-valuemin": 0, "aria-valuemax": 100 },
            h("i", { style: { width: `${s.progress * 100}%` } })),
          h("span", { class: "dim" }, `${Math.round(s.progress * 100)}%${s.eta != null ? ` · осталось ≈ ${fmtDur(s.eta)}` : ""}`)]
        : null,
      run.source !== "sdk" ? h("span", { class: "chip" }, run.source === "demo" ? "демо-данные" : `импорт: ${run.source}`) : null);
  }

  function renderTags() {
    const input = h("input", { class: "tag-input", placeholder: "+ метка", "aria-label": "Добавить метку", maxLength: 40,
      onkeydown: (e) => { if (e.key === "Enter" && input.value.trim()) setTags([...run.tags, input.value.trim()]); } });
    clear(tagsRow, run.tags.map((t) => tagEl(t, { onRemove: () => setTags(run.tags.filter((x) => x !== t)) })), input);
  }

  async function setTags(tags) {
    try { run.tags = (await api.patchRun(id, { tags })).tags; renderTags(); tagsRow.querySelector("input").focus(); }
    catch (e) { toast(e.message, "crit"); }
  }

  async function rename() {
    const v = await ask({ title: "Переименовать запуск", fields: [{ name: "name", label: "Имя", value: run.name }], ok: "Сохранить" });
    if (!v || !v.name) return;
    try { run = { ...run, name: (await api.patchRun(id, { name: v.name })).name }; renderHead(); } catch (e) { toast(e.message, "crit"); }
  }

  async function remove() {
    const ok = await ask({ title: `Удалить запуск «${run.name}»?`, text: "Метрики и параметры будут удалены без возможности восстановления.", ok: "Удалить", danger: true });
    if (!ok) return;
    try { await api.deleteRun(id); selected.delete(id); toast("Запуск удалён", "ok"); ctx.navigate("#/runs"); } catch (e) { toast(e.message, "crit"); }
  }

  function renderHealth() {
    const d = run.summary.diagnosis;
    const sig = JSON.stringify(d);
    if (sig === healthSig) return;
    healthSig = sig;
    clear(healthCard,
      h("div", { class: "health" },
        healthRing(d.health),
        h("div", null,
          h("div", { class: "muted", style: { fontSize: "12.5px" } }, "Диагноз обучения"),
          h("div", { class: "verdict" }, h("span", { class: `lv-${d.verdict.level}`, style: { display: "inline-flex" } }, icon(d.verdict.level)), d.verdict.label),
          h("div", { class: "dim", style: { marginTop: "4px", fontSize: "13px" } },
            d.health == null ? "Индекс здоровья появится, когда накопятся данные." : "Индекс здоровья: 100 — без замечаний. Считается по форме кривых и работе железа."))),
      h("div", { class: "findings" }, d.findings.map((f) => h("div", { class: "finding" },
        h("span", { class: `lv-${f.level}` }, icon(f.level)),
        h("div", null, h("b", null, f.title), h("p", { class: f.code === "failed" ? "pre" : "" }, f.text))))),
      d.findings.length ? null : h("div", { class: "muted", style: { marginTop: "12px" } }, "Замечаний нет."));
  }

  function renderTiles() {
    const s = run.summary, keys = s.keys;
    const picks = [s.main_key, s.diagnosis.val_key, s.diagnosis.train_key, Object.keys(keys).find((k) => keys[k].kind === "lr")]
      .filter((k, i, a) => k && keys[k] && keys[k].last != null && a.indexOf(k) === i).slice(0, 4);
    const options = Object.keys(keys).filter((k) => keys[k].direction);
    clear(tiles, picks.map((key, i) => {
      const info = keys[key];
      const best = info.direction && info.best != null;
      return h("div", { class: "card tile" },
        h("div", { class: "label" }, h("span", { class: "mono" }, key), i === 0 && key === s.main_key ? h("span", { class: "chip", style: { fontSize: "11px", padding: "0 7px" } }, "главная") : null),
        h("div", { class: "value" }, fmtNum(best ? info.best : info.last)),
        h("div", { class: "note" }, best ? `лучшее, шаг ${fmtNum(info.best_step, 0)} · сейчас ${fmtNum(info.last)}` : `последнее значение, шаг ${fmtNum(info.last_step, 0)}`),
        h("div", { class: "spark" }, sparkline(info.spark, { quiet: i > 0 })),
        info.hint ? h("div", { class: "note", style: { marginTop: "6px" } }, info.title === info.label ? info.hint : `${info.title}. ${info.hint}`) : null);
    }),
    !picks.length ? h("div", { class: "card empty" }, h("h3", null, "Метрик пока нет"), h("div", null, "Они появятся после первого вызова run.log().")) : null,
    options.length > 1 ? h("div", { class: "row dim", style: { gridColumn: "1 / -1", fontSize: "13px" } }, "Главная метрика:",
      h("select", { class: "input", style: { padding: "3px 8px" }, "aria-label": "Главная метрика",
        onchange: async (e) => { try { run = await api.patchRun(id, { main_metric: e.target.value }); renderTiles(); } catch (err) { toast(err.message, "crit"); } } },
        options.map((k) => h("option", { value: k, selected: k === s.main_key }, k)))) : null);
  }

  function chartOptions() {
    const time = view.axis === "time";
    return { smooth: view.smooth, log: view.log, sync: time ? "run-time" : "run-step", xTitle: time ? "время" : "шаг", xFormat: time ? fmtClock : fmtAxis, timeAxis: time };
  }

  function groupSeries(group) {
    const keys = Object.keys(run.summary.keys).filter((k) => run.summary.keys[k].group === group && series[k])
      .sort((a, b) => (SPLIT_ORDER[run.summary.keys[a].split] ?? 3) - (SPLIT_ORDER[run.summary.keys[b].split] ?? 3) || a.localeCompare(b));
    const taken = new Set();
    const time = view.axis === "time";
    return keys.slice(0, 8).map((key) => {
      let slot = SPLIT_ORDER[run.summary.keys[key].split] ?? 0;
      if (taken.has(slot)) {
        const free = [3, 4, 5, 6, 7, 0, 1, 2].filter((i) => !taken.has(i));
        slot = free[0];
      }
      taken.add(slot);
      const data = series[key];
      const split = run.summary.keys[key].split;
      return { name: keys.length > 1 && split ? `${key} · ${SPLIT_NAME[split]}` : key, color: SLOTS[slot],
        x: time && data.t ? data.t : data.steps, y: data.values };
    });
  }

  function renderCharts() {
    const keys = run.summary.keys;
    const groups = new Map();
    for (const [key, info] of Object.entries(keys)) {
      if (!series[key]) continue;
      const kind = info.kind === "aux" ? "other" : info.kind;
      if (!groups.has(info.group)) groups.set(info.group, { kind, info, main: false });
      if (key === run.summary.main_key) groups.get(info.group).main = true;
    }
    if (!groups.size && !cards.size) {
      clear(chartsBox, h("div", { class: "card empty" }, h("h3", null, "Графиков пока нет"), h("div", null, "Как только обучение запишет первые метрики, они появятся здесь.")));
      return;
    }
    for (const [kind, title, lead] of SECTIONS) {
      const mine = [...groups].filter(([, g]) => g.kind === kind).sort((a, b) => b[1].main - a[1].main || a[0].localeCompare(b[0]));
      if (!mine.length) continue;
      if (!grids.has(kind)) {
        if (!grids.size) clear(chartsBox);
        const grid = h("div", { class: "grid charts" });
        grids.set(kind, grid);
        const before = SECTIONS.slice(SECTIONS.findIndex((s) => s[0] === kind) + 1).map((s) => grids.get(s[0])).find(Boolean);
        const block = h("div", { style: { marginTop: "18px" } }, h("h3", { style: { fontSize: "14.5px" } }, title), h("div", { class: "dim", style: { margin: "2px 0 10px", fontSize: "13px" } }, lead), grid);
        before ? chartsBox.insertBefore(block, before.parentNode) : chartsBox.append(block);
      }
      for (const [group, g] of mine) {
        if (!cards.has(group)) {
          const what = g.info.hint ? (g.info.title === g.info.label ? "" : g.info.title + ". ") + g.info.hint.replace(/ Считается на .*$/, "") : "";
          const card = new ChartCard({ title: g.info.label, what, chart: chartOptions() });
          cards.set(group, card);
          grids.get(kind).append(card.el);
        }
        cards.get(group).setData(groupSeries(group));
      }
    }
  }

  function applyView(dataChanged) {
    store.set("chart-view", view);
    for (const [group, card] of cards) {
      card.chart.set(chartOptions());
      if (dataChanged) card.setData(groupSeries(group));
    }
  }

  function hwCard(key, title, what, chart) {
    if (!hwCards.has(key)) {
      const card = new ChartCard({ title, what, chart: { sync: "run-time", xTitle: "время", xFormat: fmtClock, timeAxis: true, height: 180, ...chart } });
      hwCards.set(key, card);
      hwBox.querySelector(".grid.charts").append(card.el);
    }
    return hwCards.get(key);
  }

  function renderSystem(data) {
    const sys = data.system;
    if (!sys) {
      if (hwCards.size) return;
      const cmd = `python -m monitor --server ${location.origin}`;
      clear(hwBox, h("div", { class: "note-box", style: { marginTop: "12px" } },
        run.source !== "sdk" && run.source !== "demo" ? "Для импортированных запусков показаний железа нет — они собираются только во время обучения."
          : !run.host ? "Запуск не сообщил, на какой машине он идёт."
          : `Нет показаний с машины «${run.host}». Если обучение идёт на другом компьютере, запустите там монитор из папки MLogger: ${cmd}`));
      return;
    }
    if (!hwBox.querySelector(".grid.charts")) {
      clear(hwBox, h("div", { class: "grid tiles", style: { marginTop: "12px" } }), h("div", { class: "grid charts", style: { marginTop: "14px" } }));
    }
    const hw = run.summary.hw;
    if (hw) {
      clear(hwBox.querySelector(".grid.tiles"), hw.gpus.map((g) => h("div", { class: "card tile" },
        h("div", { class: "label" }, h("span", { class: "vendor" }, g.vendor || "GPU"), g.name),
        h("div", { class: "value" }, g.util_avg == null ? "—" : `${Math.round(g.util_avg)}%`, h("small", null, "средняя загрузка")),
        h("div", { class: "note" }, [
          g.mem_max != null && g.mem_total ? `память до ${fmtGb(g.mem_max)} из ${fmtGb(g.mem_total)} ГБ` : null,
          g.temp_max != null ? `до ${Math.round(g.temp_max)} °C` : null,
          g.power_avg != null ? `≈ ${Math.round(g.power_avg)} Вт` : null].filter(Boolean).join(" · ") || "нет данных о памяти и температуре"))));
    }
    const gpuSeries = (field, scale = 1) => sys.gpus.slice(0, 8).map((g, i) => ({
      name: sys.gpus.length > 1 ? `GPU ${i} · ${g.name}` : g.name, color: SLOTS[i], x: sys.t, y: g[field].map((v) => (v == null ? null : v * scale)) }));
    const pctFmt = (v) => `${Math.round(v)}%`;
    if (sys.gpus.length) {
      hwCard("util", "Загрузка видеокарты, %", "Хорошо, когда во время обучения карта занята на 80–100%. Провалы — это ожидание данных.",
        { yMin: 0, yMax: 100, tipFormat: pctFmt, area: true }).setData(gpuSeries("util"));
      hwCard("mem", "Видеопамять, ГБ", "Сколько памяти карты занято. Упирается в потолок — возможна ошибка Out of Memory.",
        { yMin: 0, tipFormat: (v) => `${v.toFixed(1)} ГБ`, area: true }).setData(gpuSeries("mem", 1 / 2 ** 30));
      if (sys.gpus.some((g) => g.temp.some((v) => v != null))) {
        hwCard("temp", "Температура видеокарты, °C", "Выше 85 °C карта начинает сбрасывать частоты и работает медленнее.",
          { tipFormat: (v) => `${Math.round(v)} °C` }).setData(gpuSeries("temp").filter((s) => s.y.some((v) => v != null)));
      }
    }
    hwCard("cpu", "Процессор, %", "Загрузка всех ядер. Близко к 100% при простаивающей видеокарте — процессор не успевает готовить данные.",
      { yMin: 0, yMax: 100, tipFormat: pctFmt, area: true }).setData([{ name: "CPU", color: SLOTS[0], x: sys.t, y: sys.cpu }]);
    hwCard("ram", "Оперативная память, ГБ", sys.ram_total ? `Всего в системе ${fmtGb(sys.ram_total)} ГБ.` : "",
      { yMin: 0, tipFormat: (v) => `${v.toFixed(1)} ГБ`, area: true }).setData([{ name: "RAM", color: SLOTS[0], x: sys.t, y: sys.ram.map((v) => (v == null ? null : v / 2 ** 30)) }]);
  }

  function kv(title, rows, empty) {
    return h("div", { class: "card", style: { padding: "14px 6px 8px" } }, h("h3", { style: { padding: "0 12px 8px" } }, title),
      rows.length ? h("table", { class: "kv" }, h("tbody", null, rows.map(([k, v]) => h("tr", null, h("td", null, k), h("td", null, show(v))))))
        : h("div", { class: "muted", style: { padding: "0 12px 8px" } }, empty));
  }

  function renderParams() {
    const env = run.env || {};
    const envRows = [
      ["Компьютер", run.host], ["Python", env.python], ["Система", env.platform], ["Скрипт", env.script], ["Git-коммит", env.git],
      ["Ускоритель", env.accelerator], ["Устройства", (env.devices || []).join(", ") || null],
      ...Object.entries(env.frameworks || {}).map(([k, v]) => [k, v]),
      ["Импортировано из", env.imported_from], ["ID запуска", run.id],
    ].filter(([, v]) => v != null && v !== "");
    clear(paramsBox,
      kv("Параметры обучения", Object.entries(flatten(run.config)), "Параметры не переданы. Добавьте config={...} в mlogger.init()."),
      kv("Окружение", envRows, "Нет данных."));
  }

  async function refresh() {
    if (destroyed) return;
    const finalPass = run && run.status !== "running";
    if (finalPass && built) return;
    let fresh;
    try { fresh = await api.run(id); } catch (e) {
      if (!run) clear(head, h("div", { class: "card empty" }, h("h3", null, "Запуск не найден"), h("div", null, "Возможно, его удалили."), h("div", { class: "row" }, h("a", { class: "btn", href: "#/runs" }, "К списку запусков"))));
      throw e;
    }
    const first = !run;
    run = fresh;
    if (!built) build();
    renderHead();
    if (first) { renderTags(); renderParams(); notes.value = run.notes || ""; }
    renderHealth();
    renderTiles();
    series = (await api.metrics(id)).series;
    if (destroyed) return;
    renderCharts();
    if (first || Date.now() - lastSystem > 5000 || run.status !== "running") {
      lastSystem = Date.now();
      renderSystem(await api.runSystem(id));
    }
    if (run.status !== "running") renderParams();
  }

  return {
    refresh,
    destroy() { destroyed = true; for (const c of [...cards.values(), ...hwCards.values()]) c.destroy(); },
  };
}
