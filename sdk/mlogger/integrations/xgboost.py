"""XGBoost.

    from mlogger.integrations.xgboost import MLoggerCallback
    xgb.train(params, dtrain, num_boost_round=500, evals=[(dtrain, "train"), (dval, "val")],
              callbacks=[MLoggerCallback(project="tabular", config=params)])
"""

from __future__ import annotations

import xgboost as xgb

from .. import run as _run


class MLoggerCallback(xgb.callback.TrainingCallback):
    """Аргументы — те же, что у mlogger.init()."""

    def __init__(self, run=None, **init_kwargs):
        super().__init__()
        self.run = run
        self._kwargs = init_kwargs
        self._own = run is None

    def before_training(self, model):
        if self.run is None:
            self.run = _run.init(**self._kwargs)
        return model

    def after_iteration(self, model, epoch, evals_log):
        metrics = {}
        for data, by_metric in (evals_log or {}).items():
            for metric, history in by_metric.items():
                last = history[-1]
                metrics[f"{data}/{metric}"] = last[0] if isinstance(last, tuple) else last
        if metrics:
            self.run.log(metrics, step=epoch + 1)
        return False

    def after_training(self, model):
        if self._own:
            self.run.finish()
        return model
