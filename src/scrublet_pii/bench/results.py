"""Stored results: every run appends a report and a machine-readable record under bench/results/,
and the README index there is rebuilt from all of them, so history and trends stay visible.

Files per run: `<date>-<name>.md` (the report) and `<date>-<name>.json` (the record). Only
synthetic-case results are stored: no raw text, no per-case data, no personal data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


def save(folder: Path, record: dict, report: str) -> Path:
    """Write the run; never overwrite an earlier one (a second run the same day gets -2, -3...)."""
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{record['date']}-{slug(record['name'])}"
    path, n = folder / stem, 1
    while path.with_suffix(".json").exists() or path.with_suffix(".md").exists():
        n += 1
        path = folder / f"{stem}-{n}"
    record = {**record, "report": path.with_suffix(".md").name}
    path.with_suffix(".md").write_text(report, encoding="utf-8")
    path.with_suffix(".json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    index(folder)
    return path.with_suffix(".md")


def ram(model: dict) -> str:
    if model.get("ram_peak_mb"):
        return str(model["ram_peak_mb"])
    return f"{model.get('ram_after_load_mb', 'n/a')} (after load)"


def index(folder: Path) -> Path:
    """Rebuild README.md: one row per run, oldest first, so a column reads as a trend."""
    runs = sorted(
        (json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")),
        key=lambda r: (r["date"], r.get("report", "")),
    )
    lines = [
        "# Bench results",
        "",
        "Every `python -m scrublet_pii.bench bakeoff` run appends here (this table is rebuilt each time). "
        "Synthetic cases only. The winner is the highest names-caught model that passes the run's "
        'decision rule; "none" means no model passed, and the numbers are then for the model the '
        "report picked (or the best by names caught if it picked none).",
        "",
        "| Date | Run | Report | Corpus | Winner | Names caught | Asian | Wrongly hidden | p95 ms | Peak RAM MB | Models |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        models = [m for m in run["models"] if not m.get("is_baseline")] or run["models"]
        pick = next((m for m in models if m["model"] == run.get("winner")), None)
        named = next((m for m in models if m["model"] == run.get("headline_model")), None)
        shown = pick or named or max(models, key=lambda m: m["names_caught_pct"])
        lines.append(
            f"| {run['date']} | {run['name']} | [{run['report']}]({run['report']}) | "
            f"{run['corpus']['hash']} | {pick['label'] if pick else 'none'} | "
            f"{shown['names_caught_pct']:.1f}% | {shown['asian_caught_pct']:.1f}% | "
            f"{shown['wrongly_hidden_pct']:.1f}% | {shown['ms_p95']:.0f} | {ram(shown)} | "
            f"{len(run['models'])} |"
        )
    path = folder / "README.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
