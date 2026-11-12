"""Клиент MLogger: отправляет метрики обучения на локальный сервер.

Главное правило: трекер никогда не должен мешать обучению. Все сетевые операции идут
в фоновом потоке, любые ошибки связи проглатываются, а неотправленные данные
сохраняются на диск и досылаются при следующем запуске.
"""

from __future__ import annotations

import atexit
import json
import math
import os
import platform
import random
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8765"
FLUSH_INTERVAL = 1.0
HEARTBEAT_INTERVAL = 15.0
BATCH = 2000
MAX_BUFFER = 500_000
_FRAMEWORKS = ("torch", "tensorflow", "keras", "jax", "lightning", "pytorch_lightning", "ultralytics",
               "transformers", "sklearn", "xgboost", "lightgbm", "catboost", "numpy")
_ADJECTIVES = ("misty", "quiet", "silver", "granite", "rapid", "clear", "deep", "cold", "bright", "mossy",
               "steady", "wild", "calm", "blue", "stone", "swift")
_NOUNS = ("brook", "falls", "ridge", "creek", "boulder", "spring", "rapids", "canyon", "delta", "glacier",
          "lagoon", "basalt", "stream", "cliff", "pebble", "torrent")

_current = None


def _say(text: str):
    try:
        print(f"[mlogger] {text}", file=sys.stderr)
    except Exception:
        pass


def _spool_dir() -> Path:
    return Path(os.environ.get("MLOGGER_SPOOL") or Path.home() / ".mlogger" / "spool")


def _number(value):
    """Число из чего угодно: int, float, numpy, тензор с одним элементом. None — если это не число."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return float(item())
        except Exception:
            return None
    try:
        return float(value)
    except Exception:
        return None


def _flatten(data: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, name + "/"))
        else:
            out[name] = value
    return out


def _environment() -> dict:
    env = {"python": platform.python_version(), "platform": platform.platform(),
           "script": os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else None, "frameworks": {}}
    for name in _FRAMEWORKS:
        module = sys.modules.get(name)
        version = getattr(module, "__version__", None) if module else None
        if version:
            env["frameworks"][name] = str(version)
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            if torch.cuda.is_available():
                env["devices"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
                env["accelerator"] = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                env["accelerator"] = "mps"
            else:
                env["accelerator"] = "cpu"
        except Exception:
            pass
    return env


def _git_commit():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=2,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def _post(url: str, body, timeout: float = 5.0) -> int:
    """HTTP-код ответа; 0 — сервер недоступен."""
    data = json.dumps(body, default=str).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


class Run:
    """Один запуск обучения. Создаётся через mlogger.init()."""

    def __init__(self, project="default", name=None, config=None, tags=None, url=None, total_steps=None,
                 main_metric=None, notes=None, id=None, disabled=False):
        self.id = id or uuid.uuid4().hex[:12]
        self.name = name or f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}-{random.randint(1, 99)}"
        self.project = project
        self.url = (url or os.environ.get("MLOGGER_URL") or DEFAULT_URL).rstrip("/")
        self.config = dict(config or {})
        self.disabled = disabled or os.environ.get("MLOGGER_DISABLED", "") not in ("", "0")
        self._meta = {"id": self.id, "name": self.name, "project": project, "config": self.config,
                      "tags": list(tags or []), "total_steps": total_steps, "main_metric": main_metric,
                      "notes": notes, "host": socket.gethostname(), "created_at": time.time()}
        self._step = -1
        self._buffer: list = []
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._wake = threading.Event()
        self._created = False
        self._finished = False
        self._warned = False
        self._dropped = 0
        self._last_contact = 0.0
        self._error = None
        if self.disabled:
            return
        self._meta["env"] = {**_environment(), "git": _git_commit()}
        self._thread = threading.Thread(target=self._worker, name="mlogger", daemon=True)
        self._thread.start()
        atexit.register(self._atexit)
        _say(f"run '{self.name}' -> {self.url}/#/run/{self.id}")

    def log(self, metrics: dict, step: int | None = None):
        """Записать метрики шага: run.log({"train/loss": 0.42, "val/acc": 0.91}, step=epoch)."""
        if self.disabled or self._finished:
            return
        self._step = int(step) if step is not None else self._step + 1
        now = time.time()
        points = []
        for key, value in _flatten(metrics).items():
            number = _number(value)
            if number is None:
                continue
            points.append({"key": str(key), "step": self._step, "ts": now,
                           "value": number if math.isfinite(number) else None})
        with self._lock:
            self._buffer.extend(points)
            overflow = len(self._buffer) - MAX_BUFFER
            if overflow > 0:
                del self._buffer[:overflow]
                self._dropped += overflow

    def update_config(self, config: dict):
        """Дополнить параметры запуска (гиперпараметры, размер датасета и т.п.)."""
        self.config.update(config)
        self._created = False
        self._wake.set()

    def add_tags(self, *tags: str):
        self._meta["tags"] = list(dict.fromkeys([*self._meta["tags"], *tags]))
        self._created = False
        self._wake.set()

    def finish(self, status: str = "finished", error: str | None = None):
        """Завершить запуск. Вызывается автоматически при выходе из программы."""
        if self.disabled or self._finished:
            return
        global _current
        self._finished = True
        self._wake.set()
        deadline = time.time() + 10
        while time.time() < deadline and self._flush() and self._buffer:
            pass
        body = {"status": status, "error": error, "env": {**_environment(), "git": self._meta["env"].get("git")}}
        delivered = self._created and not self._buffer and _post(f"{self.url}/api/v1/runs/{self.id}/finish", body) == 200
        if not delivered:
            self._spool(body)
        if _current is self:
            _current = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.finish()
        elif issubclass(exc_type, KeyboardInterrupt):
            self.finish("stopped")
        else:
            self.finish("failed", "".join(traceback.format_exception(exc_type, exc, tb))[-2000:])
        return False

    def _ensure_created(self) -> bool:
        if self._created:
            return True
        self._created = True
        code = _post(f"{self.url}/api/v1/runs", self._meta)
        if code != 200:
            self._created = False
            if not self._warned:
                self._warned = True
                reason = "server is not reachable" if code == 0 else f"server answered HTTP {code}"
                _say(f"{reason} at {self.url}; metrics are kept in memory and will be sent later. "
                     "Start the server with start.bat (or: python start.py).")
            return False
        if self._warned:
            _say("server is back, sending buffered metrics")
            self._warned = False
        return True

    def _flush(self) -> bool:
        """Отправляет накопленное. False — сервер недоступен."""
        with self._send_lock:
            if not self._ensure_created():
                return False
            while True:
                with self._lock:
                    batch = self._buffer[:BATCH]
                if not batch:
                    break
                code = _post(f"{self.url}/api/v1/runs/{self.id}/metrics", batch)
                if code == 404:
                    self._created = False
                    return self._ensure_created()
                if code != 200:
                    return False
                with self._lock:
                    del self._buffer[:len(batch)]
                self._last_contact = time.time()
            if time.time() - self._last_contact > HEARTBEAT_INTERVAL and not self._finished:
                env = {**_environment(), "git": self._meta["env"].get("git")}
                if _post(f"{self.url}/api/v1/runs/{self.id}/heartbeat", {"env": env}) == 200:
                    self._last_contact = time.time()
            return True

    def _worker(self):
        _replay_spool(self.url)
        backoff = FLUSH_INTERVAL
        while not self._finished:
            self._wake.wait(backoff)
            self._wake.clear()
            if self._finished:
                break
            backoff = FLUSH_INTERVAL if self._flush() else min(backoff * 2, 15.0)

    def _spool(self, finish_body: dict):
        """Сервер так и не появился — сохраняем запуск на диск, чтобы дослать в следующий раз."""
        try:
            folder = _spool_dir()
            folder.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {"url": self.url, "meta": self._meta, "points": self._buffer, "finish": finish_body}
            (folder / f"{self.id}.json").write_text(json.dumps(payload, default=str), encoding="utf-8")
            _say(f"server was not reachable; run saved to {folder / (self.id + '.json')} "
                 "and will be uploaded on the next mlogger.init()")
        except Exception as e:
            _say(f"could not save unsent metrics: {e}")

    def _atexit(self):
        if self._finished:
            return
        if self._error:
            self.finish(*self._error)
        else:
            self.finish()


def _replay_spool(url: str):
    """Досылает запуски, которые не удалось отправить в прошлый раз."""
    try:
        files = sorted(_spool_dir().glob("*.json"))
    except Exception:
        return
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("url") != url:
                continue
            meta = payload["meta"]
            if _post(f"{url}/api/v1/runs", meta) != 200:
                return
            points = payload.get("points") or []
            for i in range(0, len(points), BATCH):
                if _post(f"{url}/api/v1/runs/{meta['id']}/metrics", points[i:i + BATCH], timeout=30) != 200:
                    return
            if _post(f"{url}/api/v1/runs/{meta['id']}/finish", payload.get("finish") or {}) != 200:
                return
            path.unlink()
            _say(f"uploaded previously unsent run '{meta.get('name')}'")
        except Exception:
            continue


_hook_installed = False


def _install_excepthook():
    """Необработанное исключение помечает запуск как упавший и сохраняет текст ошибки."""
    global _hook_installed
    if _hook_installed:
        return
    _hook_installed = True
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        run = _current
        if run is not None and not run._finished:
            if issubclass(exc_type, KeyboardInterrupt):
                run._error = ("stopped", None)
            else:
                run._error = ("failed", "".join(traceback.format_exception(exc_type, exc, tb))[-2000:])
        previous(exc_type, exc, tb)

    sys.excepthook = hook


def init(project: str = "default", name: str | None = None, config: dict | None = None, tags=None,
         url: str | None = None, total_steps: int | None = None, main_metric: str | None = None,
         notes: str | None = None, id: str | None = None, disabled: bool = False) -> Run:
    """Начать запуск.

    project      группа запусков (одна задача — один проект)
    name         имя запуска; если не задано, придумается само
    config       гиперпараметры: {"lr": 3e-4, "batch_size": 64, ...}
    tags         метки для поиска и фильтрации: ["baseline", "aug"]
    url          адрес сервера (по умолчанию http://127.0.0.1:8765 или переменная MLOGGER_URL)
    total_steps  сколько всего шагов — тогда интерфейс покажет прогресс и оставшееся время
    main_metric  главная метрика запуска, например "val/accuracy"
    id           задайте, чтобы продолжить существующий запуск
    disabled     True — ничего не отправлять (или переменная MLOGGER_DISABLED=1)
    """
    global _current
    if _current is not None and not _current._finished:
        _current.finish()
    _install_excepthook()
    _current = Run(project=project, name=name, config=config, tags=tags, url=url, total_steps=total_steps,
                   main_metric=main_metric, notes=notes, id=id, disabled=disabled)
    return _current


def get_run() -> Run | None:
    return _current


def log(metrics: dict, step: int | None = None):
    """Записать метрики в активный запуск (после mlogger.init())."""
    if _current is None:
        raise RuntimeError("call mlogger.init() before mlogger.log()")
    _current.log(metrics, step)


def finish(status: str = "finished", error: str | None = None):
    if _current is not None:
        _current.finish(status, error)
