import { h, clear, fmtClock, fmtGb, codeBlock } from "../dom.js";
import { api } from "../api.js";
import { LineChart, SLOTS, meter } from "../chart.js";
import { gpuHead, gpuMeters, emptyIcon } from "../parts.js";
import { t } from "../i18n.js";

export function mount(root, ctx) {
  const box = h("div");
  const hosts = new Map();
  let destroyed = false;
  root.append(
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, t("Железо")), h("div", { class: "sub" }, t("Видеокарты, процессор и память — показания обновляются каждые две секунды")))),
    box,
    h("div", { class: "section" },
      h("h2", null, t("Обучение идёт на другом компьютере?")),
      h("div", { class: "lead" }, t("Запустите на нём монитор из папки MLogger — показания появятся здесь и привяжутся к запускам с той машины. Сервер при этом должен быть запущен с параметром --host 0.0.0.0.")),
      codeBlock(`python -m monitor --server http://${ctx.ping && ctx.ping.host ? ctx.ping.host : t("адрес-этого-компьютера")}:${location.port || 8765}`)));

  const chartOpts = (extra) => ({ height: 120, timeAxis: true, xTitle: "", xFormat: (sec) => (sec === 0 ? t("сейчас") : fmtClock(sec)), area: true, sync: "hardware", ...extra });

  function hostBlock(host) {
    const system = h("div", { class: "card stack" });
    const grid = h("div", { class: "grid two", style: { marginTop: "14px" } });
    const title = h("div", { class: "row" });
    const el = h("div", { class: "section" }, title, h("div", { style: { marginTop: "12px" } }, system), grid);
    box.append(el);
    return { el, title, system, grid, gpus: new Map() };
  }

  function gpuBlock(block, g) {
    const meters = h("div");
    const utilHost = h("div"), memHost = h("div");
    block.grid.append(h("div", { class: "card" }, gpuHead(g), meters,
      h("div", { class: "muted", style: { margin: "14px 0 2px", fontSize: "12.5px" } }, t("Загрузка за последние 15 минут, %")), utilHost,
      h("div", { class: "muted", style: { margin: "10px 0 2px", fontSize: "12.5px" } }, t("Занятая память, ГБ")), memHost));
    return {
      meters,
      util: new LineChart(utilHost, chartOpts({ yMin: 0, yMax: 100, tipFormat: (v) => `${Math.round(v)}%` })),
      mem: new LineChart(memHost, chartOpts({ yMin: 0, yMax: g.mem_total ? g.mem_total / 2 ** 30 : null, tipFormat: (v) => t("{0} ГБ", [v.toFixed(1)]) })),
    };
  }

  function render(data) {
    if (!data.hosts.length) {
      if (!hosts.size) {
        clear(box, h("div", { class: "card empty" }, emptyIcon("hardware"), h("h3", null, t("Показаний пока нет")),
          h("div", null, data.errors && data.errors.length ? t("Монитор не смог запуститься: {0}", [data.errors.join("; ")]) : t("Монитор собирает первые данные — подождите пару секунд."))));
      }
      return;
    }
    if (!hosts.size) clear(box);
    for (const host of data.hosts) {
      if (!hosts.has(host.host)) hosts.set(host.host, hostBlock(host));
      const block = hosts.get(host.host), s = host.latest, info = host.info || {};
      clear(block.title, h("h2", null, host.host), h("span", { class: `dot ${host.online ? "on" : "off"}` }),
        h("span", { class: "dim" }, [host.online ? t("на связи") : t("нет свежих данных"), info.os, info.cpu].filter(Boolean).join(" · ")));
      clear(block.system,
        meter(t("Процессор"), s.cpu == null ? null : s.cpu / 100, s.cpu == null ? "—" : `${Math.round(s.cpu)}%`),
        meter(t("Память"), s.ram_total ? s.ram_used / s.ram_total : null, s.ram_total ? t("{0} / {1} ГБ", [fmtGb(s.ram_used), fmtGb(s.ram_total)]) : "—", { warnAt: 90, critAt: 96 }),
        s.gpus.length ? null : h("div", { class: "muted" }, t("Видеокарты на этой машине не обнаружены. Поддерживаются NVIDIA (nvidia-smi), а в Windows — любые карты, которые видит Диспетчер задач.")));
      for (const g of s.gpus) {
        const id = g.id || g.name;
        if (!block.gpus.has(id)) block.gpus.set(id, gpuBlock(block, g));
        const view = block.gpus.get(id);
        clear(view.meters, gpuMeters(g));
        const hist = host.history.gpus.find((x) => x.id === id);
        if (!hist) continue;
        view.util.setData([{ name: t("Загрузка"), color: SLOTS[0], x: host.history.t, y: hist.util }]);
        view.mem.setData([{ name: t("Память"), color: SLOTS[0], x: host.history.t, y: hist.mem.map((v) => (v == null ? null : v / 2 ** 30)) }]);
      }
    }
  }

  return {
    async refresh() {
      const data = await api.system();
      if (!destroyed) render(data);
    },
    destroy() {
      destroyed = true;
      for (const block of hosts.values()) for (const g of block.gpus.values()) { g.util.destroy(); g.mem.destroy(); }
    },
  };
}
