"""Импорт event-файлов TensorBoard без установки tensorflow/tensorboard.

Файл events.out.tfevents.* — это последовательность TFRecord-записей,
в каждой лежит protobuf-сообщение Event. Нам нужны только скаляры:
  - simple_value  — так пишут PyTorch SummaryWriter и TF1;
  - tensor        — так пишет TF2 (tf.summary.scalar), плагин "scalars".
Каждая папка с event-файлами считается отдельным запуском.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator

from .base import ImportedRun, MetricPoint

SOURCE = "tensorboard"

# --- Минимальный разбор protobuf -------------------------------------------


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _fields(buf: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    """Отдаёт (номер поля, тип, значение) для каждого поля сообщения."""
    pos = 0
    while pos < len(buf):
        tag, pos = _varint(buf, pos)
        num, wire = tag >> 3, tag & 7
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            value, pos = buf[pos:pos + 8], pos + 8
        elif wire == 2:
            size, pos = _varint(buf, pos)
            value, pos = buf[pos:pos + size], pos + size
        elif wire == 5:
            value, pos = buf[pos:pos + 4], pos + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield num, wire, value


def _tensor_scalar(buf: bytes) -> float | None:
    """TensorProto -> float, если это скаляр float/double."""
    dtype, has_dims, content, values = 0, False, b"", []
    for num, wire, value in _fields(buf):
        if num == 1:
            dtype = value
        elif num == 2:
            has_dims = any(n == 2 for n, _, _ in _fields(value))  # TensorShapeProto.dim
        elif num == 4:
            content = value
        elif num == 5:  # float_val (packed или одиночный)
            values += struct.unpack(f"<{len(value) // 4}f", value)
        elif num == 6:  # double_val
            values += struct.unpack(f"<{len(value) // 8}d", value)
    if has_dims:
        return None
    if values:
        return float(values[0])
    if dtype == 1 and len(content) == 4:  # DT_FLOAT
        return struct.unpack("<f", content)[0]
    if dtype == 2 and len(content) == 8:  # DT_DOUBLE
        return struct.unpack("<d", content)[0]
    return None


def _plugin_name(metadata: bytes) -> str:
    for num, _, value in _fields(metadata):
        if num == 1:  # SummaryMetadata.plugin_data
            for n, _, v in _fields(value):
                if n == 1:  # PluginData.plugin_name
                    return v.decode()
    return ""


# --- Чтение файлов ---------------------------------------------------------


def _records(path: Path) -> Iterator[bytes]:
    """TFRecord: uint64 длина, uint32 crc, данные, uint32 crc."""
    with path.open("rb") as f:
        while True:
            header = f.read(12)
            if len(header) < 12:
                return
            (length,) = struct.unpack("<Q", header[:8])
            data = f.read(length)
            if len(data) < length or len(f.read(4)) < 4:
                return  # файл ещё дописывается — берём то, что есть
            yield data


def _read_events(path: Path, plugins: dict[str, str]) -> Iterator[MetricPoint]:
    for record in _records(path):
        wall_time, step, summary = None, 0, None
        for num, _, value in _fields(record):
            if num == 1:
                (wall_time,) = struct.unpack("<d", value)
            elif num == 2:
                step = value
            elif num == 5:
                summary = value
        if summary is None:
            continue
        for num, _, value_msg in _fields(summary):
            if num != 1:
                continue
            tag, simple, tensor = None, None, None
            for n, _, v in _fields(value_msg):
                if n == 1:
                    tag = v.decode()
                elif n == 2:
                    (simple,) = struct.unpack("<f", v)
                elif n == 8:
                    tensor = v
                elif n == 9:
                    plugins[tag] = _plugin_name(v)
            if simple is not None:
                yield MetricPoint(key=tag, step=step, value=simple, ts=wall_time)
            elif tensor is not None and plugins.get(tag) == "scalars":
                # TF2 пишет metadata только в первом событии тега, поэтому plugins общий на запуск
                scalar = _tensor_scalar(tensor)
                if scalar is not None:
                    yield MetricPoint(key=tag, step=step, value=scalar, ts=wall_time)


def _event_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if "tfevents" in path.name else []
    return sorted(p for p in path.rglob("*tfevents*") if p.is_file())


def detect(path: Path) -> bool:
    return bool(_event_files(path))


def load(path: Path) -> list[ImportedRun]:
    root = path if path.is_dir() else path.parent
    by_dir: dict[Path, list[Path]] = {}
    for f in _event_files(path):
        by_dir.setdefault(f.parent, []).append(f)

    runs = []
    for run_dir, files in sorted(by_dir.items()):
        name = run_dir.relative_to(root).as_posix() if run_dir != root else run_dir.name
        run = ImportedRun(name=name, source=SOURCE, path=run_dir)
        plugins: dict[str, str] = {}
        for f in files:  # имена файлов содержат время создания, сортировка = хронология
            run.metrics.extend(_read_events(f, plugins))
        runs.append(run)
    return runs
