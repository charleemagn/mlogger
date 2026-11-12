"""python -m monitor                     показать, что видит монитор на этой машине
python -m monitor --server URL        присылать показания на сервер MLogger (для обучения на другой машине)
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request

from . import Monitor, hostname


def _gb(v):
    return f"{v / 2**30:.1f}" if v is not None else "—"


def _show(sample: dict):
    print(f"CPU {sample['cpu'] if sample['cpu'] is not None else '—'}%   "
          f"RAM {_gb(sample['ram_used'])} / {_gb(sample['ram_total'])} ГБ")
    if not sample["gpus"]:
        print("Видеокарты не найдены (или для них нет источника данных).")
    for g in sample["gpus"]:
        extra = "".join(f"   {label} {g[key]:.0f}{unit}" for key, label, unit in
                        (("temp", "t", "°C"), ("power", "P", " Вт")) if g.get(key) is not None)
        util = f"{g['util']:.0f}%" if g.get("util") is not None else "—"
        print(f"GPU {g['index']}  [{g['vendor']}] {g['name']}:  загрузка {util}   "
              f"память {_gb(g.get('mem_used'))} / {_gb(g.get('mem_total'))} ГБ{extra}")


def main():
    parser = argparse.ArgumentParser(prog="python -m monitor", description="Монитор железа MLogger")
    parser.add_argument("--server", help="адрес сервера MLogger, например http://192.168.1.10:8765")
    parser.add_argument("--interval", type=float, default=2.0, help="период опроса в секундах")
    args = parser.parse_args()

    monitor = Monitor()
    monitor.sample()
    time.sleep(1.0)
    if not args.server:
        _show(monitor.sample())
        for err in monitor.errors:
            print("предупреждение:", err)
        return

    url = args.server.rstrip("/") + "/api/v1/system"
    info = monitor.info()
    print(f"Отправляю показания «{hostname()}» на {args.server} каждые {args.interval:g} с. Ctrl+C — остановить.")
    failed = False
    while True:
        body = json.dumps({"host": hostname(), "info": info, "sample": monitor.sample()}).encode()
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).close()
            if failed:
                print("Связь с сервером восстановлена.")
            failed = False
        except OSError as e:
            if not failed:
                print(f"Сервер недоступен ({e}); продолжаю попытки.")
            failed = True
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
