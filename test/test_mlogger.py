"""Сквозные тесты: python -m unittest discover test

Сервер поднимается на свободном порту со своей временной базой, так что рабочие данные не трогаются.
"""

import json
import os
import random
import re
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sdk"))

from diagnostics import analyze, describe, pick_main
from i18n import T, localize, request_lang
from server import demo
from server.app import App, Server
from server.summary import downsample


def _series(kind, total=1500):
    rng = random.Random(kind)
    out = {}
    for step in range(total):
        for key, value in demo._scenario(kind, step, total, rng).items():
            out.setdefault(key, []).append((step, value))
    return out


class Glossary(unittest.TestCase):
    def test_describe(self):
        cases = {
            "train/loss": ("loss", "min", "train", "loss"),
            "val_loss": ("loss", "min", "val", "loss"),
            "eval_accuracy": ("score", "max", "val", "accuracy"),
            "metrics/mAP50-95(B)": ("score", "max", None, "map50-95(b)"),
            "val/box_loss": ("loss", "min", "val", "box_loss"),
            "lr/pg0": ("lr", None, None, "lr/pg0"),
            "learning_rate": ("lr", None, None, "learning_rate"),
            "train_loss_step": ("loss", "min", "train", "loss_step"),
            "grad_norm": ("other", None, None, "grad_norm"),
            "epoch": ("aux", None, None, "epoch"),
            "test/f1": ("score", "max", "test", "f1"),
        }
        for key, (kind, direction, split, group) in cases.items():
            d = describe(key)
            self.assertEqual((d["kind"], d["direction"], d["split"], d["group"]), (kind, direction, split, group), key)

    def test_main_metric(self):
        keys = ["train/loss", "val/loss", "val/accuracy", "lr"]
        self.assertEqual(pick_main({k: describe(k) for k in keys}), "val/accuracy")
        keys = ["train/box_loss", "metrics/mAP50(B)", "metrics/mAP50-95(B)", "metrics/precision(B)"]
        self.assertEqual(pick_main({k: describe(k) for k in keys}), "metrics/mAP50-95(B)")
        self.assertEqual(pick_main({k: describe(k) for k in ["loss", "val_loss"]}), "val_loss")


class Diagnosis(unittest.TestCase):
    def verdict(self, kind, **kw):
        return analyze(_series(kind), **kw)

    def test_scenarios(self):
        self.assertEqual(self.verdict("overfit", status="finished")["verdict"]["code"], "overfit")
        self.assertEqual(self.verdict("plateau", status="running")["verdict"]["code"], "plateau")
        self.assertEqual(self.verdict("plateau", status="finished")["verdict"]["code"], "converged")
        self.assertIn(self.verdict("good", status="finished")["verdict"]["code"], ("done", "converged"))
        self.assertGreaterEqual(self.verdict("good", status="finished")["health"], 90)
        self.assertLess(self.verdict("overfit", status="finished")["health"], 85)

    def test_nan_and_divergence(self):
        series = _series("nan", 900)
        self.assertEqual(analyze(series, status="running")["verdict"]["code"], "diverge")
        series["train/loss"].append((900, None))
        result = analyze(series, status="failed", error="RuntimeError: loss is NaN")
        self.assertEqual(result["verdict"]["code"], "nan")
        self.assertLess(result["health"], 30)

    def test_not_enough_data(self):
        result = analyze({"loss": [(0, 1.0), (1, 0.9)]})
        self.assertEqual(result["verdict"]["code"], "early")
        self.assertIsNone(result["health"])
        self.assertEqual(analyze({"speed": [(i, 1.0) for i in range(50)]})["verdict"]["code"], "unknown")

    def test_stuck(self):
        rng = random.Random(1)
        series = {"train/loss": [(i, 2.3 + rng.gauss(0, 0.01)) for i in range(200)]}
        self.assertEqual(analyze(series)["verdict"]["code"], "stuck")

    def test_hardware(self):
        gb = 2 ** 30
        hw = {"samples": 50, "ram_max_pct": 40, "gpus": [
            {"name": "GPU A", "util_avg": 31, "mem_max": 23.8 * gb, "mem_total": 24 * gb, "temp_max": 90}]}
        codes = {f["code"] for f in analyze(_series("good"), status="finished", hw=hw)["findings"]}
        self.assertTrue({"gpu_low", "vram_full", "gpu_hot"} <= codes)


class Languages(unittest.TestCase):
    CYRILLIC = re.compile("[\u0400-\u04FF]")

    def test_diagnosis_exists_in_both_languages(self):
        gb = 2 ** 30
        hw = {"samples": 50, "ram_max_pct": 99, "gpus": [
            {"name": "GPU A", "util_avg": 31, "mem_max": 23.8 * gb, "mem_total": 24 * gb, "temp_max": 90}]}
        for kind, status in (("overfit", "finished"), ("plateau", "running"), ("good", "finished"), ("nan", "running")):
            result = analyze(_series(kind), status=status, hw=hw)
            ru, en = localize(result, "ru"), localize(result, "en")
            for item in (ru, en):
                self.assertIsInstance(item["verdict"]["label"], str)
                for finding in item["findings"]:
                    self.assertIsInstance(finding["title"], str)
                    self.assertIsInstance(finding["text"], str)
            self.assertNotRegex(json.dumps(en, ensure_ascii=False), self.CYRILLIC)
            self.assertRegex(ru["verdict"]["label"], self.CYRILLIC)
        self.assertEqual(localize(analyze(_series("overfit"), status="finished"), "en")["verdict"]["label"], "Overfitting")

    def test_glossary_exists_in_both_languages(self):
        for key in ("val/loss", "train_accuracy", "metrics/mAP50-95(B)", "lr", "grad_norm", "test/f1", "epoch"):
            en = localize(describe(key), "en")
            self.assertTrue(en["hint"], key)
            self.assertNotRegex(json.dumps(en, ensure_ascii=False), self.CYRILLIC)
            self.assertRegex(localize(describe(key), "ru")["hint"], self.CYRILLIC)

    def test_localize_leaves_user_data_alone(self):
        data = {"config": {"ru": 0.5, "en": 0.5}, "keys": {"ru": 1, "en": 2}, "text": T("да", "yes"), "list": [T("а", "a")]}
        self.assertEqual(localize(data, "en"), {"config": {"ru": 0.5, "en": 0.5}, "keys": {"ru": 1, "en": 2},
                                                "text": "yes", "list": ["a"]})

    def test_request_language(self):
        self.assertEqual(request_lang("ru-RU,ru;q=0.9,en;q=0.8"), "ru")
        self.assertEqual(request_lang("en-US,en;q=0.9"), "en")
        self.assertEqual(request_lang("de-DE"), "en")
        self.assertEqual(request_lang(None), "en")

    def test_interface_dictionary_is_complete(self):
        ui = ROOT / "ui" / "js"
        call = re.compile(r'\bt\("((?:[^"\\]|\\.)*)"')
        used = set()
        for path in ui.rglob("*.js"):
            if path.name == "i18n.js" or path.parent.name == "lang":
                continue
            source = path.read_text(encoding="utf-8")
            used.update(json.loads(f'"{m}"') for m in call.findall(source))
            self.assertNotRegex(call.sub("", source), self.CYRILLIC, f"{path.name}: Russian text outside t()")
        raw = (ui / "lang" / "en.js").read_text(encoding="utf-8")
        english = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        self.assertEqual(used - set(english), set(), "strings without an English translation")
        self.assertEqual(set(english) - used, set(), "translations that are no longer used")
        for key, value in english.items():
            self.assertNotRegex(value, self.CYRILLIC, key)
            self.assertEqual(sorted(set(re.findall(r"\{\d+\}", key))), sorted(set(re.findall(r"\{\d+\}", value))), key)


class Downsample(unittest.TestCase):
    def test_keeps_extremes_and_gaps(self):
        pts = [(i, float(i % 50), None) for i in range(10_000)]
        pts[5000] = (5000, 999.0, None)
        pts[7000] = (7000, None, None)
        out = downsample(pts, 400)
        self.assertLessEqual(len(out), 620)
        self.assertIn(999.0, [p[1] for p in out])
        self.assertIn(None, [p[1] for p in out])
        self.assertEqual(out[-1][0], 9999)
        self.assertEqual([p[0] for p in out], sorted(p[0] for p in out))


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["MLOGGER_SPOOL"] = str(Path(cls.tmp.name) / "spool")
        cls.app = App(Path(cls.tmp.name) / "data", local_monitor=False)
        cls.server = Server(("127.0.0.1", 0), cls.app)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.db.close()
        cls.tmp.cleanup()

    def api(self, path, method="GET", body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.load(e)

    def test_sdk_roundtrip(self):
        import mlogger

        run = mlogger.init(project="tests", name="roundtrip", config={"lr": 0.01, "opt": {"name": "adam"}},
                           tags=["a", "b"], url=self.url, total_steps=100, main_metric="val/acc")
        for step in range(100):
            run.log({"train": {"loss": 1 / (step + 1)}, "val/acc": step / 100, "note": "not a number"}, step=step)
        run.log({"train/loss": float("nan")}, step=100)
        run.finish()

        status, data = self.api(f"/api/v1/runs/{run.id}")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "finished")
        self.assertEqual(data["tags"], ["a", "b"])
        self.assertEqual(data["config"]["opt"]["name"], "adam")
        self.assertEqual(data["summary"]["main_key"], "val/acc")
        self.assertEqual(data["summary"]["keys"]["train/loss"]["count"], 101)
        self.assertEqual(data["summary"]["keys"]["train/loss"]["nonfinite"], 1)
        self.assertAlmostEqual(data["summary"]["keys"]["val/acc"]["best"], 0.99)
        self.assertNotIn("note", data["summary"]["keys"])
        self.assertIn("python", data["env"])

        status, data = self.api(f"/api/v1/runs/{run.id}/metrics?keys=val/acc&max_points=50")
        self.assertEqual(list(data["series"]), ["val/acc"])
        self.assertLessEqual(len(data["series"]["val/acc"]["steps"]), 60)

        status, data = self.api(f"/api/v1/runs/{run.id}", "PATCH", {"tags": ["x", "x", " y "], "notes": "привет",
                                                                    "status": "running"})
        self.assertEqual((data["tags"], data["notes"], data["status"]), (["x", "y"], "привет", "finished"))

        status, data = self.api("/api/v1/runs?project=tests")
        self.assertIn(run.id, [r["id"] for r in data["runs"]])
        status, data = self.api("/api/v1/overview")
        self.assertGreaterEqual(data["total"], 1)

        self.assertEqual(self.api(f"/api/v1/runs/{run.id}", "DELETE")[0], 200)
        self.assertEqual(self.api(f"/api/v1/runs/{run.id}")[0], 404)

    def test_failed_run_and_context_manager(self):
        import mlogger

        with self.assertRaises(ZeroDivisionError):
            with mlogger.init(project="tests", name="boom", url=self.url) as run:
                run.log({"loss": 1.0})
                1 / 0
        status, data = self.api(f"/api/v1/runs/{run.id}")
        self.assertEqual(data["status"], "failed")
        self.assertIn("ZeroDivisionError", data["error"])
        self.assertEqual(data["summary"]["diagnosis"]["findings"][0]["code"], "failed")

    def test_offline_spool_is_replayed(self):
        import mlogger
        from mlogger import run as sdk

        dead = "http://127.0.0.1:9"
        run = mlogger.init(project="tests", name="offline", url=dead)
        for step in range(20):
            run.log({"loss": 1 / (step + 1)}, step=step)
        run.finish()
        spool = Path(os.environ["MLOGGER_SPOOL"]) / f"{run.id}.json"
        self.assertTrue(spool.exists())

        payload = json.loads(spool.read_text(encoding="utf-8"))
        payload["url"] = self.url
        spool.write_text(json.dumps(payload), encoding="utf-8")
        sdk._replay_spool(self.url)
        self.assertFalse(spool.exists())
        status, data = self.api(f"/api/v1/runs/{run.id}")
        self.assertEqual((status, data["status"], data["summary"]["keys"]["loss"]["count"]), (200, "finished", 20))

    def test_cross_site_requests_are_rejected(self):
        status, _ = self.api("/api/v1/runs", "POST", {"name": "evil"}, {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        status, _ = self.api("/api/v1/runs", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)
        status, _ = self.api("/api/v1/runs", "POST", {"name": "ok", "project": "tests"}, {"Origin": self.url})
        self.assertEqual(status, 200)

    def test_api_answers_in_the_requested_language(self):
        status, run = self.api("/api/v1/runs", "POST", {"name": "lang", "project": "tests"})
        points = [{"key": "train/loss", "step": i, "value": 2.3} for i in range(40)]
        self.api(f"/api/v1/runs/{run['id']}/metrics", "POST", points)
        self.api(f"/api/v1/runs/{run['id']}/finish", "POST", {"status": "finished"})
        labels = {}
        for lang in ("ru", "en"):
            status, data = self.api(f"/api/v1/runs/{run['id']}", headers={"Accept-Language": lang})
            diagnosis = data["summary"]["diagnosis"]
            self.assertEqual(diagnosis["verdict"]["code"], "stuck")
            self.assertIsInstance(diagnosis["findings"][0]["text"], str)
            self.assertIsInstance(data["summary"]["keys"]["train/loss"]["hint"], str)
            labels[lang] = diagnosis["verdict"]["label"]
            status, listing = self.api("/api/v1/runs?project=tests", headers={"Accept-Language": lang})
            mine = next(r for r in listing["runs"] if r["id"] == run["id"])
            self.assertEqual(mine["summary"]["diagnosis"]["verdict"]["label"], labels[lang])
            status, overview = self.api("/api/v1/overview", headers={"Accept-Language": lang})
            self.assertTrue(all(isinstance(v["label"], str) for v in overview["verdicts"]))
            self.assertTrue(all(isinstance(i["text"], str) for i in overview["insights"]))
        self.assertEqual(labels, {"ru": "Не учится", "en": "Not learning"})
        self.assertEqual(self.api("/api/v1/runs/nope", headers={"Accept-Language": "ru"})[1]["error"], "запуск не найден")
        self.assertEqual(self.api("/api/v1/runs/nope", headers={"Accept-Language": "en"})[1]["error"], "run not found")
        self.assertEqual(self.api("/api/v1/runs/nope")[1]["error"], "run not found")

    def test_static_files(self):
        with urllib.request.urlopen(self.url + "/") as r:
            self.assertIn("text/html", r.headers["Content-Type"])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(self.url + "/../start.py")
        caught.exception.close()

    def test_import_ultralytics(self):
        folder = Path(self.tmp.name) / "runs" / "detect" / "train7"
        folder.mkdir(parents=True)
        rows = ["epoch,train/box_loss,val/box_loss,metrics/mAP50-95(B),lr/pg0"]
        rows += [f"{e},{2 / e:.4f},{2.2 / e:.4f},{0.6 - 0.5 / e:.4f},0.01" for e in range(1, 31)]
        (folder / "results.csv").write_text("\n".join(rows), encoding="utf-8")
        status, data = self.api("/api/v1/import", "POST", {"path": str(folder)})
        self.assertEqual(status, 200)
        status, run = self.api(f"/api/v1/runs/{data['runs'][0]}")
        self.assertEqual((run["name"], run["source"], run["status"]), ("train7", "ultralytics", "finished"))
        self.assertEqual(run["summary"]["main_key"], "metrics/mAP50-95(B)")
        self.assertEqual(self.api("/api/v1/import", "POST", {"path": str(folder)})[1]["runs"], data["runs"])
        self.assertEqual(self.api("/api/v1/import", "POST", {"path": self.tmp.name + "/nope"})[0], 400)

    def test_system_samples_attach_to_run(self):
        status, run = self.api("/api/v1/runs", "POST", {"name": "hw", "project": "tests", "host": "rig-1"})
        gpu = {"id": "g0", "name": "Test GPU", "vendor": "AMD", "util": 20, "mem_used": 2 ** 30, "mem_total": 8 * 2 ** 30}
        self.app.system._running = (0.0, False)
        for i in range(15):
            self.app.system._persisted.clear()
            self.assertEqual(self.api("/api/v1/system", "POST", {"host": "rig-1", "info": {"os": "x"},
                                                                 "sample": {"cpu": 10, "gpus": [gpu]}})[0], 200)
        self.api(f"/api/v1/runs/{run['id']}/metrics", "POST", [{"key": "loss", "step": i, "value": 1 / (i + 1)} for i in range(30)])
        status, data = self.api(f"/api/v1/runs/{run['id']}/system")
        self.assertEqual(len(data["system"]["gpus"][0]["util"]), 15)
        time.sleep(3.2)
        status, data = self.api(f"/api/v1/runs/{run['id']}")
        self.assertIn("gpu_low", [f["code"] for f in data["summary"]["diagnosis"]["findings"]])
        status, data = self.api("/api/v1/system")
        self.assertEqual(data["hosts"][0]["latest"]["gpus"][0]["name"], "Test GPU")
        self.api(f"/api/v1/runs/{run['id']}/finish", "POST", {"status": "finished"})

    def test_demo(self):
        status, data = self.api("/api/v1/demo", "POST", {})
        self.assertEqual(len(data["runs"]), 6)
        status, listing = self.api(f"/api/v1/runs?project={demo.PROJECT}")
        verdicts = {r["name"]: r["summary"]["diagnosis"]["verdict"]["code"] for r in listing["runs"]}
        self.assertEqual(verdicts["resnet50-no-aug"], "overfit")
        self.assertEqual(verdicts["resnet18-lr-0.1"], "nan")
        self.assertEqual(verdicts["mobilenet-v3-small"], "converged")
        self.assertIn(verdicts["resnet18-cosine-randaug"], ("done", "converged"))
        status, data = self.api("/api/v1/overview")
        self.assertTrue(any("resnet18-cosine-randaug" in i["text"] for i in data["insights"]))
        self.assertEqual(self.api("/api/v1/demo", "DELETE")[1]["deleted"], 6)


if __name__ == "__main__":
    unittest.main()
