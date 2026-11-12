"""Диагноз обучения человеческим языком.

    from diagnostics import analyze
    result = analyze(series, metas, status="running")

series: {ключ: [(step, value | None), ...]}  — None означает NaN/Inf
metas:  {ключ: describe(ключ)}               — см. glossary.py

Результат:
    {"health": 0..100 | None,
     "verdict": {"code": "overfit", "label": ..., "level": "warn"},
     "findings": [{"level", "code", "title", "text", "key", "step"}, ...]}

label, title и text — тексты сразу на русском и английском (см. i18n.T);
нужный язык выбирается через i18n.localize(result, "ru" | "en").

Все правила — эвристики по форме кривых. Они подсказывают, куда посмотреть,
а не заменяют взгляд на графики.
"""

from __future__ import annotations

import math

from i18n import T

from .glossary import describe, pick_main

__all__ = ["analyze", "describe", "pick_main"]

_PENALTY = {"crit": 45, "warn": 20, "info": 5, "ok": 0}
_HW_PENALTY = {"crit": 15, "warn": 10, "info": 3, "ok": 0}
_ORDER = {"crit": 0, "warn": 1, "info": 2, "ok": 3}

_LABELS = {
    "nan": T("Развалилось (NaN)", "Blew up (NaN)"),
    "failed": T("Ошибка", "Failed"),
    "diverge": T("Расходится", "Diverging"),
    "stuck": T("Не учится", "Not learning"),
    "overfit": T("Переобучение", "Overfitting"),
    "crashed": T("Прервано", "Interrupted"),
    "plateau": T("Плато", "Plateau"),
    "noisy": T("Нестабильно", "Unstable"),
    "early": T("Мало данных", "Too early"),
    "improving": T("Учится", "Learning"),
    "done": T("Прошло хорошо", "Went well"),
    "converged": T("Сошлось", "Converged"),
    "unknown": T("Нет оценки", "No verdict"),
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
        add("crit", "failed", T("Запуск завершился с ошибкой", "The run ended with an error"),
            error.strip()[-600:] if error and error.strip()
            else T("Процесс обучения упал с исключением.", "The training process crashed with an exception."))
    elif status == "crashed":
        add("warn", "crashed", T("Связь с обучением потеряна", "Lost contact with the training process"),
            T("Процесс перестал присылать данные: его закрыли, он упал без сообщения или компьютер уснул.",
              "The process stopped sending data: it was closed, crashed silently, or the computer went to sleep."))

    for key, pts in series.items():
        if metas[key]["kind"] != "loss":
            continue
        bad = next((s for s, v in pts if v is None), None)
        if bad is not None:
            add("crit", "nan", T("В loss появились NaN или бесконечность", "The loss became NaN or infinite"),
                T(f"«{key}» перестал быть числом на шаге {bad} — дальше обучение бессмысленно. Обычно помогает "
                  "уменьшить learning rate, включить ограничение градиентов (gradient clipping) и проверить данные "
                  "на пустые или испорченные примеры.",
                  f"“{key}” stopped being a number at step {bad} — training past this point is meaningless. "
                  "Lowering the learning rate, enabling gradient clipping and checking the data for empty or "
                  "corrupted examples usually helps."), key, bad)
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
            add("crit", "diverge", T("Обучение расходится", "Training is diverging"),
                T(f"«{train_key}» опустился до {_fmt(lo)} на шаге {steps[i_lo]}, а потом вырос до {_fmt(last)}. "
                  "Модель теряет то, чему научилась. Чаще всего виноват слишком большой learning rate.",
                  f"“{train_key}” went down to {_fmt(lo)} at step {steps[i_lo]} and then rose to {_fmt(last)}. "
                  "The model is losing what it has learned. The usual cause is a learning rate that is too high."),
                train_key, steps[i_lo])
        elif n >= 20 and last >= s[0] - 0.02 * abs(s[0]):
            add("warn", "stuck", T("Модель не учится", "The model is not learning"),
                T(f"«{train_key}» почти не изменился с начала: {_fmt(s[0])} → {_fmt(last)}. Проверьте learning rate, "
                  "разметку и то, что оптимизатору переданы параметры модели.",
                  f"“{train_key}” has barely changed since the start: {_fmt(s[0])} → {_fmt(last)}. Check the "
                  "learning rate, the labels, and that the optimizer was given the model's parameters."), train_key)

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
            best = v_steps[i_lo]
            add(level, "overfit", T("Модель переобучается", "The model is overfitting"),
                T(f"На проверочных данных лучший результат был на шаге {best} («{val_key}» = {_fmt(lo)}), "
                  f"с тех пор он ухудшился на {pct:.0f}%, хотя на обучающих данных loss продолжает падать. Модель "
                  f"заучивает примеры вместо того, чтобы обобщать. Берите чекпойнт с шага {best}; дальше "
                  "помогут ранняя остановка, аугментации, регуляризация или больше данных.",
                  f"The best validation result was at step {best} (“{val_key}” = {_fmt(lo)}); since then it has "
                  f"become {pct:.0f}% worse while the training loss keeps falling. The model is memorizing examples "
                  f"instead of generalizing. Take the checkpoint from step {best}; next time early stopping, "
                  "augmentation, regularization or more data will help."), val_key, best)

    if train_key and len(clean[train_key]) >= 30 and not codes() & {"nan", "diverge"}:
        vals = [v for _, v in clean[train_key]]
        half = vals[len(vals) // 2:]
        w = max(3, len(half) // 10)
        centered = [sum(half[max(0, i - w):i + w + 1]) / len(half[max(0, i - w):i + w + 1]) for i in range(len(half))]
        resid = math.sqrt(sum((a - b) ** 2 for a, b in zip(half, centered)) / len(half))
        level = abs(sum(centered) / len(centered)) or 1e-12
        if resid / level > 0.35:
            noise = 100 * resid / level
            add("info", "noisy", T("Loss сильно скачет", "The loss is very noisy"),
                T(f"Разброс «{train_key}» от шага к шагу — около {noise:.0f}% от его уровня. Если это мешает, "
                  "попробуйте уменьшить learning rate или увеличить batch size.",
                  f"“{train_key}” varies from step to step by about {noise:.0f}% of its level. If that gets in the "
                  "way, try a lower learning rate or a larger batch size."), train_key)

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
                add("info", "plateau", T("Метрика вышла на плато", "The metric has reached a plateau"),
                    T(f"За последние {span} шагов «{target}» практически не улучшается (лучшее — {_fmt(best[-1])}). "
                      "Можно останавливать обучение или снизить learning rate.",
                      f"Over the last {span} steps “{target}” has barely improved (best: {_fmt(best[-1])}). "
                      "You can stop training or lower the learning rate."), target)
            else:
                add("ok", "converged", T("Обучение сошлось", "Training converged"),
                    T(f"«{target}» вышла на уровень {_fmt(best[-1])} и к концу перестала меняться — "
                      "модель взяла из этих настроек всё, что могла.",
                      f"“{target}” reached {_fmt(best[-1])} and stopped changing towards the end — the model got "
                      "everything it could out of these settings."), target)
        elif total > 0:
            running = status == "running"
            add("ok", "improving",
                T("Модель продолжает улучшаться", "The model keeps improving") if running
                else T("Модель училась до конца", "The model was learning until the end"),
                T(f"За последние {span} шагов {name} улучшилась с {_fmt(best[cut])} до {_fmt(best[-1])}."
                  + ("" if running else " Возможно, стоит обучать дольше — запас ещё был."),
                  f"Over the last {span} steps {name} improved from {_fmt(best[cut])} to {_fmt(best[-1])}."
                  + ("" if running else " Training longer may be worth it — there was still room to improve.")),
                target)

    if hw and hw.get("samples", 0) >= 12:
        gpus = hw.get("gpus") or []
        busy = max(gpus, key=lambda g: g.get("util_avg") or 0, default=None)
        if busy and busy.get("util_avg") is not None:
            u = busy["util_avg"]
            if u < 5:
                add("info", "gpu_idle", T("Видеокарта не использовалась", "The GPU was not used"),
                    T(f"Средняя загрузка {busy['name']} — {u:.0f}%. Похоже, обучение шло на процессоре: проверьте, "
                      "что модель и данные перенесены на GPU.",
                      f"Average load of {busy['name']} was {u:.0f}%. Training seems to have run on the CPU: check "
                      "that the model and the data are moved to the GPU."), hardware=True)
            elif u < 50:
                add("warn", "gpu_low", T("Видеокарта простаивает", "The GPU is idle most of the time"),
                    T(f"{busy['name']} загружена в среднем на {u:.0f}%. Обычно это значит, что данные готовятся "
                      "медленнее, чем модель их обрабатывает: увеличьте число воркеров загрузчика или batch size.",
                      f"{busy['name']} was loaded {u:.0f}% on average. This usually means data is prepared more "
                      "slowly than the model consumes it: add data loader workers or increase the batch size."),
                    hardware=True)
        for g in gpus:
            used, total = g.get("mem_max"), g.get("mem_total")
            if used and total and used / total > 0.96:
                add("warn", "vram_full", T("Видеопамять почти закончилась", "Video memory is almost full"),
                    T(f"{g['name']}: занято до {used / 2**30:.1f} из {total / 2**30:.1f} ГБ. Ещё немного — и обучение "
                      "упадёт с Out of Memory. Уменьшите batch size или включите смешанную точность.",
                      f"{g['name']}: up to {used / 2**30:.1f} of {total / 2**30:.1f} GB in use. A little more and "
                      "training will crash with Out of Memory. Reduce the batch size or enable mixed precision."),
                    hardware=True)
            elif used and total and (g.get("util_avg") or 0) >= 50 and used / total < 0.35:
                share = 100 * used / total
                add("info", "vram_free", T("Видеопамять используется слабо", "Video memory is barely used"),
                    T(f"{g['name']}: занято максимум {share:.0f}% памяти. Можно увеличить batch size "
                      "и обучаться быстрее.",
                      f"{g['name']}: at most {share:.0f}% of memory in use. You can increase the batch size "
                      "and train faster."), hardware=True)
            if (g.get("temp_max") or 0) >= 87:
                add("warn", "gpu_hot", T("Видеокарта перегревается", "The GPU is overheating"),
                    T(f"{g['name']} нагревалась до {g['temp_max']:.0f} °C. При такой температуре карта сбрасывает "
                      "частоты и работает медленнее — проверьте охлаждение.",
                      f"{g['name']} reached {g['temp_max']:.0f} °C. At this temperature the card throttles and "
                      "runs slower — check the cooling."), hardware=True)
        if (hw.get("ram_max_pct") or 0) > 96:
            add("warn", "ram_full", T("Оперативная память на пределе", "System memory is at its limit"),
                T(f"Занято до {hw['ram_max_pct']:.0f}% RAM — система может начать тормозить или завершить процесс.",
                  f"Up to {hw['ram_max_pct']:.0f}% of RAM in use — the system may slow down or kill the process."),
                hardware=True)

    rank = {c: i for i, c in enumerate(("nan", "diverge", "stuck", "overfit", "failed", "crashed"))}
    findings.sort(key=lambda f: (_ORDER[f["level"]], f["hardware"], rank.get(f["code"], 99)))
    training = [f for f in findings if not f["hardware"]]
    if not judged:
        verdict_code, health = "unknown", None
    elif not enough and not any(f["level"] == "crit" for f in training):
        verdict_code, health = "early", None
        add("info", "early", T("Пока мало данных", "Not enough data yet"),
            T("Для выводов нужно хотя бы десять точек loss или метрики качества — диагноз появится чуть позже.",
              "A verdict needs at least ten points of loss or a quality metric — it will appear a little later."))
    else:
        verdict_code = training[0]["code"] if training else "improving"
        penalty = sum((_HW_PENALTY if f["hardware"] else _PENALTY)[f["level"]] for f in findings)
        health = max(0, 100 - penalty)
    level = next((f["level"] for f in findings if f["code"] == verdict_code), "info")
    if verdict_code == "improving" and status != "running":
        verdict_code = "done"
    return {"health": health, "findings": findings, "train_key": train_key, "val_key": val_key,
            "verdict": {"code": verdict_code, "label": _LABELS.get(verdict_code, verdict_code), "level": level}}
