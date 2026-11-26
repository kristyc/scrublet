"""Reversible redaction: redact for the AI, restore real values in the app (ADR 0008).

    text, job = redact(text, job)      # job: the token map so far ({} or None to start)
    answer = restore(ai_answer, job)   # the app acts on real values again

The token map is plain data, token -> {"value", "kind"}. Tokens are stable within a job: a
value seen before gets the same token in every later text. The app stores the map itself
(encrypted); Scrublet never persists it. A payload that would still hold any mapped value is
refused, never returned.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from scrublet_pii import custom, patterns, printed, terms

TOKEN = re.compile(r"\[([A-Z]+)_(\d+)\]")
Job = dict[str, dict[str, str]]


class Leaked(ValueError):
    """The redacted text would still contain a value from the map. Names no value."""


def _kind(name: str) -> str:
    letters = re.sub(r"[^A-Z]", "", name.rsplit(".", 1)[-1].upper())
    return letters or "PRIVATE"


def _known(store: terms.Terms, extra: Iterable[str]) -> list[tuple[str, str]]:
    """(value, kind) for every name and private word to hide, fullest first."""
    ok = {word.casefold() for word in store.words("always_ok")}
    found = [(name, "PERSON") for name in terms.names(store)]
    found += [(word, "PRIVATE") for name in ("never_send", "always_hide")
              for word in store.words(name)]
    found += [(value, "PERSON") for value in extra]
    return [(value, kind) for value, kind in found if value.strip() and value.casefold() not in ok]


def _spans(text: str, store: terms.Terms, known: list[tuple[str, str]],
           job: Mapping[str, Mapping[str, str]]) -> list[tuple[int, int, str, str]]:
    """(start, stop, value, kind) for everything to hide; longest wins where spans overlap."""
    kinds = dict(known)
    earlier = {item["value"]: item["kind"] for item in job.values()}
    found = [(start, stop, value, earlier.get(value) or kinds.get(value, "PERSON"))
             for start, stop, value in printed.matches(text, [*kinds, *earlier])]
    found += [(start, stop, text[start:stop], _kind(name))
              for start, stop, name in patterns.find(text)]
    for pattern in store.patterns():
        for hit in custom.compile_pattern(pattern.kind, pattern.text).finditer(text):
            if hit.end() > hit.start():
                found.append((hit.start(), hit.end(), hit.group(), _kind(pattern.kind)))
    chosen: list[tuple[int, int, str, str]] = []
    for span in sorted(found, key=lambda item: (item[0], item[0] - item[1])):
        if chosen and span[0] < chosen[-1][1]:
            last = chosen[-1]
            if span[1] > last[1]:   # overlapping and reaching further: one token covers both
                kind = (span if span[1] - span[0] > last[1] - last[0] else last)[3]
                chosen[-1] = (last[0], span[1], text[last[0]:span[1]], kind)
            continue
        chosen.append(span)
    return chosen


def redact(text: str, job: Mapping[str, Mapping[str, str]] | None = None, *,
           store: terms.Terms | None = None, extra: Iterable[str] = ()) -> tuple[str, Job]:
    """The redacted text and the job's token map (the old map plus any new tokens).
    `store` defaults to the owner's word store; `extra` adds names this call must hide."""
    mapping: Job = {token: {"value": item["value"], "kind": item["kind"]}
                    for token, item in (job or {}).items()}
    store = terms.read() if store is None else store
    by_value = {item["value"]: token for token, item in mapping.items()}
    counts: dict[str, int] = {}
    for existing in mapping:
        match = TOKEN.fullmatch(existing)
        if match is None:
            raise ValueError("Invalid token map")
        counts[match[1]] = max(counts.get(match[1], 0), int(match[2]))
    pieces: list[str] = []
    at = 0
    for start, stop, value, kind in _spans(text, store, _known(store, extra), mapping):
        token = by_value.get(value)
        if token is None:
            counts[kind] = counts.get(kind, 0) + 1
            token = f"[{kind}_{counts[kind]}]"
            mapping[token], by_value[value] = {"value": value, "kind": kind}, token
        pieces += [text[at:start], token]
        at = stop
    redacted = "".join([*pieces, text[at:]])
    left = TOKEN.sub(" ", redacted)
    if any(item["value"] in left or printed.matches(left, [item["value"]])
           for item in mapping.values()):
        raise Leaked("A mapped value is still in the redacted text")
    return redacted, mapping


def restore(text: str, job: Mapping[str, Mapping[str, str]]) -> str:
    """Put the real values back. Exact tokens only; an unknown token stays as it is."""
    return TOKEN.sub(lambda hit: job[hit[0]]["value"] if hit[0] in job else hit[0], text)
