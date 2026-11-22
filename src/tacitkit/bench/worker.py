"""One model over the corpus, alone in a fresh process, so its peak memory is its own.

    python -m tacitkit.bench.worker <model> <cases.json> <out.json> --cache <folder> [--threads 2]

Runs at below-normal priority. Writes spans per case id, milliseconds per case (after a
warm-up call), memory after loading and the peak working set of the whole run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from tacitkit.bench import adapters


def memory_mb() -> tuple[float, float]:
    """(current, peak) resident memory of this process in MB."""
    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415
        import ctypes.wintypes as wt  # noqa: PLC0415

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD),
                ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        kernel.GetCurrentProcess.restype = wt.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(Counters), wt.DWORD]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        return counters.WorkingSetSize / 2**20, counters.PeakWorkingSetSize / 2**20
    import resource  # noqa: PLC0415

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = peak / 2**20 if sys.platform == "darwin" else peak / 1024  # bytes on macOS, KB on Linux
    return peak, peak  # no cheap "current" off Windows: the peak after loading stands in


def lower_priority() -> None:
    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415
        import ctypes.wintypes as wt  # noqa: PLC0415

        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = wt.HANDLE
        kernel.SetPriorityClass.argtypes = [wt.HANDLE, wt.DWORD]
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL
    else:
        import os  # noqa: PLC0415

        os.nice(10)


def run(model: str, cases: list[dict], cache: Path, threads: int) -> dict:
    lower_priority()
    detect = adapters.load(adapters.SPECS[model], cache, threads, cases)
    detect("Warm up with Ahmad bin Ismail in Petaling Jaya.")
    loaded = memory_mb()[0]
    spans, times = {}, []
    for item in cases:
        start = time.perf_counter()
        found = detect(item["text"])
        times.append((time.perf_counter() - start) * 1000)
        spans[str(item["id"])] = [list(s) for s in found]
    return {
        "model": model,
        "spans": spans,
        "ms": times,
        "ram_load_mb": loaded,
        "ram_peak_mb": memory_mb()[1],
        "threads": threads,
        "torch_loaded": "torch" in sys.modules,  # proves a "lean" adapter really is lean
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tacitkit.bench.worker")
    parser.add_argument("model")
    parser.add_argument("cases")
    parser.add_argument("out")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args(argv)
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    result = run(args.model, cases, Path(args.cache).resolve(), args.threads)
    Path(args.out).write_text(json.dumps(result), encoding="utf-8")
    print(
        f"{args.model}: {sum(result['ms']) / len(result['ms']):.1f} ms avg, "
        f"peak {result['ram_peak_mb']:.0f} MB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
