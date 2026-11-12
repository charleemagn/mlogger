"""Словарь метрик: что это за число, в какую сторону «лучше» и как объяснить его человеку.

describe("val/box_loss") ->
    {"key": "val/box_loss", "label": "box_loss", "group": "box_loss", "split": "val",
     "kind": "loss", "direction": "min", "title": "...", "hint": "..."}

kind:      loss | score | lr | aux | other
direction: min (меньше — лучше) | max (больше — лучше) | None
split:     train | val | test | None
group:     ключ без train/val — метрики одной группы рисуются на одном графике
"""

from __future__ import annotations

import re

_SPLITS = {
    "train": "train", "training": "train", "trn": "train",
    "val": "val", "valid": "val", "validation": "val", "eval": "val", "dev": "val",
    "test": "test",
}
_SEP = r"[/_.\-\s:]"
_SPLIT_RE = re.compile(rf"(?:^|(?<={_SEP}))({'|'.join(_SPLITS)})(?:{_SEP}+|$)", re.I)
_PREFIX_RE = re.compile(r"^(metrics?|scalars?)[/_.]", re.I)

_MIN_WORDS = ("loss", "error", "err", "mae", "mse", "rmse", "rmsle", "mape", "smape", "perplexity",
              "ppl", "wer", "cer", "nll", "fid", "ece")
_MAX_WORDS = ("accuracy", "acc", "f1", "precision", "recall", "auc", "auroc", "iou", "miou", "dice",
              "bleu", "rouge", "meteor", "psnr", "ssim", "r2", "map", "ap", "top1", "top5", "reward",
              "return", "fitness", "mcc", "kappa", "score")
_AUX_WORDS = ("epoch", "step", "iteration", "iter")

_GLOSSARY = [
    (r"map[_@]?(0?\.?5|50)[\-_:]+(0?\.?)?95", "mAP 50–95",
     "Главная метрика детекторов: насколько точно модель находит объекты, усреднённо по строгим и мягким "
     "порогам совпадения рамок. От 0 до 1, больше — лучше."),
    (r"map[_@]?(0?\.5|50)", "mAP 50",
     "Качество детекции при мягком пороге: рамка считается верной, если совпала с настоящей хотя бы наполовину. "
     "От 0 до 1, больше — лучше."),
    (r"\bmap\b", "mAP", "Средняя точность детекции по всем классам. От 0 до 1, больше — лучше."),
    (r"box[_\s]?loss", "Ошибка рамок", "Насколько предсказанные рамки объектов не совпадают с настоящими. Меньше — лучше."),
    (r"cls[_\s]?loss", "Ошибка классов", "Насколько часто модель путает классы объектов. Меньше — лучше."),
    (r"dfl[_\s]?loss", "Ошибка границ", "Насколько неточно модель определяет края рамок. Меньше — лучше."),
    (r"perplexity|\bppl\b", "Perplexity",
     "Насколько модель «удивляется» тексту. 1 — идеально предсказывает следующее слово, меньше — лучше."),
    (r"loss", "Loss — функция потерь",
     "Показывает, насколько сильно модель ошибается. Важна не сама цифра, а то, что она снижается."),
    (r"acc", "Accuracy — доля верных ответов", "Какую долю примеров модель угадала правильно: 0.9 = 90%. Больше — лучше."),
    (r"precision", "Precision — точность",
     "Из всего, что модель назвала «найдено», какая доля действительно верна. Высокая точность = мало ложных срабатываний."),
    (r"recall", "Recall — полнота",
     "Какую долю настоящих объектов модель нашла. Высокая полнота = мало пропусков."),
    (r"f1", "F1", "Баланс точности и полноты одним числом. От 0 до 1, больше — лучше."),
    (r"auc|auroc", "ROC AUC", "Насколько хорошо модель разделяет классы: 0.5 — как монетка, 1.0 — идеально."),
    (r"iou|dice", "Совпадение областей",
     "Насколько предсказанная область накладывается на настоящую. От 0 до 1, больше — лучше."),
    (r"bleu|rouge|meteor", "Сходство с эталоном", "Насколько сгенерированный текст похож на эталонный. Больше — лучше."),
    (r"psnr|ssim", "Качество изображения", "Насколько восстановленное изображение близко к оригиналу. Больше — лучше."),
    (r"wer|cer", "Доля ошибок распознавания", "Какая доля слов или символов распознана неверно. Меньше — лучше."),
    (r"rmse|mse|mae|mape", "Средняя ошибка", "На сколько в среднем предсказание отличается от правильного числа. Меньше — лучше."),
    (r"\blr\b|learning[_\s]?rate|lr[/_]", "Learning rate — шаг обучения",
     "Насколько сильно модель меняется за один шаг. Слишком большой — loss скачет, слишком маленький — учится медленно."),
    (r"grad[_\s]?norm", "Норма градиента", "Сила «толчка» на каждом шаге. Резкие всплески — признак нестабильного обучения."),
    (r"epoch", "Эпоха", "Номер полного прохода по обучающим данным."),
]
_GLOSSARY = [(re.compile(p, re.I), t, h) for p, t, h in _GLOSSARY]

_SPLIT_NOTE = {
    "train": "Считается на обучающих данных.",
    "val": "Считается на проверочных данных, которых модель не видела, — это честная оценка.",
    "test": "Считается на отложенных тестовых данных.",
}


def _matches(token: str, words) -> bool:
    for w in words:
        if token == w or (token.startswith(w) and re.fullmatch(r"\d*[a-z]?", token[len(w):])):
            return True
    return False


def describe(key: str) -> dict:
    split = None
    m = _SPLIT_RE.search(key)
    label = key
    if m:
        split = _SPLITS[m.group(1).lower()]
        label = (key[:m.start()] + key[m.end():]).strip("/_.- :") or key
    label = _PREFIX_RE.sub("", label) or label
    low = label.lower()
    tokens = [t for t in re.split(r"[/_.\-\s:()@]+", low) if t]

    if re.search(r"(^|[/_.\-\s])lr($|[/_.\-\s\d])|learning[_\s]?rate", low):
        kind, direction = "lr", None
    elif any(t.endswith("loss") or _matches(t, _MIN_WORDS) for t in tokens):
        kind, direction = "loss", "min"
    elif any(_matches(t, _MAX_WORDS) for t in tokens):
        kind, direction = "score", "max"
    elif any(t in _AUX_WORDS for t in tokens) and len(tokens) <= 2:
        kind, direction = "aux", None
    else:
        kind, direction = "other", None

    title, hint = label, ""
    for pattern, t, h in _GLOSSARY:
        if pattern.search(low):
            title, hint = t, h
            break
    if hint and split:
        hint = f"{hint} {_SPLIT_NOTE[split]}"
    return {"key": key, "label": label, "group": low, "split": split, "kind": kind,
            "direction": direction, "title": title, "hint": hint}


_MAIN_ORDER = ("map50-95", "map", "f1", "acc", "auc", "iou", "dice", "bleu", "rouge", "reward")


def pick_main(metas: dict) -> str | None:
    """Главная метрика запуска: сначала качество на проверке, потом loss на проверке, потом что есть."""
    def rank(key):
        m = metas[key]
        if m["kind"] == "score":
            cls = 0 if m["split"] in ("val", "test", None) else 1
        elif m["kind"] == "loss":
            cls = 2 if m["split"] in ("val", "test") else 3
        elif m["kind"] == "other":
            cls = 4
        else:
            cls = 5
        name = next((i for i, w in enumerate(_MAIN_ORDER) if w in m["group"].replace("_", "-")), len(_MAIN_ORDER))
        return (cls, name, len(key), key)
    return min(metas, key=rank) if metas else None
