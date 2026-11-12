"""Словарь метрик: что это за число, в какую сторону «лучше» и как объяснить его человеку.

describe("val/box_loss") ->
    {"key": "val/box_loss", "label": "box_loss", "group": "box_loss", "split": "val",
     "kind": "loss", "direction": "min", "title": ..., "hint": ..., "note": ...}

title, hint и note — тексты сразу на двух языках (см. i18n.T): название метрики,
объяснение простыми словами и пометка, на каких данных она считается.

kind:      loss | score | lr | aux | other
direction: min (меньше — лучше) | max (больше — лучше) | None
split:     train | val | test | None
group:     ключ без train/val — метрики одной группы рисуются на одном графике
"""

from __future__ import annotations

import re

from i18n import T

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
    (r"map[_@]?(0?\.?5|50)[\-_:]+(0?\.?)?95", T("mAP 50–95", "mAP 50–95"),
     T("Главная метрика детекторов: насколько точно модель находит объекты, усреднённо по строгим и мягким "
       "порогам совпадения рамок. От 0 до 1, больше — лучше.",
       "The main metric for detectors: how precisely the model finds objects, averaged over strict and loose "
       "box-overlap thresholds. From 0 to 1, higher is better.")),
    (r"map[_@]?(0?\.5|50)", T("mAP 50", "mAP 50"),
     T("Качество детекции при мягком пороге: рамка считается верной, если совпала с настоящей хотя бы наполовину. "
       "От 0 до 1, больше — лучше.",
       "Detection quality at a loose threshold: a box counts as correct if it overlaps the true one by at least half. "
       "From 0 to 1, higher is better.")),
    (r"\bmap\b", T("mAP", "mAP"),
     T("Средняя точность детекции по всем классам. От 0 до 1, больше — лучше.",
       "Mean detection precision over all classes. From 0 to 1, higher is better.")),
    (r"box[_\s]?loss", T("Ошибка рамок", "Box loss"),
     T("Насколько предсказанные рамки объектов не совпадают с настоящими. Меньше — лучше.",
       "How far the predicted object boxes are from the true ones. Lower is better.")),
    (r"cls[_\s]?loss", T("Ошибка классов", "Class loss"),
     T("Насколько часто модель путает классы объектов. Меньше — лучше.",
       "How often the model confuses object classes. Lower is better.")),
    (r"dfl[_\s]?loss", T("Ошибка границ", "Box edge loss"),
     T("Насколько неточно модель определяет края рамок. Меньше — лучше.",
       "How imprecisely the model locates box edges. Lower is better.")),
    (r"perplexity|\bppl\b", T("Perplexity", "Perplexity"),
     T("Насколько модель «удивляется» тексту. 1 — идеально предсказывает следующее слово, меньше — лучше.",
       "How \"surprised\" the model is by the text. 1 means it predicts the next word perfectly; lower is better.")),
    (r"loss", T("Loss — функция потерь", "Loss"),
     T("Показывает, насколько сильно модель ошибается. Важна не сама цифра, а то, что она снижается.",
       "Shows how wrong the model is. The number itself matters less than the fact that it goes down.")),
    (r"acc", T("Accuracy — доля верных ответов", "Accuracy — share of correct answers"),
     T("Какую долю примеров модель угадала правильно: 0.9 = 90%. Больше — лучше.",
       "The share of examples the model got right: 0.9 = 90%. Higher is better.")),
    (r"precision", T("Precision — точность", "Precision"),
     T("Из всего, что модель назвала «найдено», какая доля действительно верна. Высокая точность = мало ложных срабатываний.",
       "Of everything the model flagged, the share that is actually correct. High precision = few false alarms.")),
    (r"recall", T("Recall — полнота", "Recall"),
     T("Какую долю настоящих объектов модель нашла. Высокая полнота = мало пропусков.",
       "The share of real objects the model found. High recall = few misses.")),
    (r"f1", T("F1", "F1"),
     T("Баланс точности и полноты одним числом. От 0 до 1, больше — лучше.",
       "Precision and recall balanced into one number. From 0 to 1, higher is better.")),
    (r"auc|auroc", T("ROC AUC", "ROC AUC"),
     T("Насколько хорошо модель разделяет классы: 0.5 — как монетка, 1.0 — идеально.",
       "How well the model separates the classes: 0.5 is a coin flip, 1.0 is perfect.")),
    (r"iou|dice", T("Совпадение областей", "Region overlap"),
     T("Насколько предсказанная область накладывается на настоящую. От 0 до 1, больше — лучше.",
       "How much the predicted region overlaps the true one. From 0 to 1, higher is better.")),
    (r"bleu|rouge|meteor", T("Сходство с эталоном", "Similarity to reference"),
     T("Насколько сгенерированный текст похож на эталонный. Больше — лучше.",
       "How close the generated text is to the reference. Higher is better.")),
    (r"psnr|ssim", T("Качество изображения", "Image quality"),
     T("Насколько восстановленное изображение близко к оригиналу. Больше — лучше.",
       "How close the reconstructed image is to the original. Higher is better.")),
    (r"wer|cer", T("Доля ошибок распознавания", "Recognition error rate"),
     T("Какая доля слов или символов распознана неверно. Меньше — лучше.",
       "The share of words or characters recognized incorrectly. Lower is better.")),
    (r"rmse|mse|mae|mape", T("Средняя ошибка", "Average error"),
     T("На сколько в среднем предсказание отличается от правильного числа. Меньше — лучше.",
       "How far, on average, the prediction is from the correct number. Lower is better.")),
    (r"\blr\b|learning[_\s]?rate|lr[/_]", T("Learning rate — шаг обучения", "Learning rate"),
     T("Насколько сильно модель меняется за один шаг. Слишком большой — loss скачет, слишком маленький — учится медленно.",
       "How much the model changes in one step. Too high and the loss jumps around; too low and training is slow.")),
    (r"grad[_\s]?norm", T("Норма градиента", "Gradient norm"),
     T("Сила «толчка» на каждом шаге. Резкие всплески — признак нестабильного обучения.",
       "The size of the \"push\" on each step. Sharp spikes are a sign of unstable training.")),
    (r"epoch", T("Эпоха", "Epoch"),
     T("Номер полного прохода по обучающим данным.", "The number of the full pass over the training data.")),
]
_GLOSSARY = [(re.compile(p, re.I), t, h) for p, t, h in _GLOSSARY]

_SPLIT_NOTE = {
    "train": T("Считается на обучающих данных.", "Computed on the training data."),
    "val": T("Считается на проверочных данных, которых модель не видела, — это честная оценка.",
             "Computed on validation data the model has not seen — an honest estimate."),
    "test": T("Считается на отложенных тестовых данных.", "Computed on held-out test data."),
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
    note = _SPLIT_NOTE[split] if hint and split else ""
    return {"key": key, "label": label, "group": low, "split": split, "kind": kind,
            "direction": direction, "title": title, "hint": hint, "note": note}


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
