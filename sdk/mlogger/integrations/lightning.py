"""PyTorch Lightning.

    from mlogger.integrations.lightning import MLoggerLogger
    trainer = Trainer(logger=MLoggerLogger(project="cifar10", name="resnet18"))

Всё, что модель пишет через self.log(...), попадёт в MLogger.
"""

from __future__ import annotations

try:
    from lightning.pytorch.loggers.logger import Logger
    from lightning.pytorch.utilities import rank_zero_only
except ImportError:
    from pytorch_lightning.loggers.logger import Logger
    from pytorch_lightning.utilities import rank_zero_only

from .. import run as _run


class MLoggerLogger(Logger):
    """Аргументы — те же, что у mlogger.init()."""

    def __init__(self, run=None, **init_kwargs):
        super().__init__()
        self._run = run
        self._kwargs = init_kwargs

    @property
    def experiment(self):
        if self._run is None:
            self._run = _run.init(**self._kwargs)
        return self._run

    @property
    def name(self):
        return self._kwargs.get("project", "default")

    @property
    def version(self):
        return self._run.id if self._run else None

    @rank_zero_only
    def log_hyperparams(self, params, *args, **kwargs):
        params = vars(params) if hasattr(params, "__dict__") and not isinstance(params, dict) else dict(params or {})
        self.experiment.update_config(params)

    @rank_zero_only
    def log_metrics(self, metrics, step=None):
        self.experiment.log(metrics, step=step)

    @rank_zero_only
    def finalize(self, status):
        if self._run is not None:
            self._run.finish("finished" if status == "success" else "failed" if status == "failed" else "stopped")
