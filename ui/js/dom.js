const SVG_NS = "http://www.w3.org/2000/svg";
const SVG_TAGS = new Set(["svg", "path", "circle", "rect", "line", "polyline", "g"]);

export function h(tag, attrs, ...children) {
  const svg = SVG_TAGS.has(tag);
  const el = svg ? document.createElementNS(SVG_NS, tag) : document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "style" && typeof value === "object") {
      for (const [k, v] of Object.entries(value)) k.startsWith("--") ? el.style.setProperty(k, v) : (el.style[k] = v);
    } else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (!svg && key in el && key !== "list") {
      el[key] = value;
    } else {
      el.setAttribute(key === "className" ? "class" : key, value === true ? "" : value);
    }
  }
  if (svg && attrs && attrs.class) el.setAttribute("class", attrs.class);
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children) {
    if (child == null || child === false) continue;
    if (Array.isArray(child)) append(el, child);
    else el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

const ICONS = {
  overview: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
  runs: "M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01",
  compare: "M3 17l5-6 4 3 6-8M3 21h18M16 6h3v3",
  hardware: "M6 6h12v12H6zM9.5 9.5h5v5h-5zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4",
  connect: "M9 3v5M15 3v5M6 8h12v4a6 6 0 0 1-12 0zM12 18v3",
  sun: "M12 8a4 4 0 1 0 0 8a4 4 0 0 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z",
  ok: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM8 12.5l2.7 2.7L16 9.5",
  info: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM12 11v6M12 7.5h.01",
  warn: "M12 3.5L2.5 20h19zM12 10v4.5M12 17.5h.01",
  crit: "M8 2.5h8L21.5 8v8L16 21.5H8L2.5 16V8zM9 9l6 6M15 9l-6 6",
  check: "M5 12.5l4.5 4.5L19 7.5",
  stop: "M7 7h10v10H7z",
  trash: "M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13M10 11v6M14 11v6",
  back: "M15 5l-7 7 7 7",
  table: "M3 5h18v14H3zM3 10h18M3 15h18M9 5v14",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  plus: "M12 5v14M5 12h14",
  download: "M12 4v11M7 11l5 5 5-5M5 20h14",
  search: "M11 4a7 7 0 1 0 0 14a7 7 0 0 0 0-14zM20 20l-4-4",
  edit: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  upload: "M12 16V5M7 9l5-5 5 5M5 20h14",
  spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z",
  clock: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM12 7v5l3.5 2",
};

export function icon(name, cls = "") {
  return h("svg", { class: `icon ${cls}`, viewBox: "0 0 24 24", "aria-hidden": "true" }, h("path", { d: ICONS[name] || "" }));
}

export function fmtNum(v, digits) {
  if (v == null || Number.isNaN(v)) return "—";
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (digits != null) return v.toLocaleString("ru-RU", { maximumFractionDigits: digits });
  if (a >= 1e6) return v.toLocaleString("ru-RU", { notation: "compact", maximumFractionDigits: 2 });
  if (a >= 1000) return v.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
  if (a >= 100) return trim(v.toFixed(1));
  if (a >= 1) return trim(v.toFixed(3));
  if (a >= 0.001) return trim(v.toFixed(4));
  return v.toExponential(2).replace("e-", "e−");
}

const trim = (s) => (s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s);

export function fmtAxis(v) {
  const a = Math.abs(v);
  if (a >= 1e4) return v.toLocaleString("ru-RU", { notation: "compact", maximumFractionDigits: 1 });
  if (a >= 1 || v === 0) return trim(v.toFixed(a >= 100 ? 0 : 2));
  if (a >= 0.001) return trim(v.toFixed(4));
  return v.toExponential(1).replace("e-", "e−");
}

export function fmtDur(sec) {
  if (sec == null) return "—";
  sec = Math.max(0, Math.round(sec));
  const d = Math.floor(sec / 86400), hh = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (d) return `${d} д ${hh} ч`;
  if (hh) return `${hh} ч ${m} мин`;
  if (m) return `${m} мин ${s} с`;
  return `${s} с`;
}

export function fmtClock(sec) {
  const neg = sec < 0;
  sec = Math.abs(Math.round(sec));
  const hh = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const text = hh ? `${hh}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
  return neg ? `−${text}` : text;
}

export function fmtDate(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000), now = new Date();
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
  if (days === 0) return `сегодня, ${time}`;
  if (days === 1) return `вчера, ${time}`;
  const opts = { day: "numeric", month: "short" };
  if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
  return `${d.toLocaleDateString("ru-RU", opts)}, ${time}`;
}

export const fmtGb = (bytes) => (bytes == null ? "—" : (bytes / 2 ** 30).toFixed(1));

export function plural(n, one, few, many) {
  const a = n % 10, b = n % 100;
  if (a === 1 && b !== 11) return `${n} ${one}`;
  if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return `${n} ${few}`;
  return `${n} ${many}`;
}

const STATUS = {
  running: ["Идёт", "run", null],
  finished: ["Завершён", "", "check"],
  failed: ["Ошибка", "crit", "crit"],
  stopped: ["Остановлен", "", "stop"],
  crashed: ["Прерван", "warn", "warn"],
};

export function statusChip(status) {
  const [label, cls, ic] = STATUS[status] || [status, "", null];
  return h("span", { class: `chip ${cls}` }, ic ? icon(ic) : h("span", { class: "dot live" }), label);
}

export function verdictChip(diagnosis) {
  const v = diagnosis.verdict;
  return h("span", { class: `chip ${v.level}`, title: diagnosis.health != null ? `Индекс здоровья: ${diagnosis.health} из 100` : "" },
    icon(v.level), v.label);
}

export function healthColor(score) {
  if (score == null) return "var(--neutral)";
  return score >= 80 ? "var(--good)" : score >= 55 ? "var(--warning)" : score >= 30 ? "var(--serious)" : "var(--critical)";
}

const TAG_HUES = ["#2aa2b9", "#7d8fa3", "#9085e9", "#c98500", "#d55181", "#3987e5", "#4f9d69", "#b0705a"];

export function tagColor(tag) {
  let hash = 0;
  for (const ch of tag) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  return TAG_HUES[hash % TAG_HUES.length];
}

export function tagEl(tag, { onRemove, onClick, pressed } = {}) {
  return h("span", { class: `tag${onClick ? " pick" : ""}`, style: { "--tag": tagColor(tag) }, onclick: onClick,
    role: onClick ? "button" : null, tabIndex: onClick ? 0 : null, "aria-pressed": onClick ? String(!!pressed) : null,
    onkeydown: onClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } } : null },
    tag, onRemove ? h("button", { title: "Убрать метку", "aria-label": `Убрать метку ${tag}`, onclick: (e) => { e.stopPropagation(); onRemove(); } }, "×") : null);
}

let toasts;

export function toast(text, level = "info") {
  if (!toasts) document.body.append((toasts = h("div", { class: "toasts", role: "status" })));
  const el = h("div", { class: "toast" }, h("span", { class: `lv-${level}` }, icon(level)), h("span", null, text));
  toasts.append(el);
  setTimeout(() => el.remove(), level === "crit" ? 7000 : 3500);
}

export function ask({ title, text, fields = [], ok = "Готово", danger = false }) {
  return new Promise((resolve) => {
    const inputs = fields.map((f) => h("input", { class: "input", name: f.name, placeholder: f.placeholder || "", value: f.value || "" }));
    const form = h("form", { method: "dialog", onsubmit: (e) => { e.preventDefault(); done(Object.fromEntries(inputs.map((i) => [i.name, i.value.trim()]))); } },
      h("h3", null, title), text ? h("p", null, text) : null,
      fields.map((f, i) => h("label", { class: "field" }, h("span", null, f.label), inputs[i])),
      h("div", { class: "row" },
        h("button", { class: "btn ghost", type: "button", onclick: () => done(null) }, "Отмена"),
        h("button", { class: `btn ${danger ? "danger" : "primary"}`, type: "submit" }, ok)));
    const dialog = h("dialog", { oncancel: () => done(null) }, form);
    function done(value) { dialog.close(); dialog.remove(); resolve(value); }
    document.body.append(dialog);
    dialog.showModal();
    if (inputs[0]) inputs[0].focus();
  });
}

export function codeBlock(text) {
  const btn = h("button", { type: "button", onclick: async () => {
    try { await navigator.clipboard.writeText(text); btn.textContent = "Скопировано"; } catch { btn.textContent = "Выделите и скопируйте"; }
    setTimeout(() => (btn.textContent = "Копировать"), 1600);
  } }, "Копировать");
  return h("div", { class: "code" }, h("pre", null, text), btn);
}

export const store = {
  get(key, fallback) { try { const v = localStorage.getItem("mlogger-" + key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem("mlogger-" + key, JSON.stringify(value)); } catch {} },
};
