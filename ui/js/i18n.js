import en from "./lang/en.js";

const DICTS = { en };
const STORE_KEY = "mlogger-lang";

export const LANGS = [["ru", "RU", "Русский"], ["en", "EN", "English"]];

function detect() {
  try {
    const saved = localStorage.getItem(STORE_KEY);
    if (saved === "ru" || saved === "en") return saved;
  } catch {}
  return (navigator.language || "en").toLowerCase().startsWith("ru") ? "ru" : "en";
}

export const lang = detect();
export const locale = lang === "ru" ? "ru-RU" : "en-US";
document.documentElement.lang = lang;

export function t(key, args) {
  let text = lang === "ru" ? key : DICTS[lang][key] ?? key;
  if (args) text = text.replace(/\{(\d+)\}/g, (_, i) => String(args[i]));
  return text;
}

export function setLang(next) {
  if (next === lang) return;
  try { localStorage.setItem(STORE_KEY, next); } catch {}
  location.reload();
}
