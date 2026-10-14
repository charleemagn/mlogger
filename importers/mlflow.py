"""Импорт локальной папки MLflow (file store) без установки mlflow.

    mlruns/<experiment_id>/<run_id>/
        metrics/<key>   строки "<timestamp_ms> <value> <step>"
        params/<key>    значение параметра
        tags/mlflow.runName
"""

from __future__ import annotations

from pathlib import Path

from .base import ImportedRun, MetricPoint

SOURCE = "mlflow"


def _is_run_dir(path: Path) -> bool:
    return (path / "meta.yaml").is_file() and (path / "metrics").is_dir()


def _run_dirs(path: Path) -> list[Path]:
    if _is_run_dir(path):
        return [path]
    # Подходит и вся папка mlruns, и папка одного эксперимента
    return sorted(p.parent for p in path.rglob("meta.yaml") if _is_run_dir(p.parent) and ".trash" not in p.parts)


def detect(path: Path) -> bool:
    return path.is_dir() and bool(_run_dirs(path))


def _read_tree(root: Path) -> dict[str, str]:
    """Ключи с "/" (например train/loss) MLflow хранит как вложенные папки."""
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*") if p.is_file()}


def _load_run(run_dir: Path) -> ImportedRun:
    tags = _read_tree(run_dir / "tags")
    run = ImportedRun(
        name=tags.get("mlflow.runName", run_dir.name).strip(),
        source=SOURCE,
        path=run_dir,
        params={k: v.strip() for k, v in _read_tree(run_dir / "params").items()},
    )
    for key, text in _read_tree(run_dir / "metrics").items():
        for line in text.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            step = int(parts[2]) if len(parts) > 2 else 0
            run.metrics.append(MetricPoint(key=key, step=step, value=float(parts[1]), ts=int(parts[0]) / 1000))
    return run


def load(path: Path) -> list[ImportedRun]:
    return [_load_run(d) for d in _run_dirs(path)]
