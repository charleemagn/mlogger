"""Загрузка процессора и память без psutil: Windows через WinAPI, Linux через /proc."""

from __future__ import annotations

import sys


class _WindowsSystem:
    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        self._ctypes, self._wt, self._mem_cls = ctypes, wt, MEMORYSTATUSEX
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._prev = self._times()

    def _times(self):
        ct, wt = self._ctypes, self._wt
        idle, kernel, user = wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        if not self._k32.GetSystemTimes(ct.byref(idle), ct.byref(kernel), ct.byref(user)):
            return None
        val = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime
        return val(idle), val(kernel) + val(user)

    def cpu(self):
        now, prev = self._times(), self._prev
        self._prev = now
        if not now or not prev or now[1] == prev[1]:
            return None
        busy = 1 - (now[0] - prev[0]) / (now[1] - prev[1])
        return round(max(0.0, min(100.0, 100 * busy)), 1)

    def ram(self):
        m = self._mem_cls()
        m.dwLength = self._ctypes.sizeof(m)
        if not self._k32.GlobalMemoryStatusEx(self._ctypes.byref(m)):
            return None, None
        return m.ullTotalPhys - m.ullAvailPhys, m.ullTotalPhys


class _LinuxSystem:
    def __init__(self):
        self._prev = self._times()

    @staticmethod
    def _times():
        try:
            with open("/proc/stat") as f:
                parts = [int(x) for x in f.readline().split()[1:]]
            return parts[3] + (parts[4] if len(parts) > 4 else 0), sum(parts)
        except (OSError, ValueError, IndexError):
            return None

    def cpu(self):
        now, prev = self._times(), self._prev
        self._prev = now
        if not now or not prev or now[1] == prev[1]:
            return None
        return round(100 * (1 - (now[0] - prev[0]) / (now[1] - prev[1])), 1)

    def ram(self):
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    name, _, rest = line.partition(":")
                    info[name] = int(rest.split()[0]) * 1024
            return info["MemTotal"] - info.get("MemAvailable", info.get("MemFree", 0)), info["MemTotal"]
        except (OSError, ValueError, KeyError):
            return None, None


class _NoSystem:
    def cpu(self):
        return None

    def ram(self):
        return None, None


def create():
    try:
        if sys.platform == "win32":
            return _WindowsSystem()
        if sys.platform.startswith("linux"):
            return _LinuxSystem()
    except Exception:
        pass
    return _NoSystem()
