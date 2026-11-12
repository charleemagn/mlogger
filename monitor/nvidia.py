"""Видеокарты NVIDIA через nvidia-smi (ставится вместе с драйвером, Windows и Linux)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

_FIELDS = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,fan.speed"
_MIB = 1024 * 1024


def _find() -> str | None:
    exe = shutil.which("nvidia-smi")
    if exe:
        return exe
    if sys.platform == "win32":
        guess = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
        if os.path.isfile(guess):
            return guess
    return None


def _num(text: str):
    try:
        return float(text)
    except ValueError:
        return None


class Nvidia:
    vendor = "NVIDIA"

    def __init__(self):
        self.exe = _find()
        self.available = bool(self.exe) and self.sample() is not None

    def sample(self) -> list | None:
        if not self.exe:
            return None
        try:
            out = subprocess.run(
                [self.exe, f"--query-gpu={_FIELDS}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 8:
                continue
            index, name, util, used, total, temp, power, fan = parts[:8]
            used, total = _num(used), _num(total)
            gpus.append({
                "id": f"nvidia:{index}", "index": int(index) if index.isdigit() else len(gpus),
                "name": name, "vendor": self.vendor, "util": _num(util),
                "mem_used": used * _MIB if used is not None else None,
                "mem_total": total * _MIB if total is not None else None,
                "temp": _num(temp), "power": _num(power), "fan": _num(fan),
            })
        return gpus
