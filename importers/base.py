"""Единый формат, к которому импортёры приводят чужие логи."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MetricPoint:
    key: str
    step: int
    value: float
    ts: float | None = None  # unix-время в секундах, если источник его пишет


@dataclass
class ImportedRun:
    name: str
    source: str  # "ultralytics" | "tensorboard" | "mlflow"
    path: Path
    params: dict = field(default_factory=dict)
    metrics: list[MetricPoint] = field(default_factory=list)

    def keys(self) -> list[str]:
        return sorted({m.key for m in self.metrics})

    def series(self, key: str) -> list[MetricPoint]:
        return sorted((m for m in self.metrics if m.key == key), key=lambda m: m.step)

    def to_payload(self) -> list[dict]:
        """Тело для POST /api/v1/runs/{id}/metrics."""
        return [{"key": m.key, "step": m.step, "value": m.value, "ts": m.ts} for m in self.metrics]
