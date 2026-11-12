"""Ultralytics YOLO.

    from ultralytics import YOLO
    from mlogger.integrations.ultralytics import add_mlogger

    model = YOLO("yolo11n.pt")
    add_mlogger(model, project="detection")
    model.train(data="coco8.yaml", epochs=50)
"""

from __future__ import annotations

from .. import run as _run


def add_mlogger(model, run=None, **init_kwargs):
    """Подключает MLogger к модели YOLO. Аргументы — те же, что у mlogger.init()."""
    state = {"run": run, "own": run is None}

    def on_pretrain_routine_start(trainer):
        if state["run"] is None:
            args = vars(trainer.args) if hasattr(trainer.args, "__dict__") else dict(trainer.args)
            init_kwargs.setdefault("name", str(getattr(trainer.args, "name", None) or "") or None)
            init_kwargs.setdefault("config", args)
            init_kwargs.setdefault("total_steps", getattr(trainer, "epochs", None))
            init_kwargs.setdefault("main_metric", "metrics/mAP50-95(B)")
            state["run"] = _run.init(**init_kwargs)

    def on_fit_epoch_end(trainer):
        if state["run"] is None:
            return
        metrics = {}
        try:
            metrics.update(trainer.label_loss_items(trainer.tloss, prefix="train"))
        except Exception:
            pass
        metrics.update(trainer.metrics or {})
        metrics.update(getattr(trainer, "lr", None) or {})
        state["run"].log(metrics, step=trainer.epoch + 1)

    def on_train_end(trainer):
        if state["run"] is not None and state["own"]:
            state["run"].finish()

    model.add_callback("on_pretrain_routine_start", on_pretrain_routine_start)
    model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
    model.add_callback("on_train_end", on_train_end)
    return model
