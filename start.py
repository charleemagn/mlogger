"""MLogger — локальный трекер обучения ML-моделей.

    python start.py                     запустить сервер и открыть интерфейс в браузере
    python start.py --port 9000         другой порт
    python start.py --host 0.0.0.0      принимать данные с других машин в сети
    python start.py import <папка>      загрузить логи Ultralytics / TensorBoard / MLflow
    python start.py demo                добавить демонстрационные запуски

Нужен только Python 3.9+; ничего устанавливать не требуется.
Язык сообщений в консоли берётся из системы; задать его явно можно переменной MLOGGER_LANG=ru|en.
"""

import sys

if sys.version_info < (3, 9):
    sys.exit("MLogger needs Python 3.9 or newer / MLogger нужен Python 3.9 или новее. Now: " + sys.version.split()[0])

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

from i18n import pick, system_lang

LANG = system_lang()


def _(ru: str, en: str) -> str:
    return ru if LANG == "ru" else en


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
            print(_(f"MLogger уже запущен: {url}", f"MLogger is already running: {url}"))
            if not args.no_browser:
                webbrowser.open(url)
            return
        sys.exit(_(f"Порт {args.port} занят другой программой. Запустите с другим портом:  "
                   f"python start.py --port {args.port + 1}",
                   f"Port {args.port} is used by another program. Start on another port:  "
                   f"python start.py --port {args.port + 1}"))

    print(f"\n  MLogger {__version__}")
    print(_(f"  Интерфейс:  {url}", f"  Interface:  {url}"))
    print(_(f"  Данные:     {Path(args.data).resolve()}", f"  Data:       {Path(args.data).resolve()}"))
    if args.host == "0.0.0.0":
        print(_("  Сервер доступен другим машинам в сети — защиты паролем нет, используйте только в доверенной сети.",
                "  The server is open to other machines on the network and has no password — use it on a trusted "
                "network only."))
    print(_("\n  Чтобы остановить сервер, нажмите Ctrl+C или закройте это окно.\n",
            "\n  To stop the server, press Ctrl+C or close this window.\n"))
    if not args.no_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(_("\n  Сервер остановлен.", "\n  Server stopped."))
    finally:
        server.server_close()


def import_logs(args):
    from server.app import App, HttpError

    app = App(args.data, local_monitor=False)
    try:
        ids = app.import_path(args.path, args.project)
    except HttpError as e:
        sys.exit(_("Не получилось: ", "Failed: ") + str(pick(e.message, LANG)))
    print(_(f"Импортировано запусков: {len(ids)}. Откройте интерфейс:  python start.py",
            f"Runs imported: {len(ids)}. Open the interface:  python start.py"))


def demo(args):
    from server import demo as demo_data
    from server.app import App

    url = f"http://127.0.0.1:{args.port}"
    if _is_mlogger(url):
        urllib.request.urlopen(urllib.request.Request(url + "/api/v1/demo", data=b"{}", method="POST",
                                                      headers={"Content-Type": "application/json"}), timeout=30).close()
        print(_(f"Демо-запуски добавлены. Смотрите: {url}", f"Demo runs added. See: {url}"))
        return
    app = App(args.data, local_monitor=False)
    ids = demo_data.create(app.db)
    app.db.finish_run(ids[-1], "stopped")
    print(_(f"Добавлено демо-запусков: {len(ids)}. Откройте интерфейс:  python start.py",
            f"Demo runs added: {len(ids)}. Open the interface:  python start.py"))


def main():
    _utf8_console()
    default_data = os.environ.get("MLOGGER_DATA") or str(ROOT / "data")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", default=default_data,
                        help=_("папка с базой данных (по умолчанию ./data)", "folder with the database (default: ./data)"))
    common.add_argument("--port", type=int, default=int(os.environ.get("MLOGGER_PORT", DEFAULT_PORT)))

    parser = argparse.ArgumentParser(prog="python start.py", parents=[common],
                                     description=_("MLogger — локальный трекер обучения ML-моделей",
                                                   "MLogger — a local tracker for ML model training"))
    parser.add_argument("--host", default="127.0.0.1",
                        help=_("0.0.0.0 — принимать данные с других машин", "0.0.0.0 — accept data from other machines"))
    parser.add_argument("--no-browser", action="store_true", help=_("не открывать браузер", "do not open the browser"))
    sub = parser.add_subparsers(dest="command")
    p_import = sub.add_parser("import", parents=[common],
                              help=_("загрузить существующие логи обучения", "import existing training logs"))
    p_import.add_argument("path", help=_("папка запуска Ultralytics, логи TensorBoard или mlruns",
                                         "an Ultralytics run folder, TensorBoard logs or mlruns"))
    p_import.add_argument("--project", help=_("в какой проект положить запуски", "project to put the runs into"))
    sub.add_parser("demo", parents=[common], help=_("добавить демонстрационные запуски", "add demo runs"))

    args = parser.parse_args()
    {"import": import_logs, "demo": demo, None: serve}[args.command](args)


if __name__ == "__main__":
    main()
