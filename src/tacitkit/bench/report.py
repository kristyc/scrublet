"""The decision rule, and the product-owner report: rule first, numbers behind every claim.

`evaluate` turns scored runs into rows; `markdown` writes the report; `result_json` the
machine-readable record stored next to it (see results.py).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

from tacitkit.bench import adapters, cases, stats

RULE_LABELS = {
    "names_gain": "names gain",
    "names": "names caught",
    "asian": "Asian names",
    "asian_vs_baseline": "Asian vs baseline",
    "wrong_hides_vs_baseline": "wrong hides vs baseline",
    "wrong_hides": "wrong hides",
    "ram": "peak RAM",
    "median_speed": "median speed",
    "p95_speed": "p95 speed",
}


@dataclass
class Rule:
    """A model is adopted only if it passes every rule that is set (None = not checked).
    Absolute limits are on the model; "gain" and "extra" are against the baseline row."""

    min_gain_points: float | None = None  # names caught, points above the baseline (and not noise)
    min_caught: float | None = None
    min_asian: float | None = None
    min_asian_gain: float | None = None  # Asian names, points above the baseline (0 = no worse)
    max_extra_hidden: float | None = None  # wrongly hidden, points above the baseline
    max_hidden: float | None = None
    max_ram_mb: float | None = None
    max_median_ms: float | None = None
    max_p95_ms: float | None = None

    def describe(self) -> list[str]:
        lines = []
        if self.min_gain_points is not None:
            lines.append(
                f"catches at least **{self.min_gain_points:g} points more names** than the "
                f"baseline, and the gain is not noise (paired McNemar p < {stats.NOISE_P})"
            )
        if self.min_caught is not None:
            lines.append(f"catches **at least {self.min_caught:g}%** of names")
        if self.min_asian is not None:
            lines.append(
                f"catches **at least {self.min_asian:g}%** of Malay, Chinese and Indian names"
            )
        if self.min_asian_gain is not None:
            lines.append(
                "catches Malay, Chinese and Indian names "
                + (
                    "**no worse than** the baseline"
                    if self.min_asian_gain == 0
                    else f"**at least {self.min_asian_gain:g} points better** than the baseline"
                )
            )
        if self.max_extra_hidden is not None:
            lines.append(
                f"wrongly hides **at most {self.max_extra_hidden:g} points more** facts "
                "(dates, amounts, merchants, organisations, places) than the baseline"
            )
        if self.max_hidden is not None:
            lines.append(f"wrongly hides **at most {self.max_hidden:g}%** of facts")
        if self.max_ram_mb is not None:
            lines.append(
                f"uses **at most {self.max_ram_mb:g} MB** of memory at peak (fresh process)"
            )
        if self.max_median_ms is not None:
            lines.append(f"takes **at most {self.max_median_ms:g} ms** per message (median)")
        if self.max_p95_ms is not None:
            lines.append(f"takes **at most {self.max_p95_ms:g} ms** per message at p95")
        return lines

    def check(
        self, s: stats.Scores, base: stats.Scores | None, p_caught: float | None
    ) -> dict[str, bool]:
        out: dict[str, bool] = {}
        if self.min_gain_points is not None:
            out["names_gain"] = (
                bool(base)
                and s.caught - base.caught >= self.min_gain_points
                and (p_caught or 1.0) < stats.NOISE_P
            )
        if self.min_caught is not None:
            out["names"] = s.caught >= self.min_caught
        if self.min_asian is not None:
            out["asian"] = s.asian >= self.min_asian
        if self.min_asian_gain is not None:
            out["asian_vs_baseline"] = bool(base) and s.asian - base.asian >= self.min_asian_gain
        if self.max_extra_hidden is not None:
            out["wrong_hides_vs_baseline"] = (
                bool(base) and s.hidden - base.hidden <= self.max_extra_hidden
            )
        if self.max_hidden is not None:
            out["wrong_hides"] = s.hidden <= self.max_hidden
        if self.max_ram_mb is not None:
            out["ram"] = s.ram_peak_mb <= self.max_ram_mb
        if self.max_median_ms is not None:
            out["median_speed"] = s.ms_median <= self.max_median_ms
        if self.max_p95_ms is not None:
            out["p95_speed"] = s.ms_p95 <= self.max_p95_ms
        return out


@dataclass
class Row:
    spec: adapters.Spec
    scores: stats.Scores
    p_caught: float | None  # against the baseline (None for the baseline itself)
    p_hidden: float | None
    speed_x: float | None  # median speed against the baseline at the same precision
    passes: dict[str, bool]

    @property
    def adopted(self) -> bool:
        return bool(self.passes) and all(self.passes.values())


def evaluate(
    specs: list[adapters.Spec], scored: dict[str, stats.Scores], baseline: str, rule: Rule
) -> list[Row]:
    base = scored.get(baseline)
    by_precision = {
        s.baseline_for: scored[s.name] for s in specs if s.baseline_for and s.name in scored
    }
    rows = []
    for spec in specs:
        s = scored[spec.name]
        is_base = spec.name == baseline
        p_caught = (
            None if is_base or not base else stats.mcnemar(s.flags["names"], base.flags["names"])
        )
        p_hidden = (
            None if is_base or not base else stats.mcnemar(s.flags["facts"], base.flags["facts"])
        )
        ref = by_precision.get(spec.precision)
        speed = s.ms_median / ref.ms_median if ref and ref is not s and ref.ms_median else None
        rows.append(
            Row(
                spec, s, p_caught, p_hidden, speed, {} if is_base else rule.check(s, base, p_caught)
            )
        )
    return rows


def vs(delta: float, p: float | None) -> str:
    if p is None:
        return "baseline"
    return f"{delta:+.1f} pts ({'**within noise**' if p >= stats.NOISE_P else 'p<0.001' if p < 0.001 else f'p={p:.3f}'})"


def table(header: list[str], rows: list[list[str]]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(header) + " |",
            "|" + "---|" * len(header),
            *("| " + " | ".join(r) + " |" for r in rows),
        ]
    )


def recommendation(rows: list[Row], baseline: str) -> str:
    contenders = [r for r in rows if r.spec.name != baseline]
    adopted = sorted((r for r in contenders if r.adopted), key=lambda r: -r.scores.caught)
    if adopted:
        top = adopted[0]
        return (
            f"**Adopt {top.spec.label}.** It passes every rule: {top.scores.caught:.1f}% of names caught, "
            f"{top.scores.asian:.1f}% of Asian names, {top.scores.hidden:.1f}% of facts wrongly hidden, "
            f"{top.scores.ram_peak_mb:.0f} MB at peak, p95 {top.scores.ms_p95:.0f} ms. "
            f"Licence: {top.spec.consequence.rstrip('.')}."
        )

    def misses(r):
        return sum(1 for ok in r.passes.values() if not ok)

    near = sorted(contenders, key=lambda r: (misses(r), -r.scores.caught))[:3]
    lines = ["**No model passes every rule.** Closest:"]
    for r in near:
        failed = ", ".join(k for k, ok in r.passes.items() if not ok) or "none"
        lines.append(
            f"- {r.spec.label}: fails {failed} ({r.scores.caught:.1f}% names, "
            f"{r.scores.hidden:.1f}% wrongly hidden, {r.scores.ram_peak_mb:.0f} MB, "
            f"p95 {r.scores.ms_p95:.0f} ms)"
        )
    return "\n".join(lines)


def markdown(
    title: str,
    date: str,
    rows: list[Row],
    baseline: str,
    rule: Rule,
    corpus_info: dict,
    threads: int,
    notes: str = "",
) -> str:
    base = next((r for r in rows if r.spec.name == baseline), None)
    out = [
        f"# {title}",
        f"\n{date}. Local only; synthetic cases only; {threads} CPU threads; each model "
        "ran alone in a fresh process at below-normal priority.\n",
        "## Decision rule (set before the numbers)\n",
        "A challenger replaces the baseline only if it:\n",
        *[f"{n}. {line}" for n, line in enumerate(rule.describe(), 1)],
        "\nLicence never blocks an owner's own use. It only decides whether a model can be "
        "bundled in a public library or must be an optional download.\n",
        "## Recommendation\n",
        recommendation(rows, baseline),
    ]
    if notes:
        out += ["", notes.strip()]
    head = [
        "Model",
        "Precision",
        "Names caught (95% CI)",
        "vs baseline",
        "Asian names",
        "Wrongly hidden (95% CI)",
        "vs baseline",
        "ms median (p95)",
        "vs baseline, same precision",
        "Peak RAM",
        "Licence",
        "What that means",
    ]
    cells = []
    for r in rows:
        s = r.scores
        cells.append(
            [
                r.spec.label,
                r.spec.precision,
                f"**{s.caught:.1f}%** ({s.caught_ci[0]:.0f}-{s.caught_ci[1]:.0f})",
                vs(s.caught - base.scores.caught, r.p_caught) if base else "-",
                f"{s.asian:.1f}%",
                f"**{s.hidden:.1f}%** ({s.hidden_ci[0]:.0f}-{s.hidden_ci[1]:.0f})",
                vs(s.hidden - base.scores.hidden, r.p_hidden) if base else "-",
                f"{s.ms_median:.0f} ({s.ms_p95:.0f})",
                f"{r.speed_x:.1f}x slower"
                if r.speed_x and r.speed_x >= 1
                else (f"{1 / r.speed_x:.1f}x faster" if r.speed_x else "-"),
                f"{s.ram_peak_mb:.0f} MB",
                r.spec.licence,
                r.spec.consequence,
            ]
        )
    out += [
        "\n## Headline\n",
        f"{corpus_info['n']} cases in {corpus_info['categories']} categories "
        f"(corpus {corpus_info['hash']}). **Speed is like-for-like only against a baseline row of the "
        'same precision**: read the "same precision" column, not raw milliseconds across '
        'precisions. "Within noise" means p ≥ 0.05 on a paired McNemar test.\n',
        table(head, cells),
    ]
    if rule.describe():
        keys = [k for k in dict.fromkeys(k for r in rows for k in r.passes)]
        out += [
            "\n## Rules, model by model\n",
            table(
                ["Model", *[RULE_LABELS.get(k, k) for k in keys], "Adopt?"],
                [
                    [
                        r.spec.label,
                        *["pass" if r.passes.get(k) else "FAIL" for k in keys],
                        "**yes**" if r.adopted else "no",
                    ]
                    for r in rows
                    if r.passes
                ],
            ),
        ]
    cats = [c for c in cases.NAME_CATS if c in rows[0].scores.per_category]
    fact_cats = [c for c in (*cases.FACT_CATS, cases.AMBIGUOUS) if c in rows[0].scores.per_category]
    best = {c: max((r.scores.per_category[c]["caught"] or -1) for r in rows) for c in cats}
    names = [
        [
            r.spec.label,
            *[
                (f"**{v:.0f}**" if v == best[c] else f"{v:.0f}")
                if (v := r.scores.per_category[c]["caught"]) is not None
                else "-"
                for c in cats
            ],
        ]
        for r in rows
    ]
    facts = [
        [
            r.spec.label,
            *[
                f"{v:.0f}" if (v := r.scores.per_category[c]["hidden"]) is not None else "-"
                for c in fact_cats
            ],
        ]
        for r in rows
    ]
    out += [
        "\n## Who wins where: names caught, % per category (bold is best)\n",
        table(["Model", *cats], names),
        "\nFacts wrongly hidden, % per category (lower is better; the shops category is shown on its "
        "own because hiding a shop named after a person is defensible):\n",
        table(["Model", *fact_cats], facts),
        "\n## Example misses (synthetic)\n",
    ]
    for r in rows:
        if r.spec.name == baseline and len(rows) > 1:
            continue
        s = r.scores
        out.append(
            f"\n**{r.spec.label}**: {len(s.misses)} names missed, {len(s.wrong)} facts wrongly hidden."
        )
        by_cat: dict[str, list[str]] = {}
        for cat, text in s.misses:
            by_cat.setdefault(cat, []).append(text)
        for cat, texts in list(by_cat.items())[:9]:
            out.append(
                f"- missed ({cat}, {len(texts)} in this category): `{texts[len(texts) // 2].replace(chr(10), ' / ')}`"
            )
        for text, fact in s.wrong[:: max(1, len(s.wrong) // 3)][:3]:
            out.append(f"- wrongly hid `{fact}` in `{text.replace(chr(10), ' / ')}`")
    return "\n".join(out) + "\n"


def result_json(
    title: str,
    rows: list[Row],
    baseline: str,
    rule: Rule,
    corpus_info: dict,
    threads: int,
    host: dict,
    date: str | None = None,
) -> dict:
    """The machine-readable record: model, revision, precision, scores per category, RAM, speed,
    licence and the decision. No raw text and no per-case data."""
    adopted = [r for r in rows if r.adopted]
    winner = max(adopted, key=lambda r: r.scores.caught).spec.name if adopted else None
    models = []
    for r in rows:
        s = r.scores
        models.append(
            {
                "model": r.spec.name,
                "label": r.spec.label,
                "repo": r.spec.repo,
                "revision": r.spec.revision,
                "precision": r.spec.precision,
                "licence": r.spec.licence,
                "licence_consequence": r.spec.consequence,
                "names_caught_pct": round(s.caught, 2),
                "names_caught_ci": [round(x, 1) for x in s.caught_ci],
                "asian_caught_pct": round(s.asian, 2),
                "wrongly_hidden_pct": round(s.hidden, 2),
                "wrongly_hidden_ci": [round(x, 1) for x in s.hidden_ci],
                "shops_hidden_pct": s.ambiguous_hidden,
                "p_names_vs_baseline": r.p_caught,
                "p_hidden_vs_baseline": r.p_hidden,
                "ms_median": round(s.ms_median, 1),
                "ms_p95": round(s.ms_p95, 1),
                "speed_vs_baseline_same_precision": r.speed_x,
                "ram_peak_mb": round(s.ram_peak_mb),
                "ram_after_load_mb": round(s.ram_load_mb),
                "per_category": s.per_category,
                "rules": r.passes,
                "adopted": r.adopted,
                "is_baseline": r.spec.name == baseline,
            }
        )
    return {
        "title": title,
        "date": date or dt.date.today().isoformat(),
        "baseline": baseline,
        "rule": asdict(rule),
        "corpus": corpus_info,
        "threads": threads,
        "host": host,
        "winner": winner,
        "models": models,
        "decision": f"adopt {winner}" if winner else "no model passes every rule",
    }
