import { h, clear, icon, toast, fmtNum, fmtDur, plural, healthColor, codeBlock } from "../dom.js";
import { api } from "../api.js";
import { gpuHead, gpuMeters, runCard, mainMetric, importDialog, quickstartCode } from "../parts.js";
import { meter } from "../chart.js";
import { t } from "../i18n.js";

const LEVEL_COLOR = { ok: "var(--good)", info: "var(--neutral)", warn: "var(--warning)", crit: "var(--critical)" };

export function mount(root, ctx) {
  const body = h("div");
  const systemBox = h("div");
  let runsSig = "";
  const actions = h("div", { class: "actions" });
  root.append(
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, t("Обзор")), h("div", { class: "sub" }, t("Что происходит с обучением прямо сейчас и чем закончились прошлые запуски"))),
      actions),
    body);

  async function loadDemo() {
    try { await api.demo(); toast(t("Демо-запуски добавлены — один из них обучается прямо сейчас"), "ok"); runsSig = ""; await refresh(); }
    catch (e) { toast(e.message, "crit"); }
  }

  function welcome() {
    const code = quickstartCode(ctx.ping);
    return [
      h("div", { class: "card hero" },
        h("div", null,
          h("h1", null, t("Следите за обучением моделей и понимайте, что происходит")),
          h("p", null, t("MLogger собирает метрики обучения, следит за видеокартами и объясняет простыми словами, что происходит: модель учится, переобучается или пора останавливать. Всё хранится на вашем компьютере.")),
          h("div", { class: "row" },
            h("button", { class: "btn primary", onclick: loadDemo }, icon("spark"), t("Посмотреть на демо-данных")),
            h("button", { class: "btn", onclick: () => importDialog(() => refresh()) }, icon("upload"), t("Импортировать свои логи")))),
        h("img", { src: "/assets/logo.png", alt: "" })),
      h("div", { class: "section" },
        h("h2", null, t("Как подключить своё обучение")),
        h("div", { class: "card steps" },
          h("div", { class: "step" }, h("div", null, h("h3", null, t("Установите клиент в окружение, где идёт обучение")),
            h("p", null, t("Это маленький пакет без зависимостей.")), codeBlock(code.install))),
          h("div", { class: "step" }, h("div", null, h("h3", null, t("Добавьте три строки в код обучения")),
            h("p", null, t("Работает с любым фреймворком: PyTorch, TensorFlow, JAX, scikit-learn. Для Keras, Lightning, YOLO, Transformers, XGBoost и LightGBM есть готовые обёртки — см. «Подключение».")),
            codeBlock(code.basic))),
          h("div", { class: "step" }, h("div", null, h("h3", null, t("Запустите обучение")),
            h("p", null, t("Запуск появится здесь сам, графики обновляются на лету.")))))),
    ];
  }

  function ranking(runs) {
    const groups = new Map();
    for (const r of runs) {
      const m = mainMetric(r);
      if (!m || !m.info.direction) continue;
      const id = `${r.project}\u0000${m.key}`;
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push({ run: r, value: m.info.best, dir: m.info.direction, key: m.key });
    }
    const top = [...groups.values()].sort((a, b) => b.length - a.length)[0];
    if (!top || top.length < 2) return null;
    const sign = top[0].dir === "min" ? 1 : -1;
    top.sort((a, b) => sign * (a.value - b.value));
    const shown = top.slice(0, 8);
    const max = Math.max(...shown.map((t) => Math.abs(t.value))) || 1;
    return h("div", { class: "card" },
      h("h3", null, t("Рейтинг запусков по {0}", [top[0].key])),
      h("div", { class: "dim", style: { margin: "2px 0 14px" } },
        t("Проект «{0}» · {1} · лучшее значение за запуск", [top[0].run.project, top[0].dir === "min" ? t("меньше — лучше") : t("больше — лучше")])),
      h("div", { class: "bars" }, shown.map((t, i) => [
        h("a", { class: "name", href: `#/run/${t.run.id}`, title: t.run.name }, t.run.name),
        h("div", { class: "track" },
          h("i", { class: i === 0 ? "best" : "rest", style: { width: `${Math.max(1, (Math.abs(t.value) / max) * 86)}%` } }),
          h("span", null, fmtNum(t.value))),
      ])));
  }

  function verdictCard(ov) {
    const total = ov.verdicts.reduce((a, v) => a + v.count, 0) || 1;
    const levels = ["ok", "info", "warn", "crit"].map((level) => ({ level, count: ov.verdicts.filter((v) => v.level === level).reduce((a, v) => a + v.count, 0) })).filter((l) => l.count);
    const sorted = [...ov.verdicts].sort((a, b) => ["ok", "info", "warn", "crit"].indexOf(a.level) - ["ok", "info", "warn", "crit"].indexOf(b.level));
    return h("div", { class: "card" },
      h("h3", null, t("Чем закончились запуски")),
      h("div", { class: "dim", style: { margin: "2px 0 14px" } }, t("Автоматический диагноз по форме кривых обучения")),
      h("div", { class: "segbar", role: "img", "aria-label": sorted.map((v) => `${v.label}: ${v.count}`).join(", ") },
        levels.map((l) => h("i", { style: { width: `${(l.count / total) * 100}%`, background: LEVEL_COLOR[l.level] } }))),
      h("div", { class: "legend", style: { marginTop: "12px" } }, sorted.map((v) =>
        h("span", { class: "key" }, h("span", { class: `lv-${v.level}`, style: { display: "inline-flex" } }, icon(v.level, "sm")), v.label, h("b", null, String(v.count))))));
  }

  function insightsCard(ov) {
    return h("div", { class: "card" },
      h("h3", { style: { marginBottom: "12px" } }, t("Выводы")),
      ov.insights.length
        ? h("div", { class: "insights" }, ov.insights.map((i) => h("div", { class: "insight" },
          h("span", { class: `lv-${i.level}` }, icon(i.level)), h("p", null, i.text),
          i.run ? h("a", { href: `#/run/${i.run}` }, t("Открыть")) : h("span"))))
        : h("div", { class: "muted" }, t("Выводы появятся, когда накопится несколько точек метрик.")));
  }

  function renderRuns(ov, runs) {
    const demo = runs.some((r) => r.source === "demo");
    clear(actions,
      demo ? h("button", { class: "btn ghost", onclick: async () => { await api.deleteDemo(); toast(t("Демо-данные удалены"), "ok"); runsSig = ""; refresh(); } }, icon("trash", "sm"), t("Убрать демо-данные")) : null,
      h("button", { class: "btn", onclick: () => importDialog(() => { runsSig = ""; refresh(); }) }, icon("upload", "sm"), t("Импорт логов")));
    if (!runs.length) return clear(body, welcome());

    const live = runs.filter((r) => r.status === "running");
    const recent = [...live, ...runs.filter((r) => r.status !== "running")].slice(0, Math.max(5, live.length));
    clear(body,
      h("div", { class: "grid tiles" },
        tile(t("Сейчас обучается"), String(ov.running), ov.running ? t("графики обновляются на лету") : t("активных запусков нет"), ov.running ? h("span", { class: "dot live" }) : null),
        tile(t("Всего запусков"), String(ov.total), plural(ov.projects.length, t("проект"), t("проекта"), t("проектов"))),
        tile(t("Время обучения"), fmtDur(ov.train_seconds), t("суммарно по всем запускам")),
        healthTile(ov.health_avg)),
      h("div", { class: "grid split", style: { marginTop: "14px" } }, insightsCard(ov), h("div", { class: "grid" }, verdictCard(ov), systemBox)),
      h("div", { class: "section" },
        h("div", { class: "row" }, h("h2", null, live.length ? t("Идут сейчас и последние") : t("Последние запуски")), h("span", { class: "spacer" }),
          h("a", { class: "btn ghost sm", href: "#/runs" }, t("Все запуски"))),
        h("div", { class: "card", style: { marginTop: "12px" } }, recent.map(runCard))),
      h("div", { class: "section" }, ranking(runs)));
  }

  function tile(label, value, note, mark) {
    return h("div", { class: "card tile" }, h("div", { class: "label" }, mark, label), h("div", { class: "value" }, value), h("div", { class: "note" }, note));
  }

  function healthTile(avg) {
    const score = avg == null ? null : Math.round(avg);
    return h("div", { class: "card tile" },
      h("div", { class: "label" }, t("Средний индекс здоровья")),
      h("div", { class: "value" }, score == null ? "—" : String(score), h("small", null, t("из 100"))),
      h("div", { class: "progress", style: { margin: "6px 0 4px", background: `color-mix(in srgb, ${healthColor(score)} 20%, transparent)` } },
        h("i", { style: { width: `${score || 0}%`, background: healthColor(score) } })),
      h("div", { class: "note" }, t("100 — обучение без замечаний")));
  }

  function renderSystem(sys) {
    const host = sys.hosts[0];
    if (!host) {
      return clear(systemBox, h("div", { class: "card" }, h("h3", null, t("Железо сейчас")),
        h("div", { class: "muted", style: { marginTop: "8px" } }, t("Монитор ещё собирает первые показания…"))));
    }
    const s = host.latest;
    clear(systemBox, h("div", { class: "card" },
      h("div", { class: "row", style: { marginBottom: "12px" } }, h("h3", null, t("Железо сейчас")), h("span", { class: "muted" }, host.host),
        h("span", { class: "spacer" }), h("a", { class: "btn ghost sm", href: "#/hardware" }, t("Подробнее"))),
      h("div", { class: "stack" },
        s.gpus.length ? s.gpus.map((g) => h("div", null, gpuHead(g), gpuMeters(g, { compact: true }))) : h("div", { class: "muted" }, t("Видеокарты не обнаружены.")),
        h("div", { class: "stack", style: { borderTop: "1px solid var(--border)", paddingTop: "10px" } },
          meter(t("Процессор"), s.cpu == null ? null : s.cpu / 100, s.cpu == null ? "—" : `${Math.round(s.cpu)}%`),
          meter(t("Память"), s.ram_total ? s.ram_used / s.ram_total : null, s.ram_total ? t("{0} / {1} ГБ", [(s.ram_used / 2 ** 30).toFixed(1), (s.ram_total / 2 ** 30).toFixed(1)]) : "—", { warnAt: 90, critAt: 96 })))));
  }

  async function refresh() {
    const [ov, list, sys] = await Promise.all([api.overview(), api.runs(), api.system()]);
    ctx.setRunning(ov.running);
    const sig = JSON.stringify([ov.total, ov.running, ov.insights, ov.verdicts, Math.round(ov.train_seconds / 30),
      list.runs.map((r) => [r.id, r.status, r.name, r.tags, r.summary.max_step, r.summary.diagnosis.verdict.code])]);
    if (sig !== runsSig) { runsSig = sig; renderRuns(ov, list.runs); }
    renderSystem(sys);
  }

  return { refresh };
}
