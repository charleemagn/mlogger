import { h, icon, ask, toast, fmtGb, fmtNum, fmtDate, fmtDur, statusChip, verdictChip, tagEl } from "./dom.js";
import { meter, sparkline } from "./chart.js";
import { api } from "./api.js";

const pct = (v) => (v == null ? "—" : `${Math.round(v)}%`);

export function gpuMeters(g, { compact = false } = {}) {
  const memPart = g.mem_used != null && g.mem_total ? g.mem_used / g.mem_total : null;
  return h("div", { class: "stack" },
    meter("Загрузка", g.util == null ? null : g.util / 100, pct(g.util)),
    meter("Память", memPart, `${fmtGb(g.mem_used)} / ${fmtGb(g.mem_total)} ГБ`, { warnAt: 88, critAt: 96 }),
    g.temp != null ? meter("Температура", g.temp / 100, `${Math.round(g.temp)} °C`, { warnAt: 80, critAt: 87 }) : null,
    g.power != null && !compact ? h("div", { class: "meter" }, h("span", { class: "name" }, "Мощность"), h("span"), h("span", { class: "val" }, `${Math.round(g.power)} Вт`)) : null,
    g.temp == null && !compact ? h("div", { class: "muted", style: { fontSize: "12.5px" } }, "Температуру и мощность для этой карты система не сообщает.") : null);
}

export function gpuHead(g) {
  return h("div", { class: "gpu-head" }, h("span", { class: "vendor" }, g.vendor || "GPU"), h("b", null, g.name || "Видеокарта"),
    h("span", { class: "muted" }, `GPU ${g.index ?? 0}`));
}

export function mainMetric(run) {
  const key = run.summary.main_key;
  const info = key ? run.summary.keys[key] : null;
  return info && info.best != null ? { key, info } : null;
}

export function runCard(run) {
  const main = mainMetric(run);
  const s = run.summary;
  return h("div", { class: "run-card" },
    h("div", null,
      h("div", { class: "title" }, h("a", { href: `#/run/${run.id}` }, run.name), statusChip(run.status), verdictChip(s.diagnosis)),
      h("div", { class: "meta" },
        h("span", null, run.project), h("span", null, fmtDate(run.created_at)), h("span", null, fmtDur(s.duration)),
        s.progress != null && run.status === "running" ? h("span", null, `${Math.round(s.progress * 100)}%${s.eta != null ? ` · осталось ≈ ${fmtDur(s.eta)}` : ""}`) : null,
        run.tags.map((t) => tagEl(t)))),
    main ? h("div", { class: "metric" },
      h("div", { class: "muted mono", style: { fontSize: "12px" } }, main.key),
      h("b", null, fmtNum(main.info.best)),
      sparkline(main.info.spark, { height: 26 })) : h("div", { class: "metric muted" }, "нет метрик"));
}

export async function importDialog(onDone) {
  const values = await ask({
    title: "Импорт логов обучения",
    text: "Укажите папку с логами на этом компьютере. Поддерживаются Ultralytics YOLO (папка с results.csv), TensorBoard и PyTorch Lightning (events.out.tfevents.*), MLflow (папка mlruns).",
    fields: [
      { name: "path", label: "Путь к папке", placeholder: "C:\\projects\\yolo\\runs\\detect\\train" },
      { name: "project", label: "Проект (необязательно)", placeholder: "по умолчанию — название формата" },
    ],
    ok: "Импортировать",
  });
  if (!values || !values.path) return;
  try {
    const res = await api.importLogs(values.path, values.project);
    toast(`Импортировано запусков: ${res.runs.length}`, "ok");
    onDone && onDone(res.runs);
  } catch (e) {
    toast(e.message, "crit");
  }
}

export function quickstartCode(ping) {
  const sdk = ping ? ping.sdk_path : "путь\\к\\mlogger\\sdk";
  return {
    install: `pip install "${sdk}"`,
    basic: `import mlogger

run = mlogger.init(
    project="my-project",            # одна задача — один проект
    name="resnet18-baseline",        # можно не указывать — имя придумается
    config={"lr": 3e-4, "batch_size": 64, "epochs": 20},
    tags=["baseline"],
    total_steps=20,                  # тогда появятся прогресс и оставшееся время
)

for epoch in range(20):
    train_loss = train_one_epoch(model)          # ваш код
    val_loss, val_acc = evaluate(model)          # ваш код
    run.log({"train/loss": train_loss, "val/loss": val_loss, "val/accuracy": val_acc}, step=epoch + 1)

run.finish()`,
  };
}

export const emptyIcon = (name) => h("div", { class: "muted", style: { marginBottom: "10px" } }, icon(name));
