import { lang, t } from "./i18n.js";

async function request(method, path, body) {
  let res;
  try {
    res = await fetch("/api/v1" + path, {
      method,
      headers: body === undefined ? { "Accept-Language": lang } : { "Accept-Language": lang, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw Object.assign(new Error(t("Сервер MLogger не отвечает. Проверьте, что окно start.bat не закрыто.")), { offline: true });
  }
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok) throw new Error((data && data.error) || t("Ошибка сервера ({0})", [res.status]));
  return data;
}

const q = (params) => {
  const s = new URLSearchParams(Object.entries(params || {}).filter(([, v]) => v != null && v !== "")).toString();
  return s ? "?" + s : "";
};

export const api = {
  ping: () => request("GET", "/ping"),
  overview: (project) => request("GET", "/overview" + q({ project })),
  runs: (project) => request("GET", "/runs" + q({ project })),
  run: (id) => request("GET", `/runs/${id}`),
  patchRun: (id, fields) => request("PATCH", `/runs/${id}`, fields),
  deleteRun: (id) => request("DELETE", `/runs/${id}`),
  metrics: (id, maxPoints = 800) => request("GET", `/runs/${id}/metrics` + q({ max_points: maxPoints })),
  runSystem: (id) => request("GET", `/runs/${id}/system`),
  system: () => request("GET", "/system"),
  importLogs: (path, project) => request("POST", "/import", { path, project }),
  demo: () => request("POST", "/demo", {}),
  deleteDemo: () => request("DELETE", "/demo"),
};
