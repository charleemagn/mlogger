"""LightGBM.

    import mlogger
    from mlogger.integrations.lightgbm import mlogger_callback

    run = mlogger.init(project="tabular", config=params)
    lgb.train(params, train_set, valid_sets=[train_set, val_set], valid_names=["train", "val"],
              callbacks=[mlogger_callback(run)])
    run.finish()
"""

from __future__ import annotations


def mlogger_callback(run):
    """Колбэк, который после каждой итерации пишет все метрики валидации в запуск."""

    def _callback(env):
        metrics = {}
        for item in env.evaluation_result_list or []:
            data, metric, value = item[0], item[1], item[2]
            metrics[f"{data}/{metric}"] = value
        if metrics:
            run.log(metrics, step=env.iteration + 1)

    _callback.order = 20
    return _callback
