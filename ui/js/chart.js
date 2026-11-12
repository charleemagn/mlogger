import { h, clear, icon, fmtNum, fmtAxis, healthColor } from "./dom.js";
import { locale, t } from "./i18n.js";

const bus = new EventTarget();
export const SLOTS = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];

function niceStep(raw) {
  const mag = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw * (1 - 1e-9));
}

const TIME_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];

function niceTicks(min, max, count, time = false) {
  if (!(max > min)) return { ticks: [min], step: 0 };
  const raw = (max - min) / count;
  const step = (time && TIME_STEPS.find((s) => s >= raw)) || niceStep(raw);
  const ticks = [];
  for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + step * 1e-9; v += step) ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return { ticks, step };
}

function tickLabels(ticks, step) {
  const top = Math.max(...ticks.map(Math.abs));
  if (top >= 1e4) return ticks.map((t) => t.toLocaleString(locale, { notation: "compact", maximumFractionDigits: 1 }));
  const digits = step > 0 ? Math.max(0, Math.ceil(-Math.log10(step) - 1e-9) + (/^2\.5/.test(step.toExponential(2)) ? 1 : 0)) : 2;
  if (digits > 5) return ticks.map((t) => (t === 0 ? "0" : t.toExponential(1).replace("e-", "e−")));
  return ticks.map((t) => t.toFixed(digits));
}

function nearest(xs, x) {
  let lo = 0, hi = xs.length - 1;
  if (hi < 0) return -1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] < x) lo = mid; else hi = mid;
  }
  return Math.abs(xs[lo] - x) <= Math.abs(xs[hi] - x) ? lo : hi;
}

export function smooth(values, weight) {
  if (!weight) return values;
  let acc = 0, n = 0;
  return values.map((v) => {
    if (v == null) return null;
    acc = acc * weight + (1 - weight) * v;
    n += 1;
    return acc / (1 - weight ** n);
  });
}

export class LineChart {
  constructor(host, opts = {}) {
    this.host = host;
    this.opts = { height: 220, xFormat: fmtAxis, timeAxis: false, tipFormat: fmtNum, xTitle: t("шаг"), smooth: 0, log: false, ...opts };
    this.series = [];
    this.hoverX = null;
    this.showTip = false;
    this.canvas = h("canvas", { tabIndex: 0, role: "img" });
    this.tip = h("div", { class: "chart-tip", hidden: true });
    host.classList.add("chart");
    host.append(this.canvas, this.tip);

    this.canvas.addEventListener("pointermove", (e) => this._pointer(e));
    this.canvas.addEventListener("pointerleave", () => this._leave());
    this.canvas.addEventListener("blur", () => this._leave());
    this.canvas.addEventListener("keydown", (e) => this._key(e));
    this._onSync = (e) => {
      if (e.detail.source === this || e.detail.group !== this.opts.sync) return;
      this.hoverX = e.detail.x;
      this.showTip = false;
      this.tip.hidden = true;
      this.schedule();
    };
    this._onTheme = () => this.schedule();
    bus.addEventListener("hover", this._onSync);
    window.addEventListener("themechange", this._onTheme);
    this.observer = new ResizeObserver(() => this.schedule());
    this.observer.observe(host);
  }

  destroy() {
    this.observer.disconnect();
    bus.removeEventListener("hover", this._onSync);
    window.removeEventListener("themechange", this._onTheme);
  }

  setData(series) {
    this.series = series.map((s) => ({ ...s, shown: smooth(s.y, this.opts.smooth) }));
    this.canvas.setAttribute("aria-label", t("График: ") + series.map((s) => s.name).join(", "));
    this.schedule();
  }

  set(opts) {
    Object.assign(this.opts, opts);
    this.setData(this.series);
  }

  schedule() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this.draw(); });
  }

  _domain() {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const s of this.series) {
      for (let i = 0; i < s.x.length; i++) {
        const y = s.shown[i];
        if (y == null) continue;
        if (s.x[i] < x0) x0 = s.x[i];
        if (s.x[i] > x1) x1 = s.x[i];
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
    if (x0 === Infinity) return null;
    if (this.opts.smooth) {
      for (const s of this.series) {
        const raw = s.y.filter((v) => v != null).sort((a, b) => a - b);
        if (!raw.length) continue;
        const cut = raw.length > 50 ? Math.floor(raw.length * 0.02) : 0;
        y0 = Math.min(y0, raw[cut]);
        y1 = Math.max(y1, raw[raw.length - 1 - cut]);
      }
    }
    const log = this.opts.log && y0 > 0;
    if (log) { y0 = Math.log10(y0); y1 = Math.log10(y1); }
    if (y1 - y0 <= 1e-9 * Math.max(Math.abs(y0), Math.abs(y1))) {
      const pad = Math.abs(y0) * 0.1 || 1;
      y0 -= pad; y1 += pad;
    }
    const pad = (y1 - y0) * 0.06;
    y0 -= pad; y1 += pad;
    if (!log) {
      if (this.opts.yMin != null) y0 = this.opts.yMin;
      if (this.opts.yMax != null) y1 = Math.max(this.opts.yMax, y0 + 1e-9);
    }
    if (x0 === x1) { x0 -= 1; x1 += 1; }
    return { x0, x1, y0, y1, log };
  }

  draw() {
    const { host, canvas, opts } = this;
    const width = host.clientWidth, height = opts.height;
    if (!width) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.height = height + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(host);
    const color = (name) => css.getPropertyValue(name).trim();
    const font = `12px ${css.fontFamily}`;
    ctx.font = font;
    ctx.clearRect(0, 0, width, height);

    const d = this._domain();
    this.geom = null;
    if (!d) {
      ctx.fillStyle = color("--muted");
      ctx.textAlign = "center";
      ctx.fillText(t("Пока нет данных"), width / 2, height / 2);
      return;
    }
    const yScale = niceTicks(d.y0, d.y1, 4);
    const yText = d.log ? yScale.ticks.map((t) => fmtAxis(10 ** t)) : tickLabels(yScale.ticks, yScale.step);
    const yTicks = yScale.ticks.map((t, i) => ({ pos: t, label: yText[i] }));
    const left = Math.ceil(Math.max(...yTicks.map((t) => ctx.measureText(t.label).width), 12)) + 12;
    const plot = { l: left, t: 10, r: width - 14, b: height - 26 };
    const sx = (x) => plot.l + ((x - d.x0) / (d.x1 - d.x0)) * (plot.r - plot.l);
    const sy = (y) => plot.b - (((d.log ? Math.log10(y) : y) - d.y0) / (d.y1 - d.y0)) * (plot.b - plot.t);
    const syTick = (t) => plot.b - ((t - d.y0) / (d.y1 - d.y0)) * (plot.b - plot.t);
    this.geom = { plot, d, sx };

    ctx.lineWidth = 1;
    ctx.strokeStyle = color("--grid");
    ctx.fillStyle = color("--muted");
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const t of yTicks) {
      const y = Math.round(syTick(t.pos)) + 0.5;
      if (y < plot.t - 1 || y > plot.b + 1) continue;
      ctx.beginPath(); ctx.moveTo(plot.l, y); ctx.lineTo(plot.r, y); ctx.stroke();
      ctx.fillText(t.label, plot.l - 8, y);
    }
    ctx.strokeStyle = color("--axis");
    ctx.beginPath(); ctx.moveTo(plot.l, plot.b + 0.5); ctx.lineTo(plot.r, plot.b + 0.5); ctx.stroke();
    ctx.textBaseline = "top";
    ctx.textAlign = "center";
    const xTicks = niceTicks(d.x0, d.x1, Math.max(2, Math.floor((plot.r - plot.l) / 90)), opts.timeAxis).ticks;
    for (const t of xTicks) {
      const x = sx(t);
      const label = opts.xFormat(t);
      const half = ctx.measureText(label).width / 2;
      ctx.fillText(label, Math.min(Math.max(x, plot.l + half), plot.r - half), plot.b + 7);
    }

    ctx.save();
    ctx.beginPath(); ctx.rect(plot.l, plot.t - 4, plot.r - plot.l + 6, plot.b - plot.t + 5); ctx.clip();
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    const path = (s, ys) => {
      ctx.beginPath();
      let pen = false;
      for (let i = 0; i < s.x.length; i++) {
        const y = ys[i];
        if (y == null || (d.log && y <= 0)) { pen = false; continue; }
        pen ? ctx.lineTo(sx(s.x[i]), sy(y)) : ctx.moveTo(sx(s.x[i]), sy(y));
        pen = true;
      }
    };
    for (const s of this.series) {
      const c = color(s.color);
      if (opts.smooth) {
        ctx.globalAlpha = 0.22; ctx.lineWidth = 1; ctx.strokeStyle = c;
        path(s, s.y); ctx.stroke();
        ctx.globalAlpha = 1;
      }
      if (opts.area && this.series.length === 1) {
        path(s, s.shown);
        const last = lastIndex(s.shown), first = s.shown.findIndex((v) => v != null);
        if (last >= 0) {
          ctx.lineTo(sx(s.x[last]), plot.b); ctx.lineTo(sx(s.x[first]), plot.b); ctx.closePath();
          ctx.globalAlpha = 0.1; ctx.fillStyle = c; ctx.fill(); ctx.globalAlpha = 1;
        }
      }
      ctx.lineWidth = 2; ctx.strokeStyle = c;
      path(s, s.shown); ctx.stroke();
    }
    ctx.restore();

    const surface = color("--surface");
    const dot = (x, y, c) => {
      ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.fillStyle = surface; ctx.fill();
      ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fillStyle = c; ctx.fill();
    };
    if (this.hoverX == null && this.series.length <= 4) {
      for (const s of this.series) {
        const i = lastIndex(s.shown);
        if (i >= 0 && !(d.log && s.shown[i] <= 0)) dot(sx(s.x[i]), sy(s.shown[i]), color(s.color));
      }
    }
    if (this.hoverX != null && this.hoverX >= d.x0 && this.hoverX <= d.x1) {
      const x = Math.round(sx(this.hoverX)) + 0.5;
      ctx.strokeStyle = color("--axis"); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, plot.t); ctx.lineTo(x, plot.b); ctx.stroke();
      for (const s of this.series) {
        const i = nearestReal(s, this.hoverX);
        if (i >= 0 && !(d.log && s.shown[i] <= 0)) dot(sx(s.x[i]), sy(s.shown[i]), color(s.color));
      }
      if (this.showTip) this._tooltip(x, color);
    }
  }

  _tooltip(px, color) {
    const { tip, opts } = this;
    clear(tip, h("div", { class: "x" }, `${opts.xTitle} ${opts.xFormat(this.hoverX)}`));
    for (const s of this.series) {
      const i = nearestReal(s, this.hoverX);
      if (i < 0) continue;
      tip.append(h("div", { class: "r" },
        h("i", { class: "linekey", style: { background: color(s.color) } }),
        h("b", null, opts.tipFormat(s.y[i])), h("span", null, s.name)));
    }
    tip.hidden = false;
    const w = tip.offsetWidth, hostW = this.host.clientWidth;
    tip.style.left = (px + 14 + w > hostW ? Math.max(0, px - 14 - w) : px + 14) + "px";
    tip.style.top = "8px";
  }

  _setHover(x, tip) {
    this.hoverX = x;
    this.showTip = tip;
    if (!tip) this.tip.hidden = true;
    bus.dispatchEvent(new CustomEvent("hover", { detail: { source: this, group: this.opts.sync, x } }));
    this.schedule();
  }

  _pointer(e) {
    if (!this.geom) return;
    const { plot, d } = this.geom;
    const px = e.clientX - this.canvas.getBoundingClientRect().left;
    const want = d.x0 + ((px - plot.l) / (plot.r - plot.l)) * (d.x1 - d.x0);
    let best = null;
    for (const s of this.series) {
      const i = nearest(s.x, want);
      if (i >= 0 && (best == null || Math.abs(s.x[i] - want) < Math.abs(best - want))) best = s.x[i];
    }
    if (best != null) this._setHover(best, true);
  }

  _leave() {
    if (this.hoverX != null) this._setHover(null, false);
  }

  _key(e) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const xs = [...new Set(this.series.flatMap((s) => s.x))].sort((a, b) => a - b);
    if (!xs.length) return;
    e.preventDefault();
    const at = this.hoverX == null ? xs.length - 1 : nearest(xs, this.hoverX) + (e.key === "ArrowRight" ? 1 : -1);
    this._setHover(xs[Math.min(xs.length - 1, Math.max(0, at))], true);
  }
}

function lastIndex(values) {
  for (let i = values.length - 1; i >= 0; i--) if (values[i] != null) return i;
  return -1;
}

function nearestReal(s, x) {
  let i = nearest(s.x, x);
  if (i < 0) return -1;
  if (s.shown[i] != null) return i;
  for (let k = 1; k < 4; k++) {
    if (s.shown[i - k] != null) return i - k;
    if (s.shown[i + k] != null) return i + k;
  }
  return -1;
}

export class ChartCard {
  constructor({ title, what, chart = {} }) {
    this.legend = h("div", { class: "legend" });
    this.last = h("div", { class: "last" });
    this.plot = h("div");
    this.tableWrap = h("div", { class: "table-wrap", hidden: true });
    this.toggle = h("button", { class: "btn ghost sm", type: "button", "aria-pressed": "false", title: t("Показать данные таблицей"),
      onclick: () => this._toggleTable() }, icon("table", "sm"), t("Таблица"));
    this.el = h("div", { class: "card chart-card" },
      h("div", { class: "chart-head" },
        h("div", null, h("h3", null, title), what ? h("div", { class: "what" }, what) : null),
        this.last, this.toggle),
      this.legend, this.plot, this.tableWrap);
    this.chart = new LineChart(this.plot, chart);
    this.series = [];
  }

  setData(series) {
    this.series = series;
    this.chart.setData(series);
    const fmt = this.chart.opts.tipFormat;
    const lastOf = (s) => { const i = lastIndex(s.y); return i >= 0 ? fmt(s.y[i]) : "—"; };
    if (series.length === 1) {
      this.legend.hidden = true;
      this.last.textContent = lastOf(series[0]);
    } else {
      this.last.textContent = "";
      this.legend.hidden = false;
      clear(this.legend, series.map((s) => h("span", { class: "key" },
        h("i", { class: "linekey", style: { background: `var(${s.color})` } }), s.name, h("b", null, lastOf(s)))));
    }
    if (!this.tableWrap.hidden) this._renderTable();
  }

  _toggleTable() {
    this.tableWrap.hidden = !this.tableWrap.hidden;
    this.toggle.setAttribute("aria-pressed", String(!this.tableWrap.hidden));
    if (!this.tableWrap.hidden) this._renderTable();
  }

  _renderTable() {
    const { xTitle, xFormat, tipFormat } = this.chart.opts;
    const rows = new Map();
    this.series.forEach((s, col) => s.x.forEach((x, i) => {
      if (!rows.has(x)) rows.set(x, []);
      rows.get(x)[col] = s.y[i];
    }));
    const xs = [...rows.keys()].sort((a, b) => a - b);
    const shown = xs.length > 400 ? xs.filter((_, i) => i % Math.ceil(xs.length / 400) === 0 || i === xs.length - 1) : xs;
    clear(this.tableWrap, h("table", { class: "small-table" },
      h("thead", null, h("tr", null, h("th", null, xTitle), this.series.map((s) => h("th", { class: "n" }, s.name)))),
      h("tbody", null, shown.map((x) => h("tr", null, h("td", null, xFormat(x)),
        this.series.map((_, col) => h("td", { class: "n" }, rows.get(x)[col] == null ? "—" : tipFormat(rows.get(x)[col]))))))));
  }

  destroy() { this.chart.destroy(); }
}

export function sparkline(values, { quiet = false, height = 34 } = {}) {
  const vals = (values || []).filter((v) => v != null);
  const svg = h("svg", { class: `spark${quiet ? " quiet" : ""}`, viewBox: `0 0 100 ${height}`, preserveAspectRatio: "none", "aria-hidden": "true" });
  svg.style.height = height + "px";
  if (vals.length < 2) return svg;
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const d = vals.map((v, i) => `${i ? "L" : "M"}${((i / (vals.length - 1)) * 100).toFixed(2)} ${(height - 3 - ((v - min) / span) * (height - 6)).toFixed(2)}`).join("");
  svg.append(h("path", { d }));
  return svg;
}

export function healthRing(score) {
  const r = 42, len = 2 * Math.PI * r;
  const part = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  return h("div", { class: "ring", style: { "--c": healthColor(score) }, role: "img",
    "aria-label": score == null ? t("Индекс здоровья пока не посчитан") : t("Индекс здоровья {0} из 100", [score]) },
    h("svg", { viewBox: "0 0 100 100" },
      h("circle", { class: "track", cx: 50, cy: 50, r }),
      h("circle", { class: "fill", cx: 50, cy: 50, r, "stroke-dasharray": len, "stroke-dashoffset": len * (1 - part) })),
    h("div", { class: "center" }, h("b", null, score == null ? "—" : String(score)), h("span", null, t("из 100"))));
}

export function meter(name, part, text, { warnAt = null, critAt = null } = {}) {
  const pct = part == null ? 0 : Math.max(0, Math.min(1, part)) * 100;
  const c = critAt != null && pct >= critAt ? "var(--critical)" : warnAt != null && pct >= warnAt ? "var(--warning)" : "var(--accent)";
  return h("div", { class: "meter", style: { "--c": c } },
    h("span", { class: "name" }, name), h("div", { class: "bar" }, h("i", { style: { width: pct + "%" } })), h("span", { class: "val" }, text));
}
