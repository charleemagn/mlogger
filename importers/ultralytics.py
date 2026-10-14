"""Импорт results.csv от Ultralytics (YOLO).

Папка запуска выглядит так:
    runs/detect/train/
        results.csv   epoch,train/box_loss,...,metrics/mAP50-95(B),...,lr/pg0
        args.yaml     параметры обучения
"""

from __future__ import annotations

import csv
from pathlib import Path

from .base import ImportedRun, MetricPoint

SOURCE = "ultralytics"


def _csv_path(path: Path) -> Path | None:
    if path.is_file() and path.name == "results.csv":
        return path
    if path.is_dir() and (path / "results.csv").is_file():
        return path / "results.csv"
    return None


def detect(path: Path) -> bool:
    return _csv_path(path) is not None


def _read_args(run_dir: Path) -> dict:
    args = run_dir / "args.yaml"
    if not args.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    return yaml.safe_load(args.read_text(encoding="utf-8")) or {}


def load(path: Path) -> list[ImportedRun]:
    csv_path = _csv_path(path)
    run_dir = csv_path.parent
    run = ImportedRun(name=run_dir.name, source=SOURCE, path=run_dir, params=_read_args(run_dir))

    with csv_path.open(newline="", encoding="utf-8") as f:
        # Старые версии выравнивают колонки пробелами: "      train/box_loss"
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        for row in reader:
            values = dict(zip(header, (v.strip() for v in row)))
            step = int(float(values.pop("epoch")))
            for key, raw in values.items():
                if raw == "":
                    continue
                run.metrics.append(MetricPoint(key=key, step=step, value=float(raw)))
    return [run]
