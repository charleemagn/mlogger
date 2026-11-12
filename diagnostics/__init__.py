"""Диагноз обучения человеческим языком.

    from diagnostics import analyze
    result = analyze(series, metas, status="running")

series: {ключ: [(step, value | None), ...]}  — None означает NaN/Inf
metas:  {ключ: describe(ключ)}               — см. glossary.py

Результат:
    {"health": 0..100 | None,
     "verdict": {"code": "overfit", "label": "Переобучение", "level": "warn"},
     "findings": [{"level", "code", "title", "text", "key", "step"}, ...]}

Все правила — эвристики по форме кривых. Они подсказывают, куда посмотреть,
а не заменяют взгляд на графики.
"""

from __future__ import annotations

import math

from .glossary import describe, pick_main

__all__ = ["analyze", "describe", "pick_main"]

_PENALTY = {"crit": 45, "warn": 20, "info": 5, "ok": 0}
_HW_PENALTY = {"crit": 15, "warn": 10, "info": 3, "ok": 0}
_ORDER = {"crit": 0, "warn": 1, "info": 2, "ok": 3}

_LABELS = {
    "nan": "Развалилось (NaN)", "failed": "Ошибка", "diverge": "Расходится", "stuck": "Не учится",
    "overfit": "Переобучение", "crashed": "Прервано", "plateau": "Плато", "noisy": "Нестабильно",
    "early": "Мало данных", "improving": "Учится", "done": "Прошло хорошо", "converged": "Сошлось",
    "unknown": "Нет оценки",
}


def _fmt(v: float) -> str:
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 100:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.3f}".rstrip("0").rstrip(".")
    if a >= 0.001:
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return f"{v:.2e}"


def _smooth(values: list, window: int | None = None) -> list:
    """Скользящее среднее по предыдущим точкам."""
    n = len(values)
    w = window or max(1, min(25, n // 15))
    if w <= 1:
        return list(values)
    out, acc = [], 0.0
    for i, v in enumerate(values):
        acc += v
        if i >= w:
            acc -= values[i - w]
        out.append(acc / min(i + 1, w))
    return out


def _nearest(steps: list, step: int) -> int:
    return min(range(len(steps)), key=lambda i: abs(steps[i] - step))


def _loss_pair(clean: dict, metas: dict):
    """Пара (train loss, val loss) одной группы; если пары нет — самый длинный train loss."""
    groups: dict = {}
    for key, pts in clean.items():
        m = metas[key]
        if m["kind"] != "loss" or len(pts) < 2:
            continue
        split = "val" if m["split"] in ("val", "test") else "train"
        slot = groups.setdefault(m["group"], {})
        if split not in slot or len(pts) > len(clean[slot[split]]):
            slot[split] = key
    paired = {g: s for g, s in groups.items() if len(s) == 2}
    if paired:
        g = "loss" if "loss" in paired else max(paired, key=lambda g: (len(clean[paired[g]["val"]]), g))
        return paired[g]["train"], paired[g]["val"]
    trains = [s["train"] for s in groups.values() if "train" in s]
    if trains:
        return max(trains, key=lambda k: len(clean[k])), None
    vals = [s["val"] for s in groups.values() if "val" in s]
    return (None, max(vals, key=lambda k: len(clean[k]))) if vals else (None, None)


def analyze(series: dict, metas: dict | None = None, *, status: str = "running", error: str | None = None,
            hw: dict | None = None, main_key: str | None = None) -> dict:
    metas = metas or {k: describe(k) for k in series}
    findings: list = []

    def add(level, code, title, text, key=None, step=None, hardware=False):
        findings.append({"level": level, "code": code, "title": title, "text": text,
                         "key": key, "step": step, "hardware": hardware})

    clean = {k: [(s, v) for s, v in pts if v is not None] for k, pts in series.items()}
    judged = [k for k in clean if metas[k]["kind"] in ("loss", "score")]
    enough = max((len(clean[k]) for k in judged), default=0) >= 10

    if status == "failed":
        add("crit", "failed", "Запуск завершился с ошибкой",
            (error or "Процесс обучения упал с исключением.").strip()[-600:])
    elif status == "crashed":
        add("warn", "crashed", "Связь с обучением потеряна",
            "Процесс перестал присылать данные: его закрыли, он упал без сообщения или компьютер уснул.")

    for key, pts in series.items():
        if metas[key]["kind"] != "loss":
            continue
        bad = next((s for s, v in pts if v is None), None)
        if bad is not None:
            add("crit", "nan", "В loss появились NaN или бесконечность",
                f"«{key}» перестал быть числом на шаге {bad} — дальше обучение бессмысленно. Обычно помогает "
                "уменьшить learning rate, включить ограничение градиентов (gradient clipping) и проверить данные "
                "на пустые или испорченные примеры.", key, bad)
            break

    train_key, val_key = _loss_pair(clean, metas)
    codes = lambda: {f["code"] for f in findings}

    if train_key and len(clean[train_key]) >= 8 and "nan" not in codes():
        steps = [s for s, _ in clean[train_key]]
        s = _smooth([v for _, v in clean[train_key]])
        n = len(s)
        lo = min(s)
        i_lo = s.index(lo)
        drop = s[0] - lo
        last = s[-1]
        if drop > 0 and i_lo < n - max(3, n // 10) and (last - lo) > 0.5 * drop and last > lo + 0.2 * abs(lo):
            add("crit", "diverge", "Обучение расходится",
                f"«{train_key}» опустился до {_fmt(lo)} на шаге {steps[i_lo]}, а потом вырос до {_fmt(last)}. "
                "Модель теряет то, чему научилась. Чаще всего виноват слишком большой learning rate.",
                train_key, steps[i_lo])
        elif n >= 20 and last >= s[0] - 0.02 * abs(s[0]):
            add("warn", "stuck", "Модель не учится",
                f"«{train_key}» почти не изменился с начала: {_fmt(s[0])} → {_fmt(last)}. Проверьте learning rate, "
                "разметку и то, что оптимизатору переданы параметры модели.", train_key)

    if train_key and val_key and len(clean[val_key]) >= 6 and not codes() & {"nan", "diverge"}:
        v_steps = [s for s, _ in clean[val_key]]
        sv = _smooth([v for _, v in clean[val_key]], max(1, min(5, len(v_steps) // 10)))
        n = len(sv)
        lo = min(sv)
        i_lo = sv.index(lo)
        gain = sv[0] - lo
        rise = sv[-1] - lo
        t_steps = [s for s, _ in clean[train_key]]
        st = _smooth([v for _, v in clean[train_key]])
        t_at_best = st[_nearest(t_steps, v_steps[i_lo])]
        t_last = st[-1]
        if (i_lo <= n - 1 - max(2, n // 8) and gain > 0 and rise > 0.1 * gain
                and rise > 0.03 * abs(lo) and t_last < t_at_best):
            pct = 100 * rise / abs(lo) if lo else 0
            level = "crit" if rise > 0.5 * gain or pct > 30 else "warn"
            add(level, "overfit", "Модель переобучается",
                f"На проверочных данных лучший результат был на шаге {v_steps[i_lo]} («{val_key}» = {_fmt(lo)}), "
                f"с тех пор он ухудшился на {pct:.0f}%, хотя на обучающих данных loss продолжает падать. Модель "
                f"заучивает примеры вместо того, чтобы обобщать. Берите чекпойнт с шага {v_steps[i_lo]}; дальше "
                "помогут ранняя остановка, аугментации, регуляризация или больше данных.", val_key, v_steps[i_lo])

    if train_key and len(clean[train_key]) >= 30 and not codes() & {"nan", "diverge"}:
        vals = [v for _, v in clean[train_key]]
        half = vals[len(vals) // 2:]
        w = max(3, len(half) // 10)
        centered = [sum(half[max(0, i - w):i + w + 1]) / len(half[max(0, i - w):i + w + 1]) for i in range(len(half))]
        resid = math.sqrt(sum((a - b) ** 2 for a, b in zip(half, centered)) / len(half))
        level = abs(sum(centered) / len(centered)) or 1e-12
        if resid / level > 0.35:
            add("info", "noisy", "Loss сильно скачет",
                f"Разброс «{train_key}» от шага к шагу — около {100 * resid / level:.0f}% от его уровня. Если это мешает, "
                "попробуйте уменьшить learning rate или увеличить batch size.", train_key)

    target = main_key if main_key in clean and metas[main_key]["direction"] else None
    target = target or val_key or train_key
    if not target:
        scored = [k for k in judged if len(clean[k]) >= 2]
        target = pick_main({k: metas[k] for k in scored}) if scored else None
    if target and len(clean[target]) >= 12 and not codes() & {"nan", "diverge", "stuck", "overfit"}:
        sign = -1 if metas[target]["direction"] == "min" else 1
        steps = [s for s, _ in clean[target]]
        s = _smooth([v for _, v in clean[target]], max(1, min(5, len(steps) // 12)))
        best, acc = [], None
        for v in s:
            acc = v if acc is None or sign * v > sign * acc else acc
            best.append(acc)
        cut = int(len(s) * 0.7)
        total = abs(best[-1] - s[0])
        recent = abs(best[-1] - best[cut])
        span = steps[-1] - steps[cut]
        name = metas[target]["label"]
        if total > 0 and recent / total < 0.02:
            if status == "running":
                add("info", "plateau", "Метрика вышла на плато",
                    f"За последние {span} шагов «{target}» практически не улучшается (лучшее — {_fmt(best[-1])}). "
                    "Можно останавливать обучение или снизить learning rate.", target)
            else:
                add("ok", "converged", "Обучение сошлось",
                    f"«{target}» вышла на уровень {_fmt(best[-1])} и к концу перестала меняться — "
                    "модель взяла из этих настроек всё, что могла.", target)
        elif total > 0:
            add("ok", "improving", "Модель продолжает улучшаться" if status == "running" else "Модель училась до конца",
                f"За последние {span} шагов {name} улучшилась с {_fmt(best[cut])} до {_fmt(best[-1])}."
                + ("" if status == "running" else " Возможно, стоит обучать дольше — запас ещё был."), target)

    if hw and hw.get("samples", 0) >= 12:
        gpus = hw.get("gpus") or []
        busy = max(gpus, key=lambda g: g.get("util_avg") or 0, default=None)
        if busy and busy.get("util_avg") is not None:
            u = busy["util_avg"]
            if u < 5:
                add("info", "gpu_idle", "Видеокарта не использовалась",
                    f"Средняя загрузка {busy['name']} — {u:.0f}%. Похоже, обучение шло на процессоре: проверьте, "
                    "что модель и данные перенесены на GPU.", hardware=True)
            elif u < 50:
                add("warn", "gpu_low", "Видеокарта простаивает",
                    f"{busy['name']} загружена в среднем на {u:.0f}%. Обычно это значит, что данные готовятся медленнее, "
                    "чем модель их обрабатывает: увеличьте число воркеров загрузчика или batch size.", hardware=True)
        for g in gpus:
            used, total = g.get("mem_max"), g.get("mem_total")
            if used and total and used / total > 0.96:
                add("warn", "vram_full", "Видеопамять почти закончилась",
                    f"{g['name']}: занято до {used / 2**30:.1f} из {total / 2**30:.1f} ГБ. Ещё немного — и обучение "
                    "упадёт с Out of Memory. Уменьшите batch size или включите смешанную точность.", hardware=True)
            elif used and total and (g.get("util_avg") or 0) >= 50 and used / total < 0.35:
                add("info", "vram_free", "Видеопамять используется слабо",
                    f"{g['name']}: занято максимум {100 * used / total:.0f}% памяти. Можно увеличить batch size "
                    "и обучаться быстрее.", hardware=True)
            if (g.get("temp_max") or 0) >= 87:
                add("warn", "gpu_hot", "Видеокарта перегревается",
                    f"{g['name']} нагревалась до {g['temp_max']:.0f} °C. При такой температуре карта сбрасывает "
                    "частоты и работает медленнее — проверьте охлаждение.", hardware=True)
        if (hw.get("ram_max_pct") or 0) > 96:
            add("warn", "ram_full", "Оперативная память на пределе",
                f"Занято до {hw['ram_max_pct']:.0f}% RAM — система может начать тормозить или завершить процесс.",
                hardware=True)

    rank = {c: i for i, c in enumerate(("nan", "diverge", "stuck", "overfit", "failed", "crashed"))}
    findings.sort(key=lambda f: (_ORDER[f["level"]], f["hardware"], rank.get(f["code"], 99)))
    training = [f for f in findings if not f["hardware"]]
    if not judged:
        verdict_code, health = "unknown", None
    elif not enough and not any(f["level"] == "crit" for f in training):
        verdict_code, health = "early", None
        add("info", "early", "Пока мало данных",
            "Для выводов нужно хотя бы десять точек loss или метрики качества — диагноз появится чуть позже.")
    else:
        verdict_code = training[0]["code"] if training else "improving"
        penalty = sum((_HW_PENALTY if f["hardware"] else _PENALTY)[f["level"]] for f in findings)
        health = max(0, 100 - penalty)
    level = next((f["level"] for f in findings if f["code"] == verdict_code), "info")
    if verdict_code == "improving" and status != "running":
        verdict_code = "done"
    return {"health": health, "findings": findings, "train_key": train_key, "val_key": val_key,
            "verdict": {"code": verdict_code, "label": _LABELS.get(verdict_code, verdict_code), "level": level}}
