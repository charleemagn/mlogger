"""Демо-данные: несколько правдоподобных запусков, чтобы интерфейс можно было посмотреть сразу.

Кривые синтетические, но каждая показывает свой сценарий: хорошее обучение, переобучение,
плато, развал с NaN и один запуск, который «обучается» прямо сейчас.
"""

from __future__ import annotations

import math
import random
import threading
import time

PROJECT = "demo-cifar10"
HOST = "demo-rig"
GB = 2 ** 30
GPUS = [("demo:0", "NVIDIA GeForce RTX 4090", "NVIDIA", 24 * GB), ("demo:1", "AMD Radeon RX 7900 XT", "AMD", 20 * GB)]


def _curve(rng, step, total, *, start, floor, speed, noise):
    """Экспоненциальный спад от start к floor с шумом."""
    base = floor + (start - floor) * math.exp(-speed * step / total)
    return max(1e-4, base * (1 + rng.gauss(0, noise)))


def _lr(step, total, peak, warmup=0.05):
    w = int(total * warmup)
    if step < w:
        return peak * (step + 1) / w
    return peak * 0.5 * (1 + math.cos(math.pi * (step - w) / max(1, total - w)))


def _scenario(kind: str, step: int, total: int, rng) -> dict:
    """Точки одного шага для сценария."""
    p = step / total
    val = step % 25 == 0 or step == total - 1
    out = {}
    if kind == "good":
        out["train/loss"] = _curve(rng, step, total, start=2.3, floor=0.18, speed=5.0, noise=0.06)
        out["lr"] = _lr(step, total, 3e-4)
        if val:
            vl = _curve(rng, step, total, start=2.25, floor=0.31, speed=4.6, noise=0.015)
            out["val/loss"] = vl
            out["val/accuracy"] = min(0.99, 0.915 - 0.82 * math.exp(-4.8 * p) + rng.gauss(0, 0.003))
    elif kind == "best":
        out["train/loss"] = _curve(rng, step, total, start=2.3, floor=0.21, speed=4.2, noise=0.07)
        out["lr"] = _lr(step, total, 6e-4)
        if val:
            out["val/loss"] = _curve(rng, step, total, start=2.25, floor=0.22, speed=4.0, noise=0.015)
            out["val/accuracy"] = min(0.99, 0.945 - 0.85 * math.exp(-4.2 * p) + rng.gauss(0, 0.003))
    elif kind == "overfit":
        out["train/loss"] = _curve(rng, step, total, start=2.3, floor=0.015, speed=7.5, noise=0.06)
        out["lr"] = 1e-3
        if val:
            rise = max(0.0, p - 0.33) ** 1.3 * 0.5
            out["val/loss"] = (0.48 + 1.8 * math.exp(-11 * p) + rise) * (1 + rng.gauss(0, 0.012))
            out["val/accuracy"] = 0.87 - 0.78 * math.exp(-10 * p) - 0.07 * max(0.0, p - 0.33) + rng.gauss(0, 0.003)
    elif kind == "plateau":
        out["train/loss"] = _curve(rng, step, total, start=2.3, floor=0.62, speed=14.0, noise=0.05)
        out["lr"] = 1e-4
        if val:
            out["val/loss"] = _curve(rng, step, total, start=2.25, floor=0.69, speed=13.0, noise=0.008)
            out["val/accuracy"] = 0.781 - 0.7 * math.exp(-13 * p) + rng.gauss(0, 0.0012)
    elif kind == "nan":
        blow = max(0.0, p - 0.55)
        out["train/loss"] = _curve(rng, step, total, start=2.3, floor=1.1, speed=6.0, noise=0.22) * (1 + 60 * blow ** 2)
        out["lr"] = 1e-1
        if val:
            out["val/loss"] = _curve(rng, step, total, start=2.3, floor=1.3, speed=5.0, noise=0.05) * (1 + 60 * blow ** 2)
            out["val/accuracy"] = max(0.1, 0.52 - 0.42 * math.exp(-5 * p) - 4 * blow + rng.gauss(0, 0.01))
    return out


RUNS = [
    ("resnet18-baseline", "good", 1500, 4.2, 38, "finished", ["baseline"],
     {"model": "resnet18", "optimizer": "AdamW", "lr": 3e-4, "batch_size": 128, "epochs": 60, "augment": "flip+crop",
      "weight_decay": 0.05, "scheduler": "cosine"}, 93),
    ("resnet50-no-aug", "overfit", 1500, 3.1, 64, "finished", ["no-aug"],
     {"model": "resnet50", "optimizer": "AdamW", "lr": 1e-3, "batch_size": 128, "epochs": 60, "augment": "none",
      "weight_decay": 0.0, "scheduler": "constant"}, 96),
    ("resnet18-lr-0.1", "nan", 900, 2.6, 14, "failed", ["lr-sweep"],
     {"model": "resnet18", "optimizer": "SGD", "lr": 1e-1, "batch_size": 128, "epochs": 60, "augment": "flip+crop",
      "weight_decay": 0.05, "scheduler": "constant"}, 91),
    ("mobilenet-v3-small", "plateau", 1500, 1.8, 47, "finished", ["mobile"],
     {"model": "mobilenet_v3_small", "optimizer": "AdamW", "lr": 1e-4, "batch_size": 32, "epochs": 60,
      "augment": "flip+crop", "weight_decay": 0.05, "scheduler": "constant", "num_workers": 1}, 34),
    ("resnet18-cosine-randaug", "best", 1500, 0.9, 41, "finished", ["aug", "кандидат"],
     {"model": "resnet18", "optimizer": "AdamW", "lr": 6e-4, "batch_size": 256, "epochs": 60, "augment": "randaugment",
      "weight_decay": 0.05, "scheduler": "cosine"}, 95),
]
ENV = {"python": "3.12.4", "platform": "Windows-11", "frameworks": {"torch": "2.6.0+cu124", "numpy": "2.1.3"},
       "script": "train.py", "demo": True}


def _hardware(db, rng, t0: float, minutes: float, util: float, mem_frac: float):
    """Показания «учебной» машины с двумя видеокартами разных производителей."""
    n = int(minutes * 60 / 15)
    for i in range(n):
        warm = min(1.0, i / 8)
        db.add_sample(HOST, {
            "ts": t0 + i * 15, "cpu": max(3.0, rng.gauss(38 if util > 60 else 96, 6)),
            "ram_used": (11.5 + rng.gauss(0, 0.2)) * GB, "ram_total": 64 * GB,
            "gpus": [
                {"id": GPUS[0][0], "index": 0, "name": GPUS[0][1], "vendor": GPUS[0][2], "mem_total": GPUS[0][3],
                 "util": max(0.0, min(100.0, rng.gauss(util, 4) * warm)), "mem_used": mem_frac * GPUS[0][3] * (0.3 + 0.7 * warm),
                 "temp": 42 + (29 if util > 60 else 14) * warm + rng.gauss(0, 0.8), "power": 60 + util * 3.4 * warm, "fan": 30 + 40 * warm},
                {"id": GPUS[1][0], "index": 1, "name": GPUS[1][1], "vendor": GPUS[1][2], "mem_total": GPUS[1][3],
                 "util": max(0.0, rng.gauss(3, 1.5)), "mem_used": 0.9 * GB, "temp": None, "power": None, "fan": None},
            ]})


def create(db) -> list:
    remove(db)
    now = time.time()
    created = []
    db.save_host(HOST, {"host": HOST, "os": "Windows 11", "cpu": "AMD Ryzen 9 7950X", "demo": True})
    for name, kind, total, days, minutes, status, tags, config, util in RUNS:
        rng = random.Random(name)
        t0 = now - days * 86400
        run = db.create_run({"name": name, "project": PROJECT, "source": "demo", "status": status, "host": HOST,
                             "created_at": t0, "total_steps": 1500, "config": config, "tags": ["demo", *tags], "env": ENV,
                             "main_metric": "val/accuracy"})
        points = []
        for step in range(total):
            ts = t0 + minutes * 60 * step / total
            for key, value in _scenario(kind, step, total, rng).items():
                points.append({"key": key, "step": step, "value": value, "ts": ts})
        if kind == "nan":
            points.append({"key": "train/loss", "step": total, "value": None, "ts": t0 + minutes * 60})
        db.add_metrics(run["id"], points)
        db.finish_run(run["id"], status, finished_at=t0 + minutes * 60,
                      error="RuntimeError: loss is NaN at step 900\n  File \"train.py\", line 88, in train_step"
                      if status == "failed" else None)
        _hardware(db, rng, t0, minutes, util, 0.985 if kind == "overfit" else (0.22 if kind == "best" else 0.6))
        created.append(run["id"])

    live = db.create_run({"name": "vit-tiny-live", "project": PROJECT, "source": "demo", "total_steps": 600,
                          "config": {"model": "vit_tiny_patch16", "optimizer": "AdamW", "lr": 5e-4, "batch_size": 256,
                                     "epochs": 24, "augment": "randaugment", "weight_decay": 0.05, "scheduler": "cosine"},
                          "tags": ["demo", "live"], "env": ENV, "main_metric": "val/accuracy"})
    created.append(live["id"])
    threading.Thread(target=_live, args=(db, live["id"]), name="mlogger-demo", daemon=True).start()
    return created


def _live(db, run_id: str, total: int = 600):
    """Запуск, который «обучается» на глазах: полторы точки в секунду в течение нескольких минут."""
    rng = random.Random(run_id)
    for step in range(total):
        if not db.get_run(run_id):
            return
        points = [{"key": k, "step": step, "value": v, "ts": time.time()}
                  for k, v in _scenario("good", int(step * 2.5), 1500, rng).items()]
        db.heartbeat(run_id)
        db.add_metrics(run_id, points)
        time.sleep(0.65)
    db.finish_run(run_id, "finished")


def remove(db) -> int:
    runs = [r for r in db.list_runs() if r["source"] == "demo"]
    for r in runs:
        db.delete_run(r["id"])
    db.delete_samples(HOST)
    return len(runs)
