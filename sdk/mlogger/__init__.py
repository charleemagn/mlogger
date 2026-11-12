"""MLogger — клиент локального трекера обучения.

    import mlogger

    run = mlogger.init(project="cifar10", name="resnet18", config={"lr": 3e-4}, tags=["baseline"])
    for epoch in range(epochs):
        ...
        run.log({"train/loss": train_loss, "val/loss": val_loss, "val/accuracy": acc}, step=epoch)
    run.finish()

Работает с любым фреймворком: в log() можно передавать обычные числа, numpy-скаляры и тензоры.
Готовые обёртки для Keras, Lightning, Ultralytics, Transformers, XGBoost и LightGBM — в mlogger.integrations.
"""

from .run import Run, finish, get_run, init, log

__version__ = "0.1.0"
__all__ = ["Run", "init", "log", "finish", "get_run"]
