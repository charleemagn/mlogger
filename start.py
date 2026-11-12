"""MLogger — локальный трекер обучения ML-моделей.

    python start.py                     запустить сервер и открыть интерфейс в браузере
    python start.py --port 9000         другой порт
    python start.py --host 0.0.0.0      принимать данные с других машин в сети
    python start.py import <папка>      загрузить логи Ultralytics / TensorBoard / MLflow
    python start.py demo                добавить демонстрационные запуски

Нужен только Python 3.9+; ничего устанавливать не требуется.
"""

import sys

if sys.version_info < (3, 9):
    sys.exit("MLogger нужен Python 3.9 или новее. Сейчас: " + sys.version.split()[0])

import argparse
import json
import os
import threading
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
DEFAULT_PORT = 8765


def _utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _is_mlogger(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/api/v1/ping", timeout=2) as r:
            return json.load(r).get("app") == "mlogger"
    except (OSError, ValueError):
        return False


def serve(args):
    from server import __version__
    from server.app import App, Server

    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    url = f"http://{shown_host}:{args.port}"
    try:
        server = Server((args.host, args.port), App(args.data))
    except OSError:
        if _is_mlogger(url):
            print(f"MLogger уже запущен: {url}")
            if not args.no_browser:
                webbrowser.open(url)
            return
        sys.exit(f"Порт {args.port} занят другой программой. Запустите с другим портом:  python start.py --port {args.port + 1}")

    print(f"\n  MLogger {__version__}")
    print(f"  Интерфейс:  {url}")
    print(f"  Данные:     {Path(args.data).resolve()}")
    if args.host == "0.0.0.0":
        print("  Сервер доступен другим машинам в сети — защиты паролем нет, используйте только в доверенной сети.")
    print("\n  Чтобы остановить сервер, нажмите Ctrl+C или закройте это окно.\n")
    if not args.no_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Сервер остановлен.")
    finally:
        server.server_close()


def import_logs(args):
    from server.app import App, HttpError

    app = App(args.data, local_monitor=False)
    try:
        ids = app.import_path(args.path, args.project)
    except HttpError as e:
        sys.exit(f"Не получилось: {e.message}")
    print(f"Импортировано запусков: {len(ids)}. Откройте интерфейс:  python start.py")


def demo(args):
    from server import demo as demo_data
    from server.app import App

    url = f"http://127.0.0.1:{args.port}"
    if _is_mlogger(url):
        urllib.request.urlopen(urllib.request.Request(url + "/api/v1/demo", data=b"{}", method="POST",
                                                      headers={"Content-Type": "application/json"}), timeout=30).close()
        print(f"Демо-запуски добавлены. Смотрите: {url}")
        return
    app = App(args.data, local_monitor=False)
    ids = demo_data.create(app.db)
    app.db.finish_run(ids[-1], "stopped")
    print(f"Добавлено демо-запусков: {len(ids)}. Откройте интерфейс:  python start.py")


def main():
    _utf8_console()
    default_data = os.environ.get("MLOGGER_DATA") or str(ROOT / "data")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", default=default_data, help="папка с базой данных (по умолчанию ./data)")
    common.add_argument("--port", type=int, default=int(os.environ.get("MLOGGER_PORT", DEFAULT_PORT)))

    parser = argparse.ArgumentParser(prog="python start.py", parents=[common],
                                     description="MLogger — локальный трекер обучения ML-моделей")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 — принимать данные с других машин")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    sub = parser.add_subparsers(dest="command")
    p_import = sub.add_parser("import", parents=[common], help="загрузить существующие логи обучения")
    p_import.add_argument("path", help="папка запуска Ultralytics, логи TensorBoard или mlruns")
    p_import.add_argument("--project", help="в какой проект положить запуски")
    sub.add_parser("demo", parents=[common], help="добавить демонстрационные запуски")

    args = parser.parse_args()
    {"import": import_logs, "demo": demo, None: serve}[args.command](args)


if __name__ == "__main__":
    main()
