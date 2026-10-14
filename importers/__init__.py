"""Импорт существующих логов обучения: пользователь ничего не меняет в коде.

    from importers import load
    runs = load("runs/detect/train")      # results.csv от Ultralytics
    runs = load("lightning_logs")         # event-файлы TensorBoard
    runs = load("mlruns")                 # локальная папка MLflow

Новый формат = новый модуль с функциями detect(path) и load(path),
добавленный в IMPORTERS.
"""

from __future__ import annotations

from pathlib import Path

from . import mlflow, tensorboard, ultralytics
from .base import ImportedRun, MetricPoint

# Порядок важен: у Ultralytics рядом с results.csv бывают и event-файлы TensorBoard
IMPORTERS = [ultralytics, mlflow, tensorboard]

__all__ = ["IMPORTERS", "ImportedRun", "MetricPoint", "load"]


def load(path: str | Path, source: str | None = None) -> list[ImportedRun]:
    """Определяет формат по содержимому path и возвращает найденные запуски."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    for importer in IMPORTERS:
        if source is None and importer.detect(path) or importer.SOURCE == source:
            return importer.load(path)
    raise ValueError(f"не удалось определить формат логов: {path}")
