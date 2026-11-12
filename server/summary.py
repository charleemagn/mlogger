"""Сводка запуска: итоги по каждой метрике, главная метрика, диагноз, прогресс."""

from __future__ import annotations

import time

from diagnostics import analyze, describe, pick_main

SPARK_POINTS = 48
ANALYZE_POINTS = 2000
SUMMARY_VERSION = 2


def bucket_mean(values: list, n: int) -> list:
    """Сжимает ряд до n точек усреднением по корзинам (для спарклайнов и анализа)."""
    values = [v for v in values if v is not None]
    if len(values) <= n:
        return values
    size = len(values) / n
    out = []
    for i in range(n):
        chunk = values[int(i * size):max(int((i + 1) * size), int(i * size) + 1)]
        out.append(sum(chunk) / len(chunk))
    return out


def downsample(points: list, max_points: int) -> list:
    """Прореживает [(step, value, ts)], сохраняя в каждой корзине минимум и максимум — пики не теряются."""
    n = len(points)
    if n <= max_points or max_points < 4:
        return points
    buckets = max_points // 2
    size = n / buckets
    out = []
    for b in range(buckets):
        chunk = points[int(b * size):max(int((b + 1) * size), int(b * size) + 1)]
        real = [p for p in chunk if p[1] is not None]
        if not real:
            out.append(chunk[0])
            continue
        lo, hi = min(real, key=lambda p: p[1]), max(real, key=lambda p: p[1])
        picked = {lo[0]: lo, hi[0]: hi}
        if len(real) < len(chunk):
            gap = next(p for p in chunk if p[1] is None)
            picked[gap[0]] = gap
        out.extend(picked[s] for s in sorted(picked))
    if out[-1][0] != points[-1][0]:
        out.append(points[-1])
    return out


def series_payload(points: list, t0: float, max_points: int) -> dict:
    points = downsample(points, max_points)
    has_ts = any(p[2] is not None for p in points)
    return {
        "steps": [p[0] for p in points],
        "values": [p[1] for p in points],
        "t": [round(p[2] - t0, 1) if p[2] is not None else None for p in points] if has_ts else None,
    }


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _max(xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def hw_stats(samples: list) -> dict | None:
    """Средние и пики по железу за время запуска — для диагноза и плашек."""
    if not samples:
        return None
    gpus: dict = {}
    for s in samples:
        for g in s.get("gpus") or []:
            slot = gpus.setdefault(g.get("id") or g.get("name"), {"name": g.get("name"), "vendor": g.get("vendor"),
                                                                  "util": [], "mem": [], "temp": [], "power": [],
                                                                  "mem_total": g.get("mem_total")})
            slot["util"].append(g.get("util"))
            slot["mem"].append(g.get("mem_used"))
            slot["temp"].append(g.get("temp"))
            slot["power"].append(g.get("power"))
    ram = [100 * s["ram_used"] / s["ram_total"] for s in samples if s.get("ram_used") and s.get("ram_total")]
    return {
        "samples": len(samples),
        "cpu_avg": _mean([s.get("cpu") for s in samples]),
        "ram_max_pct": _max(ram),
        "gpus": [{"name": g["name"], "vendor": g["vendor"], "mem_total": g["mem_total"],
                  "util_avg": _mean(g["util"]), "util_max": _max(g["util"]), "mem_max": _max(g["mem"]),
                  "temp_max": _max(g["temp"]), "power_avg": _mean(g["power"])} for g in gpus.values()],
    }


def system_payload(samples: list, t0: float, max_points: int = 400) -> dict:
    """Ряды для графиков железа: время в секундах от t0, по одному ряду на видеокарту."""
    if len(samples) > max_points:
        step = len(samples) / max_points
        samples = [samples[int(i * step)] for i in range(max_points)]
    gpus: dict = {}
    for i, s in enumerate(samples):
        for g in s.get("gpus") or []:
            gid = g.get("id") or g.get("name")
            slot = gpus.setdefault(gid, {"id": gid, "name": g.get("name"), "vendor": g.get("vendor"),
                                         "mem_total": g.get("mem_total"),
                                         "util": [None] * len(samples), "mem": [None] * len(samples),
                                         "temp": [None] * len(samples), "power": [None] * len(samples)})
            slot["util"][i] = g.get("util")
            slot["mem"][i] = g.get("mem_used")
            slot["temp"][i] = g.get("temp")
            slot["power"][i] = g.get("power")
    return {
        "t": [round(s["ts"] - t0, 1) for s in samples],
        "cpu": [s.get("cpu") for s in samples],
        "ram": [s.get("ram_used") for s in samples],
        "ram_total": next((s.get("ram_total") for s in samples if s.get("ram_total")), None),
        "gpus": list(gpus.values()),
    }


def build_summary(db, run: dict) -> dict:
    raw = db.series(run["id"])
    metas = {k: describe(k) for k in raw}
    keys: dict = {}
    max_step, last_ts = None, None
    for key, pts in raw.items():
        real = [(s, v) for s, v, _ in pts if v is not None]
        meta = metas[key]
        info = {**meta, "count": len(pts), "nonfinite": len(pts) - len(real)}
        if real:
            sign = -1 if meta["direction"] == "min" else 1
            best = max(real, key=lambda p: sign * p[1]) if meta["direction"] else real[-1]
            info.update(first=real[0][1], last=real[-1][1], last_step=real[-1][0],
                        min=min(v for _, v in real), max=max(v for _, v in real),
                        best=best[1], best_step=best[0],
                        spark=bucket_mean([v for _, v in real], SPARK_POINTS))
        keys[key] = info
        if pts:
            max_step = pts[-1][0] if max_step is None else max(max_step, pts[-1][0])
            stamps = [t for _, _, t in pts[-3:] if t is not None]
            if stamps:
                last_ts = max(stamps) if last_ts is None else max(last_ts, *stamps)

    main_key = run.get("main_metric") if run.get("main_metric") in keys else pick_main(metas)

    end = run.get("finished_at") or (time.time() if run["status"] == "running" else last_ts) or run["created_at"]
    hw = hw_stats(db.samples(run["host"], run["created_at"], end)) if run.get("host") else None

    analysis_series = {}
    for key, pts in raw.items():
        if metas[key]["kind"] not in ("loss", "score"):
            continue
        pts = downsample(pts, ANALYZE_POINTS) if len(pts) > ANALYZE_POINTS else pts
        analysis_series[key] = [(s, v) for s, v, _ in pts]
    diagnosis = analyze(analysis_series, {k: metas[k] for k in analysis_series}, status=run["status"],
                        error=run.get("error"), hw=hw, main_key=main_key)

    progress, eta = None, None
    total = run.get("total_steps")
    if run["status"] == "finished":
        progress = 1.0
    elif total and max_step is not None:
        progress = max(0.0, min(1.0, max_step / total))
        elapsed = (last_ts or time.time()) - run["created_at"]
        if run["status"] == "running" and max_step > 0 and elapsed > 0:
            eta = max(0.0, (total - max_step) * elapsed / max_step)

    return {"keys": keys, "main_key": main_key, "max_step": max_step, "last_ts": last_ts,
            "duration": max(0.0, end - run["created_at"]), "progress": progress, "eta": eta,
            "hw": hw, "diagnosis": diagnosis, "built_at": time.time(), "version": SUMMARY_VERSION}
