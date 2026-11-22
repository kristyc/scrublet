"""python -m scrublet_pii.bench: bakeoff, export-gliner, models, results.

    python -m scrublet_pii.bench models
    python -m scrublet_pii.bench bakeoff --models current_ner,gliner_multi_pii --cache D:/models --rule slim
    python -m scrublet_pii.bench export-gliner --cache D:/models
    python -m scrublet_pii.bench results

Weights download to --cache at pinned commits and are removed afterwards unless --keep-models.
Only what this run added is removed, by absolute path, and never the cache folder itself if it
already held something.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from scrublet_pii.bench import adapters, cases, report, results, stats

RULES = {
    # Replace the baseline: a clear gain, nothing lost, usable speed and memory.
    "replace": report.Rule(
        min_gain_points=10,
        min_asian_gain=0,
        max_extra_hidden=3,
        max_median_ms=200,
        max_p95_ms=500,
        max_ram_mb=1500,
    ),
    # Slim a model that already won on quality: stay near its full-size numbers in less memory.
    "slim": report.Rule(
        min_caught=77.5, min_asian=95, max_hidden=2.5, max_ram_mb=1500, max_p95_ms=300
    ),
    "none": report.Rule(),
}


def cpu_percent() -> float | None:
    """Whole-PC CPU use over one second, or None where it cannot be read."""

    def times():
        if sys.platform == "win32":
            import ctypes  # noqa: PLC0415
            import ctypes.wintypes as wt  # noqa: PLC0415

            idle, kernel, user = wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            )
            both = [(f.dwHighDateTime << 32) | f.dwLowDateTime for f in (idle, kernel, user)]
            return both[0], both[1] + both[2]
        fields = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        return fields[3] + fields[4], sum(fields)

    try:
        a, b = times()
        time.sleep(1)
        c, d = times()
    except (OSError, ValueError, IndexError):
        return None
    return 100 * (1 - (c - a) / (d - b)) if d > b else None


def wait_for_cpu(limit: float) -> None:
    while (use := cpu_percent()) is not None and use > limit:
        print(f"CPU at {use:.0f}% (limit {limit:.0f}%), waiting 30 s", flush=True)
        time.sleep(30)


def safe_cache(path: str) -> Path:
    cache = Path(path).resolve()
    if cache == Path(cache.anchor) or cache == Path.home().resolve():
        raise SystemExit(
            f"--cache {cache} is a drive root or home folder; name a folder for models"
        )
    return cache


def listing(cache: Path) -> set[str]:
    return {p.name for p in cache.iterdir()} if cache.is_dir() else set()


def hub_listing(cache: Path) -> set[str]:
    return listing(cache / "hub")


def cleanup(cache: Path, before: set[str], hub_before: set[str], existed: bool) -> list[str]:
    """Remove what this run added to `cache`, by absolute path, and nothing else."""
    removed = []
    hub = cache / "hub"
    for name in sorted(hub_listing(cache) - hub_before):
        shutil.rmtree(hub / name, ignore_errors=True)
        removed.append(str(hub / name))
    for name in sorted(listing(cache) - before):
        target = cache / name
        if target.is_dir():
            if name == "hub" and any(target.iterdir()):
                continue  # something else lives in it now: leave it
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
        removed.append(str(target))
    if not existed and cache.is_dir() and not any(cache.iterdir()):
        cache.rmdir()
        removed.append(str(cache))
    return removed


def run_worker(model: str, cases_file: Path, out: Path, cache: Path, threads: int) -> str | None:
    """Run one model in a fresh process; the error text if it failed."""
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "scrublet_pii.bench.worker",
            model,
            str(cases_file),
            str(out),
            "--cache",
            str(cache),
            "--threads",
            str(threads),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if done.returncode != 0 or not out.is_file():
        lines = [x for x in (done.stderr or done.stdout).strip().splitlines() if x.strip()]
        return (lines[-1] if lines else f"exit {done.returncode}")[:300]
    print(done.stdout.strip().splitlines()[-1] if done.stdout.strip() else model, flush=True)
    return None


def host_info() -> dict:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "cpus": os.cpu_count(),
    }


def bakeoff(args) -> int:
    names = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in names if m not in adapters.SPECS]
    if unknown:
        raise SystemExit(f"unknown model(s) {unknown}; run `python -m scrublet_pii.bench models`")
    baseline = args.baseline
    if baseline and baseline not in names:
        names.insert(0, baseline)
    cache = safe_cache(args.cache)
    existed = cache.is_dir()
    before, hub_before = listing(cache), hub_listing(cache)
    cache.mkdir(parents=True, exist_ok=True)
    rule = RULES[args.rule]
    rule = report.Rule(
        **{
            **rule.__dict__,
            **{
                k: v
                for k, v in vars(args).items()
                if k in report.Rule.__dataclass_fields__ and v is not None
            },
        }
    )
    corpus = cases.build()
    info = {
        "hash": cases.corpus_hash(corpus),
        "n": len(corpus),
        "categories": len({c["category"] for c in corpus}),
        "seed": cases.SEED,
    }
    scored, failed, ran = {}, {}, []
    work = Path(tempfile.mkdtemp(prefix="scrublet-bench-"))
    try:
        cases_file = work / "cases.json"
        cases_file.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")
        for name in names:
            spec = adapters.SPECS[name]
            if args.max_cpu:
                wait_for_cpu(args.max_cpu)
            try:
                adapters.fetch(spec, cache)
            except Exception as error:
                failed[name] = f"download failed: {type(error).__name__}"
                continue
            out = work / f"{name}.json"
            error = run_worker(name, cases_file, out, cache, args.threads)
            if error:
                failed[name] = error
                print(f"{name}: skipped ({error})", flush=True)
                continue
            scored[name] = stats.score(
                corpus,
                json.loads(out.read_text()),
                cases.NAME_CATS,
                cases.FACT_CATS,
                cases.ASIAN_CATS,
                cases.AMBIGUOUS,
            )
            ran.append(adapters.SPECS[name])
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if not args.keep_models:
            for path in cleanup(cache, before, hub_before, existed):
                print(f"removed {path}")
    if not ran:
        raise SystemExit("no model ran: " + json.dumps(failed))
    base = baseline if baseline in scored else None
    if baseline and not base:
        print(f"baseline {baseline} did not run; no comparisons", file=sys.stderr)
    rows = report.evaluate(ran, scored, base or "", rule)
    notes = Path(args.notes).read_text(encoding="utf-8") if args.notes else ""
    if failed:
        notes += "\n\n**Did not run:** " + "; ".join(f"{k} ({v})" for k, v in failed.items())
    date = dt.date.today().isoformat()
    text = report.markdown(args.title, date, rows, base or "", rule, info, args.threads, notes)
    record = report.result_json(
        args.title, rows, base or "", rule, info, args.threads, host_info(), date
    )
    record["name"], record["failed"] = args.name, failed
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"report: {Path(args.out).resolve()}")
    if not args.no_store:
        print(f"stored: {results.save(Path(args.results_dir).resolve(), record, text)}")
    return 0


def export_gliner(args) -> int:
    """Export GLiNER multi PII v1 to ONNX with gliner's own export_to_onnx, then slim it: the
    embedding table to int8 (`onnx_emb8`) and, slower, 8-bit MatMul weights (`onnx_emb8_mm8`)."""
    cache = safe_cache(args.cache)
    spec = adapters.SPECS["gliner_multi_pii"]
    adapters.fetch(spec, cache)
    os.environ["HF_HUB_OFFLINE"] = "1"
    from gliner import GLiNER  # noqa: PLC0415

    out = cache / adapters.ONNX_DIR
    model = GLiNER.from_pretrained(adapters._snapshot(spec, cache), local_files_only=True)
    model.eval()
    print(
        model.export_to_onnx(
            out, onnx_filename="model.onnx", quantized_filename="model_int8.onnx", quantize=True
        )
    )
    from onnxruntime.quantization import QuantType, quantize_dynamic  # noqa: PLC0415

    quantize_dynamic(
        str(out / "model.onnx"),
        str(out / "model_emb8.onnx"),
        weight_type=QuantType.QInt8,
        op_types_to_quantize=["Gather"],
        extra_options={"DefaultTensorType": 1},
    )
    print({f.name: f.stat().st_size // 2**20 for f in out.glob("*.onnx")})
    return 0


def models(args) -> int:
    for spec in adapters.SPECS.values():
        print(f"{spec.name:34} {spec.precision:10} {spec.licence}")
        print(f"{'':34} {spec.consequence}")
        if spec.extras:
            print(f"{'':34} needs: {spec.extras}")
    return 0


def show_results(args) -> int:
    print(results.index(Path(args.results_dir).resolve()).read_text(encoding="utf-8"))
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="python -m scrublet_pii.bench", description=__doc__.split("\n\n")[0]
    )
    sub = top.add_subparsers(dest="command", required=True)
    run = sub.add_parser("bakeoff", help="run the corpus over models and write the report")
    run.add_argument("--models", required=True, help="comma-separated names from `models`")
    run.add_argument(
        "--baseline", default="current_ner", help="reference row (default current_ner; '' for none)"
    )
    run.add_argument(
        "--cache", required=True, help="folder for downloaded weights (you choose; never the repo)"
    )
    run.add_argument(
        "--keep-models", action="store_true", help="keep downloaded weights (default: remove them)"
    )
    run.add_argument("--threads", type=int, default=2)
    run.add_argument(
        "--max-cpu", type=float, default=0, help="wait while the PC's CPU use is above this %%"
    )
    run.add_argument("--rule", choices=sorted(RULES), default="replace")
    for field in report.Rule.__dataclass_fields__:
        run.add_argument(
            "--" + field.replace("_", "-"),
            dest=field,
            type=float,
            default=None,
            help="override the rule",
        )
    run.add_argument("--name", default="bakeoff", help="short name for the stored files")
    run.add_argument("--title", default="Name-model bake-off")
    run.add_argument("--notes", help="markdown file added under the recommendation")
    run.add_argument("--out", help="also write the report here")
    run.add_argument("--results-dir", default="bench/results")
    run.add_argument("--no-store", action="store_true", help="do not append to the results folder")
    run.set_defaults(func=bakeoff)
    ex = sub.add_parser("export-gliner", help="make the ONNX variants of GLiNER multi PII v1")
    ex.add_argument("--cache", required=True)
    ex.set_defaults(func=export_gliner)
    sub.add_parser("models", help="list adapters, licences and what each needs").set_defaults(
        func=models
    )
    res = sub.add_parser("results", help="rebuild and print the results index")
    res.add_argument("--results-dir", default="bench/results")
    res.set_defaults(func=show_results)
    return top


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if getattr(args, "baseline", None) == "":
        args.baseline = ""
    return args.func(args)
