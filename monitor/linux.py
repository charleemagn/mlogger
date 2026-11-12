"""Видеокарты AMD в Linux через sysfs (драйвер amdgpu). NVIDIA читается через nvidia-smi."""

from __future__ import annotations

from pathlib import Path


def _read(path: Path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _int(path: Path):
    text = _read(path)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


class LinuxAmd:
    vendor = "AMD"

    def __init__(self):
        self.cards = []
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
            dev = card / "device"
            if "-" in card.name or _read(dev / "vendor") != "0x1002" or not (dev / "gpu_busy_percent").exists():
                continue
            self.cards.append((card.name, dev))
        self.available = bool(self.cards)

    def sample(self) -> list:
        gpus = []
        for i, (card, dev) in enumerate(self.cards):
            hwmon = next(iter(sorted((dev / "hwmon").glob("hwmon*"))), None) if (dev / "hwmon").is_dir() else None
            temp = _int(hwmon / "temp1_input") if hwmon else None
            power = _int(hwmon / "power1_average") if hwmon else None
            name = _read(dev / "product_name") or f"AMD Radeon ({card})"
            gpus.append({
                "id": f"amd:{card}", "index": i, "name": name, "vendor": self.vendor,
                "util": _int(dev / "gpu_busy_percent"),
                "mem_used": _int(dev / "mem_info_vram_used"), "mem_total": _int(dev / "mem_info_vram_total"),
                "temp": temp / 1000 if temp is not None else None,
                "power": power / 1e6 if power is not None else None, "fan": None,
            })
        return gpus
