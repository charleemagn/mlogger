import { h, clear, icon, codeBlock } from "../dom.js";
import { importDialog, quickstartCode } from "../parts.js";

const SNIPPETS = [
  ["Любой код / PyTorch", (c) => c.basic,
    "Подходит для собственного цикла обучения на PyTorch, JAX, scikit-learn — чём угодно. В log() можно передавать числа, numpy-скаляры и тензоры."],
  ["Keras / TensorFlow", () => `from mlogger.integrations.keras import MLoggerCallback

model.fit(
    x_train, y_train, epochs=20, validation_data=(x_val, y_val),
    callbacks=[MLoggerCallback(project="my-project", config={"lr": 1e-3})],
)`, "Все метрики из model.fit, включая val_*, записываются в конце каждой эпохи."],
  ["PyTorch Lightning", () => `from lightning import Trainer
from mlogger.integrations.lightning import MLoggerLogger

trainer = Trainer(max_epochs=20, logger=MLoggerLogger(project="my-project", name="resnet18"))
trainer.fit(model, datamodule)`, "В MLogger попадёт всё, что модель пишет через self.log(...), и гиперпараметры."],
  ["Ultralytics YOLO", () => `from ultralytics import YOLO
from mlogger.integrations.ultralytics import add_mlogger

model = YOLO("yolo11n.pt")
add_mlogger(model, project="detection")
model.train(data="coco8.yaml", epochs=50)`, "Записываются потери, mAP, precision, recall и learning rate по эпохам, а также все аргументы обучения."],
  ["Hugging Face", () => `from transformers import Trainer
from mlogger.integrations.transformers import MLoggerCallback

trainer = Trainer(model=model, args=args, train_dataset=train, eval_dataset=val,
                  callbacks=[MLoggerCallback(project="bert-finetune")])
trainer.train()`, "Записывается всё, что логирует Trainer: loss, eval_*, learning_rate, grad_norm."],
  ["XGBoost", () => `import xgboost as xgb
from mlogger.integrations.xgboost import MLoggerCallback

xgb.train(params, dtrain, num_boost_round=500,
          evals=[(dtrain, "train"), (dval, "val")],
          callbacks=[MLoggerCallback(project="tabular", config=params)])`, "Метрики всех наборов из evals — после каждой итерации бустинга."],
  ["LightGBM", () => `import lightgbm as lgb
import mlogger
from mlogger.integrations.lightgbm import mlogger_callback

run = mlogger.init(project="tabular", config=params)
lgb.train(params, train_set, valid_sets=[train_set, val_set], valid_names=["train", "val"],
          callbacks=[mlogger_callback(run)])
run.finish()`, "Метрики всех валидационных наборов — после каждой итерации."],
];

export function mount(root, ctx) {
  const code = quickstartCode(ctx.ping);
  const snippet = h("div");
  const tabs = h("div", { class: "tabs", role: "tablist" });
  let active = 0;

  function renderSnippet() {
    clear(tabs, SNIPPETS.map(([label], i) => h("button", { type: "button", role: "tab", "aria-selected": String(i === active), onclick: () => { active = i; renderSnippet(); } }, label)));
    clear(snippet, h("p", { class: "dim", style: { marginBottom: "8px" } }, SNIPPETS[active][2]), codeBlock(SNIPPETS[active][1](code)));
  }

  root.append(
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, "Подключение"), h("div", { class: "sub" }, "Три шага, чтобы обучение появилось в MLogger"))),
    h("div", { class: "card steps" },
      h("div", { class: "step" }, h("div", null,
        h("h3", null, "Установите клиент"),
        h("p", null, "Выполните команду в том окружении Python (venv, conda), где запускается обучение. Пакет маленький и ничего за собой не тянет."),
        codeBlock(code.install))),
      h("div", { class: "step" }, h("div", null,
        h("h3", null, "Добавьте MLogger в код обучения"),
        tabs, snippet)),
      h("div", { class: "step" }, h("div", null,
        h("h3", null, "Запустите обучение"),
        h("p", null, "Запуск сразу появится в разделе «Запуски». Если сервер MLogger в этот момент выключен, обучение не пострадает: метрики сохранятся и загрузятся при следующем запуске.")))),

    h("div", { class: "section" },
      h("h2", null, "Уже есть логи?"),
      h("div", { class: "lead" }, "Код менять не обязательно: MLogger читает results.csv от Ultralytics, файлы событий TensorBoard (их пишут PyTorch Lightning, Keras, Transformers) и папку mlruns от MLflow."),
      h("div", { class: "row" },
        h("button", { class: "btn primary", onclick: () => importDialog((ids) => ctx.navigate(ids.length === 1 ? `#/run/${ids[0]}` : "#/runs")) }, icon("upload", "sm"), "Импортировать логи"),
        h("span", { class: "muted" }, "или из командной строки:")),
      h("div", { style: { marginTop: "10px" } }, codeBlock("python start.py import C:\\путь\\к\\папке\\с\\логами"))),

    h("div", { class: "section" },
      h("h2", null, "Полезные мелочи"),
      h("div", { class: "grid two" },
        h("div", { class: "card" }, h("h3", null, "Как называть метрики"),
          h("p", { class: "dim", style: { marginTop: "6px" } }, "Пишите train/loss и val/loss (или train_loss, val_loss) — тогда MLogger нарисует их на одном графике и сможет заметить переобучение. Метрики качества узнаёт по названию: accuracy, f1, mAP, auc, iou и другие.")),
        h("div", { class: "card" }, h("h3", null, "Метки и параметры"),
          h("p", { class: "dim", style: { marginTop: "6px" } }, "tags=[...] в mlogger.init() — метки для поиска и фильтров; их можно править и в интерфейсе. config={...} — гиперпараметры: по ним удобно сравнивать запуски.")),
        h("div", { class: "card" }, h("h3", null, "Прогресс и оставшееся время"),
          h("p", { class: "dim", style: { marginTop: "6px" } }, "Передайте total_steps — общее число шагов или эпох. MLogger покажет полосу прогресса и оценит, сколько осталось.")),
        h("div", { class: "card" }, h("h3", null, "Сервер на другом адресе"),
          h("p", { class: "dim", style: { marginTop: "6px" } }, "По умолчанию клиент пишет на http://127.0.0.1:8765. Другой адрес задаётся параметром url=... или переменной окружения MLOGGER_URL. MLOGGER_DISABLED=1 отключает отправку.")))));
  renderSnippet();
  return {};
}
