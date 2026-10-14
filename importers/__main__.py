"""python -m importers <путь> [--source ultralytics|tensorboard|mlflow]"""

import argparse

from . import IMPORTERS, load

parser = argparse.ArgumentParser(prog="python -m importers", description="Показать, что удалось импортировать из логов")
parser.add_argument("path")
parser.add_argument("--source", choices=[i.SOURCE for i in IMPORTERS])
args = parser.parse_args()

for run in load(args.path, args.source):
    print(f"[{run.source}] {run.name}  ({run.path})")
    if run.params:
        print(f"  параметров: {len(run.params)}")
    for key in run.keys():
        points = run.series(key)
        print(f"  {key:<32} точек: {len(points):>6}  шаги {points[0].step}..{points[-1].step}  последнее: {points[-1].value:.6g}")
