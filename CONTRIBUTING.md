# Contributing to MLogger

Thanks for taking the time to improve MLogger! Bug reports, ideas and pull requests are all welcome. This guide explains how to report a problem, how the repository is organized and how to get a change merged.

More than anything, a clear bug report or a well-argued feature request helps the project move forward.

## 📝 The best way to contribute: open a great issue

### 🐛 Reporting a bug

Before opening a new issue, please [search the existing ones](https://github.com/charleemagn/mlogger/issues) — the problem may already be known.

A good bug report contains:

- what you did, what you expected and what happened instead
- a minimal way to reproduce it: a short script, or the exact steps in the interface
- the output of the console window where `start.bat` or `start.py` is running, if there is any
- your operating system, Python version and, for hardware issues, the output of `python -m monitor`

Use the [bug report template](https://github.com/charleemagn/mlogger/issues/new/choose): it asks for all of this.

### ✨ Requesting a feature

Describe the problem you are trying to solve first, and the solution you have in mind second. A concrete example ("I train on two machines and want to see both in one list") is worth more than an abstract request.

## 🏡 Set up MLogger locally

MLogger has no third-party dependencies, so there is nothing to install for the server:

```bash
git clone https://github.com/charleemagn/mlogger.git
cd mlogger
python start.py
```

To work on the client, install it in editable mode into the environment you train in:

```bash
pip install -e sdk
```

The interface is plain JavaScript without a build step: edit a file in `ui/`, reload the page.

## 🧱 Structure of the repository

- `start.py`, `start.bat`, `start.sh` — entry points
- `server/` — the HTTP server and the SQLite storage
- `ui/` — the web interface
- `sdk/` — the client package `mlogger` and the framework integrations
- `monitor/` — the hardware monitor for GPUs, CPU and memory
- `diagnostics/` — the training diagnosis and the metric glossary
- `importers/` — importers for Ultralytics, TensorBoard and MLflow logs
- `i18n/` — helpers for the two interface languages, Russian and English
- `demo/` — runnable examples
- `test/` — tests
- `readme_files/` — images for the README; `readme_files/ru/` holds the Russian README and its screenshots

## 🚀 Run MLogger

```bash
python start.py --no-browser --port 8765
```

Use a separate data folder while developing, so you do not touch your real history:

```bash
python start.py --data ./data-dev
```

`python start.py demo` adds demo runs, and `python demo/quickstart.py` sends a simulated training run through the real client.

## 🧪 Testing

The tests use only the standard library. They start a server on a free port with a temporary database, so your data is never touched:

```bash
python -m unittest discover test
```

Please add or update a test when you change behavior. The same command runs in CI on Linux and Windows for every pull request.

A few ground rules for the code:

- **No third-party dependencies** in `server/`, `monitor/`, `diagnostics/`, `importers/`, `ui/` or the core of `sdk/`. This is what lets people run MLogger with a double click.
- **Keep Python 3.9 compatible.**
- **The client must never break training.** Network errors are swallowed, work happens off the main thread.
- **Interface text is user-facing.** Write it for someone who is not an ML engineer.

## 🌍 Languages

MLogger speaks Russian and English, and every user-facing text must exist in both.

- **Interface (`ui/js/`)** — write the Russian text in the code and wrap it in `t("...")`; add the English translation to `ui/js/lang/en.js` under the same key. Values go into the text through numbered placeholders: `t("Удалить запуск «{0}»?", [name])`.
- **Server, diagnosis and glossary** — build texts with `T("русский", "English")` from the `i18n` package. The API returns them in the language of the request.
- **Command line** — `start.py` and `monitor/__main__.py` use a local `_("русский", "English")` helper.
- **README** — `README.md` is the English version and `readme_files/ru/README.md` the Russian one; keep them in sync.

The tests fail if an interface string has no English translation or if Russian text is left outside `t()`.

## 📮 Submitting PRs

1. Open an issue first for anything larger than a small fix, so the approach can be agreed on.
2. Fork the repository and create a branch from `main`.
3. Make your change and run the tests.
4. Add a line to [CHANGELOG.md](CHANGELOG.md) under the upcoming version.
5. Open a pull request and fill in the template.

Small, focused pull requests are reviewed faster than large ones.

## ❓ Need help or have questions?

Open an [issue](https://github.com/charleemagn/mlogger/issues/new/choose) — questions are welcome there too.

## 🚧 Troubleshooting

- **"Port 8765 is in use"** — another program has the port. Start with `python start.py --port 8766` and point the client at it with `MLOGGER_URL`.
- **The run does not appear** — check that the client and the server use the same address, and look at the first lines your training script prints: the client reports where it sends data.
- **No GPU on the hardware page** — run `python -m monitor` and include its output in your bug report.
