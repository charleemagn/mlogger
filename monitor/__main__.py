"""python -m monitor                     показать, что видит монитор на этой машине
python -m monitor --server URL        присылать показания на сервер MLogger (для обучения на другой машине)

Язык сообщений берётся из системы; задать его явно можно переменной MLOGGER_LANG=ru|en.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from i18n import system_lang

from . import Monitor, hostname

LANG = system_lang()


def _(ru: str, en: str) -> str:
    return ru if LANG == "ru" else en


def _gb(v):
    return f"{v / 2**30:.1f}" if v is not None else "—"


def _show(sample: dict):
    unit = _("ГБ", "GB")
    print(f"CPU {sample['cpu'] if sample['cpu'] is not None else '—'}%   "
          f"RAM {_gb(sample['ram_used'])} / {_gb(sample['ram_total'])} {unit}")
    if not sample["gpus"]:
        print(_("Видеокарты не найдены (или для них нет источника данных).",
                "No GPUs found (or there is no data source for them)."))
    for g in sample["gpus"]:
        extra = "".join(f"   {label} {g[key]:.0f}{suffix}" for key, label, suffix in
                        (("temp", "t", "°C"), ("power", "P", _(" Вт", " W"))) if g.get(key) is not None)
        util = f"{g['util']:.0f}%" if g.get("util") is not None else "—"
        print(f"GPU {g['index']}  [{g['vendor']}] {g['name']}:  {_('загрузка', 'load')} {util}   "
              f"{_('память', 'memory')} {_gb(g.get('mem_used'))} / {_gb(g.get('mem_total'))} {unit}{extra}")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(prog="python -m monitor",
                                     description=_("Монитор железа MLogger", "MLogger hardware monitor"))
    parser.add_argument("--server", help=_("адрес сервера MLogger, например http://192.168.1.10:8765",
                                           "MLogger server address, for example http://192.168.1.10:8765"))
    parser.add_argument("--interval", type=float, default=2.0,
                        help=_("период опроса в секундах", "polling interval in seconds"))
    args = parser.parse_args()

    monitor = Monitor()
    monitor.sample()
    time.sleep(1.0)
    if not args.server:
        _show(monitor.sample())
        for err in monitor.errors:
            print(_("предупреждение:", "warning:"), err)
        return

    url = args.server.rstrip("/") + "/api/v1/system"
    info = monitor.info()
    print(_(f"Отправляю показания «{hostname()}» на {args.server} каждые {args.interval:g} с. Ctrl+C — остановить.",
            f"Sending readings of “{hostname()}” to {args.server} every {args.interval:g} s. Press Ctrl+C to stop."))
    failed = False
    while True:
        body = json.dumps({"host": hostname(), "info": info, "sample": monitor.sample()}).encode()
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).close()
            if failed:
                print(_("Связь с сервером восстановлена.", "Connection to the server is back."))
            failed = False
        except OSError as e:
            if not failed:
                print(_(f"Сервер недоступен ({e}); продолжаю попытки.", f"Server is not reachable ({e}); retrying."))
            failed = True
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
