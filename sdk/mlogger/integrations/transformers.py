"""Hugging Face Transformers (Trainer).

    from mlogger.integrations.transformers import MLoggerCallback
    trainer = Trainer(model=model, args=args, ..., callbacks=[MLoggerCallback(project="bert-finetune")])
"""

from __future__ import annotations

from transformers import TrainerCallback

from .. import run as _run


class MLoggerCallback(TrainerCallback):
    """Аргументы — те же, что у mlogger.init()."""

    def __init__(self, run=None, **init_kwargs):
        self.run = run
        self._kwargs = init_kwargs
        self._own = run is None

    def on_train_begin(self, args, state, control, **kwargs):
        if not state.is_world_process_zero:
            return
        if self.run is None:
            self._kwargs.setdefault("config", args.to_dict())
            self._kwargs.setdefault("total_steps", state.max_steps or None)
            self._kwargs.setdefault("name", getattr(args, "run_name", None))
            self.run = _run.init(**self._kwargs)

    def on_log(self, args, state, control, logs=None, **kwargs):
        if self.run is not None and logs and state.is_world_process_zero:
            self.run.log({k: v for k, v in logs.items() if isinstance(v, (int, float))}, step=state.global_step)

    def on_train_end(self, args, state, control, **kwargs):
        if self.run is not None and self._own and state.is_world_process_zero:
            self.run.finish()
