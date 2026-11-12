"""Пример без зависимостей: «обучение» имитируется формулами, зато видно всё, что умеет клиент.

    1. Запустите сервер:   start.bat   (или python start.py)
    2. Запустите пример:   python demo/quickstart.py
    3. Откройте http://127.0.0.1:8765 — запуск появится в списке и будет обновляться на лету.

Если клиент ещё не установлен (pip install ./sdk), пример возьмёт его прямо из папки проекта.
"""

import math
import random
import sys
import time
from pathlib import Path

try:
    import mlogger
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk"))
    import mlogger

EPOCHS = 30
config = {"model": "tiny-cnn", "optimizer": "adam", "lr": 3e-3, "batch_size": 64, "epochs": EPOCHS}

run = mlogger.init(
    project="quickstart",
    config=config,
    tags=["example"],
    total_steps=EPOCHS,
    main_metric="val/accuracy",
)

rng = random.Random(0)
for epoch in range(1, EPOCHS + 1):
    progress = epoch / EPOCHS
    train_loss = 0.15 + 2.1 * math.exp(-5 * progress) + rng.gauss(0, 0.02)
    val_loss = 0.28 + 2.0 * math.exp(-4.5 * progress) + rng.gauss(0, 0.02)
    val_acc = 0.93 - 0.85 * math.exp(-4.5 * progress) + rng.gauss(0, 0.004)
    lr = config["lr"] * 0.5 * (1 + math.cos(math.pi * progress))

    run.log({"train/loss": train_loss, "val/loss": val_loss, "val/accuracy": val_acc, "lr": lr}, step=epoch)
    print(f"epoch {epoch:2d}  train_loss={train_loss:.3f}  val_loss={val_loss:.3f}  val_acc={val_acc:.3f}")
    time.sleep(0.5)

run.finish()
