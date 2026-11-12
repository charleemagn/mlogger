"""Два языка MLogger: русский и английский.

    T("Запуск", "Run")       -> {"@t": ["Запуск", "Run"]}   текст сразу на обоих языках
    pick(text, "en")         -> "Run"
    localize(obj, "en")      -> тот же объект, где каждый такой текст заменён строкой

Тексты хранятся на обоих языках, а язык выбирается в момент ответа — поэтому
переключение языка не требует ничего пересчитывать.
"""

from __future__ import annotations

import os
import sys

LANGS = ("ru", "en")
DEFAULT = "en"
_MARK = "@t"


def T(ru: str, en: str) -> dict:
    return {_MARK: [ru, en]}


def is_text(value) -> bool:
    return isinstance(value, dict) and len(value) == 1 and _MARK in value


def pick(value, lang: str):
    if not is_text(value):
        return value
    return value[_MARK][LANGS.index(lang if lang in LANGS else DEFAULT)]


def join(*parts, sep: str = "") -> dict:
    """Склеивает строки и двуязычные тексты в один двуязычный текст."""
    return T(sep.join(str(pick(p, "ru")) for p in parts), sep.join(str(pick(p, "en")) for p in parts))


def localize(obj, lang: str):
    if is_text(obj):
        return pick(obj, lang)
    if isinstance(obj, dict):
        return {k: localize(v, lang) for k, v in obj.items()}
    if isinstance(obj, list):
        return [localize(v, lang) for v in obj]
    return obj


def normalize(value) -> str:
    code = str(value or "").strip().lower().replace("_", "-")
    if code.startswith("ru"):
        return "ru"
    return "en" if code else DEFAULT


def request_lang(header) -> str:
    """Язык из заголовка Accept-Language: «ru-RU,ru;q=0.9,en;q=0.8» -> «ru»."""
    first = str(header or "").split(",")[0].split(";")[0]
    return normalize(first)


def system_lang() -> str:
    """Язык для консоли: переменная MLOGGER_LANG, иначе язык системы."""
    forced = os.environ.get("MLOGGER_LANG")
    if forced:
        return normalize(forced)
    if sys.platform == "win32":
        try:
            import ctypes
            return "ru" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x19 else "en"
        except Exception:
            return DEFAULT
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(name):
            return normalize(os.environ[name])
    return DEFAULT
