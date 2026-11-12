"""Монитор железа: видеокарты любых производителей, процессор и память.

    from monitor import Monitor
    m = Monitor()
    m.sample()  ->  {"ts": ..., "cpu": 12.5, "ram_used": ..., "ram_total": ...,
                     "gpus": [{"id", "index", "name", "vendor", "util", "mem_used", "mem_total",
                               "temp", "power", "fan"}, ...]}

Откуда берутся данные:
  NVIDIA            nvidia-smi (Windows и Linux): загрузка, память, температура, мощность, вентилятор
  AMD/Intel/прочие  Windows: счётчики производительности (загрузка и память, как в Диспетчере задач)
  AMD               Linux: sysfs драйвера amdgpu

Запуск как отдельного агента на другой машине:  python -m monitor --server http://адрес:8765
"""

from __future__ import annotations

import platform
import socket
import sys
import time

from . import system

__all__ = ["Monitor", "hostname"]


def hostname() -> str:
    return socket.gethostname() or "localhost"


def _cpu_name() -> str:
    """Название процессора, как его показывает система («AMD Ryzen 9 ...»), а не «AMD64 Family 26»."""
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        if sys.platform.startswith("linux"):
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.partition(":")[2].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine()


class Monitor:
    def __init__(self):
        self.system = system.create()
        self.backends = []
        self.errors = []
        skip = []
        try:
            from .nvidia import Nvidia
            nv = Nvidia()
            if nv.available:
                self.backends.append(nv)
                skip.append("NVIDIA")
        except Exception as e:
            self.errors.append(f"nvidia: {e}")
        if sys.platform == "win32":
            try:
                from .windows import WindowsGpu
                win = WindowsGpu(skip_vendors=skip)
                if win.available:
                    self.backends.append(win)
            except Exception as e:
                self.errors.append(f"windows: {e}")
        elif sys.platform.startswith("linux"):
            try:
                from .linux import LinuxAmd
                amd = LinuxAmd()
                if amd.available:
                    self.backends.append(amd)
            except Exception as e:
                self.errors.append(f"linux: {e}")

    def info(self) -> dict:
        return {"host": hostname(), "os": f"{platform.system()} {platform.release()}",
                "cpu": _cpu_name(), "python": platform.python_version()}

    def sample(self) -> dict:
        gpus = []
        for backend in self.backends:
            try:
                gpus.extend(backend.sample() or [])
            except Exception:
                continue
        for i, g in enumerate(gpus):
            g["index"] = i
        used, total = self.system.ram()
        return {"ts": time.time(), "cpu": self.system.cpu(), "ram_used": used, "ram_total": total, "gpus": gpus}
