"""Любые видеокарты в Windows (AMD, Intel, NVIDIA, Qualcomm) — теми же счётчиками, что и Диспетчер задач.

Список карт и объём памяти берём из DXGI, загрузку и занятую память — из счётчиков
производительности «GPU Engine» и «GPU Adapter Memory» (Windows 10 1709+).
Температуру и мощность Windows сама не отдаёт — для них нужен инструмент производителя.
"""

from __future__ import annotations

import ctypes
import re
from ctypes import wintypes as wt

VENDORS = {0x10DE: "NVIDIA", 0x1002: "AMD", 0x1022: "AMD", 0x8086: "Intel", 0x5143: "Qualcomm", 0x1414: "Microsoft"}
_SOFTWARE_FLAG = 2
_PDH_FMT_DOUBLE = 0x00000200
_PDH_MORE_DATA = 0x800007D2
_LUID_RE = re.compile(r"luid_0x([0-9a-f]+)_0x([0-9a-f]+)", re.I)
_ENG_RE = re.compile(r"_eng_(\d+)")


class _GUID(ctypes.Structure):
    _fields_ = [("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", ctypes.c_ubyte * 8)]


class _LUID(ctypes.Structure):
    _fields_ = [("low", wt.DWORD), ("high", wt.LONG)]


class _DESC1(ctypes.Structure):
    _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", wt.UINT), ("DeviceId", wt.UINT),
                ("SubSysId", wt.UINT), ("Revision", wt.UINT), ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t), ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", _LUID), ("Flags", wt.UINT)]


class _VALUE(ctypes.Structure):
    _fields_ = [("CStatus", wt.DWORD), ("doubleValue", ctypes.c_double)]


class _ITEM(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _VALUE)]


def _method(obj: ctypes.c_void_p, index: int, *argtypes):
    """Метод COM-объекта по номеру в таблице виртуальных функций."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])


def adapters() -> list:
    """Физические видеоадаптеры: имя, производитель, память и LUID для связи со счётчиками."""
    dxgi = ctypes.WinDLL("dxgi")
    iid = _GUID(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    factory = ctypes.c_void_p()
    dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    dxgi.CreateDXGIFactory1.restype = ctypes.c_long
    if dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0 or not factory:
        return []
    found, seen = [], set()
    try:
        enum = _method(factory, 12, wt.UINT, ctypes.POINTER(ctypes.c_void_p))
        i = 0
        while True:
            adapter = ctypes.c_void_p()
            if enum(factory, i, ctypes.byref(adapter)) != 0 or not adapter:
                break
            i += 1
            desc = _DESC1()
            ok = _method(adapter, 10, ctypes.POINTER(_DESC1))(adapter, ctypes.byref(desc)) == 0
            _method(adapter, 2)(adapter)
            luid = (desc.AdapterLuid.high & 0xFFFFFFFF, desc.AdapterLuid.low)
            if not ok or desc.Flags & _SOFTWARE_FLAG or desc.VendorId == 0x1414 or luid in seen:
                continue
            seen.add(luid)
            dedicated = desc.DedicatedVideoMemory
            integrated = dedicated < 512 * 1024 * 1024
            found.append({"luid": luid, "name": desc.Description.strip(),
                          "vendor": VENDORS.get(desc.VendorId, f"0x{desc.VendorId:04X}"),
                          "integrated": integrated,
                          "mem_total": desc.SharedSystemMemory if integrated else dedicated})
    finally:
        _method(factory, 2)(factory)
    return found


class _Counters:
    def __init__(self):
        self.pdh = pdh = ctypes.WinDLL("pdh")
        pdh.PdhOpenQueryW.argtypes = [wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
        pdh.PdhAddEnglishCounterW.argtypes = [wt.HANDLE, wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
        pdh.PdhCollectQueryData.argtypes = [wt.HANDLE]
        pdh.PdhGetFormattedCounterArrayW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.DWORD),
                                                     ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
        pdh.PdhCloseQuery.argtypes = [wt.HANDLE]
        for fn in (pdh.PdhOpenQueryW, pdh.PdhAddEnglishCounterW, pdh.PdhCollectQueryData,
                   pdh.PdhGetFormattedCounterArrayW, pdh.PdhCloseQuery):
            fn.restype = wt.DWORD
        self.query = wt.HANDLE()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.query)) != 0:
            raise OSError("PdhOpenQuery failed")
        self.util = self._add(r"\GPU Engine(*)\Utilization Percentage")
        self.dedicated = self._add(r"\GPU Adapter Memory(*)\Dedicated Usage")
        self.shared = self._add(r"\GPU Adapter Memory(*)\Shared Usage")
        if not self.util and not self.dedicated:
            raise OSError("GPU performance counters are not available")
        pdh.PdhCollectQueryData(self.query)

    def _add(self, path: str):
        handle = wt.HANDLE()
        return handle if self.pdh.PdhAddEnglishCounterW(self.query, path, 0, ctypes.byref(handle)) == 0 else None

    def collect(self):
        self.pdh.PdhCollectQueryData(self.query)

    def read(self, counter) -> list:
        """[(имя экземпляра, значение)] для счётчика со звёздочкой."""
        if not counter:
            return []
        size, count = wt.DWORD(0), wt.DWORD(0)
        status = self.pdh.PdhGetFormattedCounterArrayW(counter, _PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None)
        if status != _PDH_MORE_DATA or not size.value:
            return []
        buf = ctypes.create_string_buffer(size.value)
        if self.pdh.PdhGetFormattedCounterArrayW(counter, _PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buf) != 0:
            return []
        items = ctypes.cast(buf, ctypes.POINTER(_ITEM))
        return [(items[i].szName or "", items[i].FmtValue.doubleValue) for i in range(count.value)
                if items[i].FmtValue.CStatus in (0, 1)]

    def close(self):
        self.pdh.PdhCloseQuery(self.query)


def _luid(name: str):
    m = _LUID_RE.search(name)
    return (int(m.group(1), 16), int(m.group(2), 16)) if m else None


class WindowsGpu:
    def __init__(self, skip_vendors=()):
        self.adapters = [a for a in adapters() if a["vendor"] not in skip_vendors]
        self.counters = _Counters() if self.adapters else None
        self.available = bool(self.adapters)
        self._fresh, self._age = None, 0

    def _rotate(self):
        """Список процессов в счётчике фиксируется при создании запроса, поэтому запрос
        периодически пересоздаётся — иначе обучение, запущенное позже монитора, не будет видно."""
        if self._fresh:
            self.counters.close()
            self.counters, self._fresh, self._age = self._fresh, None, 0
        self._age += 1
        if self._age >= 5:
            try:
                self._fresh = _Counters()
            except OSError:
                self._age = 0

    def sample(self) -> list:
        if not self.counters:
            return []
        self._rotate()
        self.counters.collect()
        engines: dict = {}
        for name, value in self.counters.read(self.counters.util):
            luid, eng = _luid(name), _ENG_RE.search(name)
            if luid and eng:
                engines[(luid, eng.group(1))] = engines.get((luid, eng.group(1)), 0.0) + value
        util: dict = {}
        for (luid, _), value in engines.items():
            util[luid] = max(util.get(luid, 0.0), value)
        dedicated = {_luid(n): v for n, v in self.counters.read(self.counters.dedicated)}
        shared = {_luid(n): v for n, v in self.counters.read(self.counters.shared)}
        gpus = []
        for i, a in enumerate(self.adapters):
            used = (shared if a["integrated"] else dedicated).get(a["luid"])
            gpus.append({
                "id": f"win:{a['luid'][0]:x}-{a['luid'][1]:x}", "index": i, "name": a["name"], "vendor": a["vendor"],
                "util": round(min(100.0, util[a["luid"]]), 1) if a["luid"] in util else None,
                "mem_used": used, "mem_total": a["mem_total"], "temp": None, "power": None, "fan": None,
            })
        return gpus
