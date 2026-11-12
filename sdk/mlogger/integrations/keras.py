"""Keras / TensorFlow.

    from mlogger.integrations.keras import MLoggerCallback
    model.fit(x, y, epochs=20, validation_data=(xv, yv),
              callbacks=[MLoggerCallback(project="mnist", config={"lr": 1e-3})])
"""

from __future__ import annotations

try:
    import keras
except ImportError:
    from tensorflow import keras

from .. import run as _run


class MLoggerCallback(keras.callbacks.Callback):
    """Пишет метрики в конце каждой эпохи. Аргументы — те же, что у mlogger.init()."""

    def __init__(self, run=None, **init_kwargs):
        super().__init__()
        self.run = run
        self._kwargs = init_kwargs
        self._own = run is None

    def on_train_begin(self, logs=None):
        if self.run is None:
            epochs = (self.params or {}).get("epochs")
            self._kwargs.setdefault("total_steps", epochs)
            self.run = _run.init(**self._kwargs)

    def on_epoch_end(self, epoch, logs=None):
        metrics = dict(logs or {})
        try:
            lr = self.model.optimizer.learning_rate
            metrics.setdefault("lr", float(lr(self.model.optimizer.iterations) if callable(lr) else lr))
        except Exception:
            pass
        self.run.log(metrics, step=epoch + 1)

    def on_train_end(self, logs=None):
        if self._own:
            self.run.finish()
