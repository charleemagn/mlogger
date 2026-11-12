"""Готовые обёртки для популярных фреймворков. Каждая импортирует свой фреймворк только при использовании.

    from mlogger.integrations.keras import MLoggerCallback          # Keras / TensorFlow
    from mlogger.integrations.lightning import MLoggerLogger        # PyTorch Lightning
    from mlogger.integrations.ultralytics import add_mlogger        # YOLO
    from mlogger.integrations.transformers import MLoggerCallback   # Hugging Face Trainer
    from mlogger.integrations.xgboost import MLoggerCallback        # XGBoost
    from mlogger.integrations.lightgbm import mlogger_callback      # LightGBM
"""
