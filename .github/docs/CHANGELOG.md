# mlogger

## 0.1.0

### Features

- Local server on the Python standard library and SQLite: start it with `start.bat`, `start.sh` or `python start.py`, no installation required.
- Windows app `MLogger.exe`: MLogger in its own window with a tray icon, starting and stopping the local server by itself; built from `desktop/` and published as a self-contained archive.
- Two languages, English and Russian: a switch in the interface, bilingual diagnosis, glossary and error messages, console messages in the system language, and a README in both languages.
- Web interface with an overview, a run list, a run page, run comparison, a hardware page and connection instructions, in light and dark themes.
- Training diagnosis: a verdict and a health score from 0 to 100 with plain-language findings — overfitting, plateau, divergence, NaN, unstable loss, idle GPU, full video memory, overheating.
- Metric glossary: every chart explains what the number means and which direction is better.
- Client package `mlogger` with background delivery, offline buffering and automatic status reporting on crashes.
- Framework integrations for Keras, PyTorch Lightning, Ultralytics YOLO, Hugging Face Transformers, XGBoost and LightGBM.
- Hardware monitor for NVIDIA GPUs on Windows and Linux, any GPU on Windows through performance counters, and AMD GPUs on Linux; a standalone agent for remote machines.
- Tags, search, filters and sorting in the run list.
- Importers for Ultralytics, TensorBoard and MLflow logs, available from the interface and the command line.
- Demo data with typical training scenarios, including a run that trains live.
