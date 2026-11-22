"""Scoring and statistics for a name-finding bake-off. Standard library only.

A name is *caught* when every word of it is hidden (markers such as bin, a/l and d/o need not
be). A fact is *wrongly hidden* when any word of it is hidden. Spans are (start, stop) pairs.
Differences come with paired exact McNemar p-values and Wilson 95% intervals, so "within
noise" is a number, not a feeling.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

CONNECTORS = frozenset({"bin", "binti", "bt", "bte", "a/l", "a/p", "s/o", "d/o"})
NOISE_P = 0.05


def words(text: str, start: int) -> list[tuple[int, int]]:
    """(start, stop) of each word of `text`, which sits at `start` in the case, markers left out."""
    out, index = [], 0
    for word in text.split():
        at = text.index(word, index)
        index = at + len(word)
        if word.lower().strip(",.") not in CONNECTORS:
            out.append((start + at, start + at + len(word)))
    return out


def merged(spans) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(map(tuple, spans)):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def covered(word: tuple[int, int], spans) -> bool:
    """At least half of the word is inside a hidden span."""
    a, b = word
    return sum(max(0, min(b, d) - max(a, c)) for c, d in merged(spans)) * 2 >= b - a


def judge(case: dict, spans) -> tuple[bool | None, list[bool]]:
    """(name caught or None if the case has no names, one 'wrongly hidden' flag per fact)."""
    text = case["text"]
    caught = None
    if case["names"]:
        caught = all(
            covered(w, spans) for name in case["names"] for w in words(name, text.index(name))
        )
    hidden = [
        any(covered(w, spans) for w in words(keep, text.index(keep))) for keep in case["keeps"]
    ]
    return caught, hidden


def wilson(k: int, n: int) -> tuple[float, float]:
    """95% Wilson interval for k of n, in percent."""
    if n == 0:
        return (0.0, 0.0)
    z, p = 1.96, k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half) * 100, min(1.0, centre + half) * 100


def mcnemar(a: list[bool], b: list[bool]) -> float:
    """Exact two-sided McNemar p for paired outcomes (same cases, same order)."""
    only_a = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    only_b = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)


def pct(k: int, n: int) -> float | None:
    return 100 * k / n if n else None


@dataclass
class Scores:
    """One model's results over the corpus."""

    caught: float
    caught_ci: tuple[float, float]
    n_names: int
    asian: float
    asian_ci: tuple[float, float]
    hidden: float
    hidden_ci: tuple[float, float]
    n_facts: int
    ambiguous_hidden: float | None
    per_category: dict[str, dict]
    ms_median: float
    ms_p95: float
    ram_peak_mb: float
    ram_load_mb: float
    flags: dict = field(default_factory=dict, repr=False)  # paired flags for p-values
    misses: list = field(default_factory=list, repr=False)  # (category, text)
    wrong: list = field(default_factory=list, repr=False)  # (text, fact)


def score(cases: list[dict], run: dict, name_cats, fact_cats, asian_cats, ambiguous: str) -> Scores:
    """Score one worker run (spans per case id, timings, memory)."""
    verdicts = [judge(c, run["spans"][str(c["id"])]) for c in cases]
    names = [
        (c, ok)
        for c, (ok, _) in zip(cases, verdicts, strict=True)
        if ok is not None and c["category"] in name_cats
    ]
    facts = [
        (c, f, h)
        for c, (_, hs) in zip(cases, verdicts, strict=True)
        if c["category"] in fact_cats
        for f, h in zip(c["keeps"], hs, strict=True)
    ]
    ambiguous_flags = [
        h
        for c, (_, hs) in zip(cases, verdicts, strict=True)
        if c["category"] == ambiguous
        for h in hs
    ]
    asian = [ok for c, ok in names if c["category"] in asian_cats]
    per = {}
    for cat in dict.fromkeys(c["category"] for c in cases):
        oks = [
            ok
            for c, (ok, _) in zip(cases, verdicts, strict=True)
            if c["category"] == cat and ok is not None
        ]
        hs = [
            h
            for c, (_, flags) in zip(cases, verdicts, strict=True)
            if c["category"] == cat
            for h in flags
        ]
        per[cat] = {
            "caught": pct(sum(oks), len(oks)),
            "n_names": len(oks),
            "hidden": pct(sum(hs), len(hs)),
            "n_facts": len(hs),
        }
    ms = sorted(run["ms"])
    caught, hidden = sum(ok for _, ok in names), sum(h for _, _, h in facts)
    return Scores(
        caught=100 * caught / len(names),
        caught_ci=wilson(caught, len(names)),
        n_names=len(names),
        asian=100 * sum(asian) / len(asian),
        asian_ci=wilson(sum(asian), len(asian)),
        hidden=100 * hidden / len(facts),
        hidden_ci=wilson(hidden, len(facts)),
        n_facts=len(facts),
        ambiguous_hidden=pct(sum(ambiguous_flags), len(ambiguous_flags)),
        per_category=per,
        ms_median=statistics.median(ms),
        ms_p95=ms[int(0.95 * len(ms))],
        ram_peak_mb=run["ram_peak_mb"],
        ram_load_mb=run["ram_load_mb"],
        flags={"names": [ok for _, ok in names], "facts": [h for _, _, h in facts], "asian": asian},
        misses=[(c["category"], c["text"]) for c, ok in names if not ok],
        wrong=[(c["text"], f) for c, f, h in facts if h],
    )
