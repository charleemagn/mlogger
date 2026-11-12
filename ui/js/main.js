import { h, clear, icon, toast } from "./dom.js";
import { api } from "./api.js";
import * as overview from "./views/overview.js";
import * as runs from "./views/runs.js";
import * as run from "./views/run.js";
import * as compare from "./views/compare.js";
import * as hardware from "./views/hardware.js";
import * as connect from "./views/connect.js";

const REFRESH_MS = 2500;
const ROUTES = [
  [/^\/?$/, overview, "overview"],
  [/^\/runs$/, runs, "runs"],
  [/^\/run\/([\w-]+)$/, run, "runs"],
  [/^\/compare$/, compare, "compare"],
  [/^\/hardware$/, hardware, "hardware"],
  [/^\/connect$/, connect, "connect"],
];
const NAV = [
  ["overview", "#/", "Обзор"],
  ["runs", "#/runs", "Запуски"],
  ["compare", "#/compare", "Сравнение"],
  ["hardware", "#/hardware", "Железо"],
  ["connect", "#/connect", "Подключение"],
];

const main = h("main", { class: "main" });
const links = {};
const runningBadge = h("span", { class: "count", hidden: true });
const connDot = h("span", { class: "dot on" });
const connText = h("span", null, "Сервер на связи");
const themeBtn = h("button", { type: "button", onclick: toggleTheme });

function isDark() {
  const forced = document.documentElement.dataset.theme;
  return forced ? forced === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}

function paintThemeButton() {
  clear(themeBtn, icon(isDark() ? "sun" : "moon"), h("span", null, isDark() ? "Светлая тема" : "Тёмная тема"));
}

function toggleTheme() {
  const next = isDark() ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("mlogger-theme", next); } catch {}
  paintThemeButton();
  window.dispatchEvent(new Event("themechange"));
}

document.getElementById("app").append(h("div", { class: "shell" },
  h("aside", { class: "side" },
    h("a", { class: "brand", href: "#/", title: "MLogger" }, h("img", { src: "/assets/logo.png", alt: "MLogger" })),
    h("nav", { class: "nav" }, NAV.map(([key, href, label]) =>
      (links[key] = h("a", { href }, icon(key), h("span", { class: "label" }, label), key === "runs" ? runningBadge : null)))),
    h("div", { class: "side-foot" },
      h("div", { class: "conn" }, connDot, connText),
      themeBtn)),
  main));
paintThemeButton();

function setOnline(online) {
  connDot.className = `dot ${online ? "on" : "off"}`;
  connText.textContent = online ? "Сервер на связи" : "Нет связи с сервером";
}

const ctx = {
  navigate(hash) { location.hash = hash; },
  ping: null,
  setRunning(n) {
    runningBadge.hidden = !n;
    runningBadge.textContent = String(n);
    runningBadge.title = `Сейчас обучается: ${n}`;
  },
};

let view = null;
let busy = false;
let failures = 0;

async function refresh() {
  if (!view || !view.refresh || busy || document.hidden) return;
  busy = true;
  const current = view;
  try {
    await current.refresh();
    failures = 0;
    setOnline(true);
  } catch (e) {
    if (view === current && ++failures === 1) toast(e.message, "crit");
    setOnline(!/не отвечает/.test(e.message));
  } finally {
    busy = false;
  }
}

function route() {
  const [path, query = ""] = (location.hash.slice(1) || "/").split("?");
  if (view && view.destroy) view.destroy();
  view = null;
  clear(main);
  window.scrollTo(0, 0);
  for (const [pattern, module, navKey] of ROUTES) {
    const m = pattern.exec(path);
    if (!m) continue;
    for (const [key, link] of Object.entries(links)) link.classList.toggle("active", key === navKey);
    view = module.mount(main, { ...ctx, params: m.slice(1), query: new URLSearchParams(query) });
    busy = false;
    failures = 0;
    refresh();
    return;
  }
  clear(main, h("div", { class: "card empty" }, h("h3", null, "Такой страницы нет"), h("a", { class: "btn", href: "#/" }, "На обзор")));
}

window.addEventListener("hashchange", route);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
setInterval(refresh, REFRESH_MS);
api.ping().then((p) => { ctx.ping = p; }).catch(() => setOnline(false)).finally(route);
