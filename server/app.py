"""HTTP-сервер MLogger: REST API + раздача веб-интерфейса. Только стандартная библиотека."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .db import DB
from .summary import build_summary, series_payload, system_payload

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
MAX_BODY = 64 * 1024 * 1024
SAMPLE_INTERVAL = 2.0
PERSIST_INTERVAL = 5.0
RING_SIZE = 450
SUMMARY_MIN_AGE = 3.0

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
        ".svg": "image/svg+xml", ".ico": "image/x-icon", ".json": "application/json"}


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


class SystemStore:
    """Показания железа: свежие — в памяти, история — в базе и только на время обучения."""

    def __init__(self, db: DB):
        self.db = db
        self.lock = threading.Lock()
        self.rings: dict = {}
        self.infos: dict = {}
        self._persisted: dict = {}
        self._running = (0.0, False)

    def _training(self) -> bool:
        checked, value = self._running
        if time.time() - checked > 5:
            value = self.db.has_running()
            self._running = (time.time(), value)
        return value

    def add(self, host: str, sample: dict, info: dict | None = None):
        with self.lock:
            self.rings.setdefault(host, deque(maxlen=RING_SIZE)).append(sample)
            if info and self.infos.get(host) != info:
                self.infos[host] = info
                self.db.save_host(host, info)
        if self._training() and sample["ts"] - self._persisted.get(host, 0) >= PERSIST_INTERVAL:
            self._persisted[host] = sample["ts"]
            self.db.add_sample(host, sample)

    def live(self) -> list:
        now = time.time()
        with self.lock:
            hosts = [(h, list(ring), self.infos.get(h, {})) for h, ring in self.rings.items()]
        out = []
        for host, samples, info in hosts:
            if not samples or now - samples[-1]["ts"] > 120:
                continue
            out.append({"host": host, "info": info, "latest": samples[-1], "online": now - samples[-1]["ts"] < 15,
                        "history": system_payload(samples, now, 300)})
        return out


class App:
    def __init__(self, data_dir: str | Path, local_monitor: bool = True):
        self.data_dir = Path(data_dir)
        self.db = DB(self.data_dir / "mlogger.db")
        self.system = SystemStore(self.db)
        self.monitor_errors: list = []
        self._summary_lock = threading.Lock()
        if local_monitor:
            threading.Thread(target=self._monitor_loop, name="mlogger-monitor", daemon=True).start()

    def _monitor_loop(self):
        try:
            from monitor import Monitor, hostname
            monitor = Monitor()
            self.monitor_errors = monitor.errors
            host, info = hostname(), monitor.info()
            monitor.sample()
        except Exception as e:
            self.monitor_errors = [str(e)]
            return
        while True:
            time.sleep(SAMPLE_INTERVAL)
            try:
                self.system.add(host, monitor.sample(), info)
            except Exception:
                continue

    def summarized(self, run: dict) -> dict:
        """Запуск с актуальной сводкой; для идущих запусков пересчёт не чаще раза в несколько секунд."""
        summary = run.get("summary")
        stale = run["dirty"] or not summary
        if run["status"] == "running" and summary and time.time() - summary.get("built_at", 0) < SUMMARY_MIN_AGE:
            stale = False
        elif run["status"] == "running" and summary and summary.get("hw") is not None:
            stale = True
        if stale:
            with self._summary_lock:
                summary = build_summary(self.db, run)
                self.db.save_summary(run["id"], summary)
            run["summary"] = summary
        run.pop("dirty", None)
        return run

    def runs(self, project: str | None = None) -> list:
        self.db.mark_stale()
        return [self.summarized(r) for r in self.db.list_runs(project)]

    def run(self, run_id: str) -> dict:
        self.db.mark_stale()
        run = self.db.get_run(run_id)
        if not run:
            raise HttpError(404, "запуск не найден")
        return self.summarized(run)

    def import_path(self, path: str, project: str | None = None) -> list:
        from importers import load

        target = Path(path.strip().strip('"')).expanduser()
        try:
            imported = load(target)
        except FileNotFoundError:
            raise HttpError(400, f"путь не найден: {target}")
        except ValueError:
            raise HttpError(400, "в этой папке нет логов Ultralytics (results.csv), TensorBoard (events.out.tfevents.*) "
                                 "или MLflow (mlruns)")
        created = []
        for item in imported:
            if not item.metrics:
                continue
            run_id = hashlib.sha1(f"{item.source}|{item.path.resolve()}|{item.name}".encode()).hexdigest()[:12]
            stamps = [m.ts for m in item.metrics if m.ts]
            started = min(stamps) if stamps else item.path.stat().st_mtime
            self.db.delete_run(run_id)
            self.db.create_run({"id": run_id, "name": item.name, "project": project or item.source,
                                "source": item.source, "status": "finished", "created_at": started,
                                "finished_at": max(stamps) if stamps else started, "config": item.params,
                                "tags": [item.source], "env": {"imported_from": str(item.path)}})
            self.db.add_metrics(run_id, item.to_payload())
            created.append(run_id)
        if not created:
            raise HttpError(400, "логи найдены, но числовых метрик в них нет")
        return created


def _fmt(v) -> str:
    if v is None:
        return "—"
    a = abs(v)
    if a >= 100:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.3f}".rstrip("0").rstrip(".")
    return f"{v:.4f}".rstrip("0").rstrip(".") if a >= 0.001 or a == 0 else f"{v:.2e}"


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} {few}"
    return f"{n} {many}"


def insights(runs: list) -> list:
    """Короткие выводы по набору запусков — то, что человек сказал бы, посмотрев на все графики."""
    out = []
    if not runs:
        return out
    groups: dict = {}
    for r in runs:
        main = r["summary"]["main_key"]
        info = r["summary"]["keys"].get(main) if main else None
        if info and info.get("direction") and info.get("best") is not None:
            groups.setdefault((r["project"], main), []).append((r, info))
    if groups:
        (project, main), items = max(groups.items(), key=lambda kv: (len(kv[1]), kv[1][0][0]["created_at"]))
        sign = -1 if items[0][1]["direction"] == "min" else 1
        best_run, best = max(items, key=lambda it: sign * it[1]["best"])
        text = f"Лучший результат в проекте «{project}» — у запуска «{best_run['name']}»: {main} = {_fmt(best['best'])}"
        if len(items) > 1:
            others = sorted((it[1]["best"] for it in items if it[0] is not best_run), reverse=sign > 0)
            text += f" (следующий — {_fmt(others[0])})"
        out.append({"level": "ok", "text": text + ".", "run": best_run["id"]})

    by_code: dict = {}
    for r in runs:
        for f in r["summary"]["diagnosis"]["findings"]:
            by_code.setdefault(f["code"], []).append(r)
    names = lambda rs: ", ".join(f"«{r['name']}»" for r in rs[:3]) + (" и другие" if len(rs) > 3 else "")

    if by_code.get("overfit"):
        rs = by_code["overfit"]
        out.append({"level": "warn", "run": rs[0]["id"],
                    "text": f"{_plural(len(rs), 'запуск переобучился', 'запуска переобучились', 'запусков переобучились')}: "
                            f"{names(rs)}. Лучше взять более ранний чекпойнт — он указан в диагнозе запуска."})
    broken = (by_code.get("nan") or []) + [r for r in by_code.get("diverge") or [] if r not in (by_code.get("nan") or [])]
    if broken:
        out.append({"level": "crit", "run": broken[0]["id"],
                    "text": f"{_plural(len(broken), 'запуск развалился', 'запуска развалились', 'запусков развалились')} "
                            f"(NaN или рост loss): {names(broken)}. Обычно причина — слишком большой learning rate."})
    if by_code.get("gpu_low"):
        rs = by_code["gpu_low"]
        out.append({"level": "warn", "run": rs[0]["id"],
                    "text": f"В {_plural(len(rs), 'запуске', 'запусках', 'запусках')} видеокарта простаивала ({names(rs)}): "
                            "обучение можно ускорить, если быстрее подавать данные."})
    if by_code.get("vram_full"):
        rs = by_code["vram_full"]
        out.append({"level": "warn", "run": rs[0]["id"],
                    "text": f"Видеопамять была на пределе: {names(rs)}. Есть риск падения с Out of Memory."})
    live = [r for r in runs if r["status"] == "running"]
    plateau = [r for r in live if r["summary"]["diagnosis"]["verdict"]["code"] == "plateau"]
    if plateau:
        out.append({"level": "info", "run": plateau[0]["id"],
                    "text": f"Идущий запуск {names(plateau)} вышел на плато — возможно, его уже можно останавливать."})
    healthy = [r for r in runs if (r["summary"]["diagnosis"]["health"] or 0) >= 80]
    judged = [r for r in runs if r["summary"]["diagnosis"]["health"] is not None]
    if len(judged) >= 3:
        out.append({"level": "info", "run": None,
                    "text": f"{len(healthy)} из {len(judged)} оценённых запусков прошли без серьёзных замечаний."})
    return out


def overview(app: App, project: str | None) -> dict:
    runs = app.runs(project)
    verdicts: dict = {}
    for r in runs:
        v = r["summary"]["diagnosis"]["verdict"]
        slot = verdicts.setdefault(v["code"], {"code": v["code"], "label": v["label"], "level": v["level"], "count": 0})
        slot["count"] += 1
    health = [r["summary"]["diagnosis"]["health"] for r in runs if r["summary"]["diagnosis"]["health"] is not None]
    return {
        "total": len(runs),
        "running": sum(r["status"] == "running" for r in runs),
        "train_seconds": sum(r["summary"]["duration"] for r in runs),
        "health_avg": sum(health) / len(health) if health else None,
        "verdicts": sorted(verdicts.values(), key=lambda v: -v["count"]),
        "insights": insights(runs),
        "projects": app.db.projects(),
    }


def slim(run: dict) -> dict:
    """Запуск для списка: без спарклайнов всех метрик, только главная."""
    summary = run["summary"]
    keys = {}
    for key, info in summary["keys"].items():
        keys[key] = info if key == summary["main_key"] else {k: v for k, v in info.items() if k != "spark"}
    out = {k: v for k, v in run.items() if k not in ("env", "summary")}
    out["summary"] = {**summary, "keys": keys}
    return out


ROUTES: list = []


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn))
        return fn
    return deco


@route("GET", "/api/v1/ping")
def _ping(app, req):
    from monitor import hostname
    return {"app": "mlogger", "version": __version__, "sdk_path": str(ROOT / "sdk"), "root": str(ROOT),
            "host": hostname(), "monitor_errors": app.monitor_errors}


@route("GET", "/api/v1/overview")
def _overview(app, req):
    return overview(app, req.query.get("project"))


@route("GET", "/api/v1/runs")
def _runs(app, req):
    return {"runs": [slim(r) for r in app.runs(req.query.get("project"))], "projects": app.db.projects()}


@route("POST", "/api/v1/runs")
def _create(app, req):
    return app.db.create_run(req.body if isinstance(req.body, dict) else {})


@route("GET", "/api/v1/runs/([\\w\\-]+)")
def _run(app, req, run_id):
    return app.run(run_id)


@route("PATCH", "/api/v1/runs/([\\w\\-]+)")
def _patch(app, req, run_id):
    if not app.db.update_run(run_id, req.body if isinstance(req.body, dict) else {}):
        raise HttpError(404, "запуск не найден")
    return app.run(run_id)


@route("DELETE", "/api/v1/runs/([\\w\\-]+)")
def _delete(app, req, run_id):
    if not app.db.delete_run(run_id):
        raise HttpError(404, "запуск не найден")
    return {"ok": True}


@route("POST", "/api/v1/runs/([\\w\\-]+)/metrics")
def _metrics_add(app, req, run_id):
    points = req.body.get("points") if isinstance(req.body, dict) else req.body
    if not isinstance(points, list):
        raise HttpError(400, "ожидается список точек [{key, step, value, ts}]")
    if not app.db.heartbeat(run_id):
        raise HttpError(404, "запуск не найден")
    return {"saved": app.db.add_metrics(run_id, points)}


@route("GET", "/api/v1/runs/([\\w\\-]+)/metrics")
def _metrics_get(app, req, run_id):
    run = app.db.get_run(run_id)
    if not run:
        raise HttpError(404, "запуск не найден")
    keys = [k for k in req.query.get("keys", "").split(",") if k] or None
    limit = max(50, min(5000, int(req.query.get("max_points", 800))))
    series = app.db.series(run_id, keys)
    return {"series": {k: series_payload(pts, run["created_at"], limit) for k, pts in series.items()}}


@route("GET", "/api/v1/runs/([\\w\\-]+)/system")
def _run_system(app, req, run_id):
    run = app.db.get_run(run_id)
    if not run:
        raise HttpError(404, "запуск не найден")
    if not run.get("host"):
        return {"host": None, "system": None}
    end = run.get("finished_at") or time.time()
    samples = app.db.samples(run["host"], run["created_at"], end)
    return {"host": run["host"], "system": system_payload(samples, run["created_at"]) if samples else None}


@route("POST", "/api/v1/runs/([\\w\\-]+)/heartbeat")
def _heartbeat(app, req, run_id):
    if not app.db.heartbeat(run_id, req.body.get("env") if isinstance(req.body, dict) else None):
        raise HttpError(404, "запуск не найден")
    return {"ok": True}


@route("POST", "/api/v1/runs/([\\w\\-]+)/finish")
def _finish(app, req, run_id):
    body = req.body if isinstance(req.body, dict) else {}
    if body.get("env"):
        app.db.heartbeat(run_id, body["env"])
    if not app.db.finish_run(run_id, body.get("status") or "finished", body.get("error")):
        raise HttpError(404, "запуск не найден")
    return {"ok": True}


@route("GET", "/api/v1/system")
def _system(app, req):
    return {"hosts": app.system.live(), "errors": app.monitor_errors}


@route("POST", "/api/v1/system")
def _system_add(app, req):
    body = req.body if isinstance(req.body, dict) else {}
    sample, host = body.get("sample"), str(body.get("host") or "")[:100]
    if not host or not isinstance(sample, dict):
        raise HttpError(400, "ожидается {host, sample}")
    sample["ts"] = time.time()
    sample.setdefault("gpus", [])
    app.system.add(host, sample, body.get("info") if isinstance(body.get("info"), dict) else None)
    return {"ok": True}


@route("POST", "/api/v1/import")
def _import(app, req):
    body = req.body if isinstance(req.body, dict) else {}
    if not body.get("path"):
        raise HttpError(400, "укажите путь к папке с логами")
    return {"runs": app.import_path(str(body["path"]), body.get("project") or None)}


@route("POST", "/api/v1/demo")
def _demo(app, req):
    from . import demo
    return {"runs": demo.create(app.db)}


@route("DELETE", "/api/v1/demo")
def _demo_delete(app, req):
    from . import demo
    return {"deleted": demo.remove(app.db)}


class Handler(BaseHTTPRequestHandler):
    server_version = "MLogger/" + __version__
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _same_origin(self) -> bool:
        """Страница с чужого сайта не должна уметь писать в локальный сервер."""
        origin = self.headers.get("Origin")
        if not origin or origin == "null":
            return origin is None
        return urlparse(origin).netloc == self.headers.get("Host")

    def _handle(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.close_connection = True
            return self._json(413, {"error": "слишком большой запрос"})
        raw = self.rfile.read(length) if length else b""
        if not path.startswith("/api/"):
            if self.command not in ("GET", "HEAD"):
                return self._json(405, {"error": "метод не поддерживается"})
            return self._static(path)
        allowed = self.server.allowed_hosts
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if allowed is not None and host not in allowed:
            return self._json(403, {"error": "неизвестный адрес сервера"})
        if self.command != "GET" and not self._same_origin():
            return self._json(403, {"error": "запрос с другого сайта отклонён"})
        try:
            self.query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            self.body = json.loads(raw.decode("utf-8")) if raw else {}
            for method, pattern, fn in ROUTES:
                m = pattern.match(path)
                if m and method == self.command:
                    return self._json(200, fn(self.server.app, self, *m.groups()))
            self._json(404, {"error": "нет такого адреса"})
        except HttpError as e:
            self._json(e.status, {"error": e.message})
        except (ValueError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"некорректный запрос: {e}"})
        except Exception as e:
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def _static(self, path: str):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (UI_DIR / rel).resolve()
        if UI_DIR.resolve() not in target.parents or not target.is_file():
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        self._send(200, target.read_bytes(), MIME.get(target.suffix.lower(), "application/octet-stream"))

    do_GET = do_HEAD = do_POST = do_PATCH = do_DELETE = _handle


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, app: App):
        super().__init__(address, Handler)
        self.app = app
        loopback = address[0] in ("127.0.0.1", "localhost", "::1")
        self.allowed_hosts = {"127.0.0.1", "localhost", "::1"} if loopback else None
