"""Reversible redaction: redact for the AI, restore real values in the app (ADR 0008).

    text, job = redact(text, job)                    # job: the token map so far (None to start)
    answer = restore(ai_answer, job, only={"PERSON"})  # real values back, chosen kinds only

The token map is plain data, token -> {"value", "kind"}. Every token of a job carries the
job's random nonce ("[PERSON_1_k3f9qz]"), so text the AI was fed cannot name a token it was
not shown. Tokens are stable within a job: a value seen before keeps its token in every later
text. The app stores the map itself (encrypted); Scrublet never persists it. A payload that
would still hold any mapped value is refused, never returned.
"""

from __future__ import annotations

import re
import secrets
import string
from collections.abc import Collection, Iterable, Mapping

from scrublet_pii import custom, patterns, printed, terms

TOKEN = re.compile(r"\[([A-Z]+)_(\d+)_([a-z0-9]{6})\]")
# Anything shaped like a token, with or without a nonce: escaped in input so it never restores.
SHAPED = re.compile(r"\[(?=[A-Z]+_\d+(?:_[a-z0-9]+)?\])")
# A link or address; a token inside one is never restored (the AI may be building a URL).
LINK = re.compile(r"(?i)\b(?:(?:https?|ftp|file|mailto|data|javascript):|www\.)[^\s<>\"']+")
Job = dict[str, dict[str, str]]
Span = tuple[int, int, str, str]


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
           job: Mapping[str, Mapping[str, str]]) -> list[Span]:
    """(start, stop, value, kind) for everything to hide, never overlapping. The longer span
    wins; a shorter one reaching past it keeps its own value and token for the part outside."""
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
    chosen: list[Span] = []
    for start, stop, value, kind in sorted(found, key=lambda item: (item[0], item[0] - item[1])):
        if chosen and start < chosen[-1][1]:
            edge = chosen[-1][1]
            if stop > edge and any(char.isalnum() for char in text[edge:stop]):
                chosen.append((edge, stop, value, kind))
            continue
        chosen.append((start, stop, value, kind))
    return chosen


def _parsed(mapping: Mapping[str, object]) -> tuple[str, dict[str, int]]:
    """The job's one nonce (a new random one for an empty map) and the last number per kind."""
    nonces: set[str] = set()
    counts: dict[str, int] = {}
    for token in mapping:
        match = TOKEN.fullmatch(token)
        if match is None:
            raise ValueError("Invalid token map")
        nonces.add(match[3])
        counts[match[1]] = max(counts.get(match[1], 0), int(match[2]))
    if len(nonces) > 1:
        raise ValueError("Invalid token map")
    alphabet = string.ascii_lowercase + string.digits
    return (nonces.pop() if nonces else "".join(secrets.choice(alphabet) for _ in range(6)),
            counts)


def redact(text: str, job: Mapping[str, Mapping[str, str]] | None = None, *,
           store: terms.Terms | None = None, extra: Iterable[str] = ()) -> tuple[str, Job]:
    """The redacted text and the job's token map (the old map plus any new tokens).
    `store` defaults to the owner's word store; `extra` adds names this call must hide.
    Token-shaped text already in the input is escaped, so it can never be restored."""
    mapping: Job = {token: {"value": item["value"], "kind": item["kind"]}
                    for token, item in (job or {}).items()}
    nonce, counts = _parsed(mapping)
    store = terms.read() if store is None else store
    text = SHAPED.sub("\uff3b", text)  # a fullwidth bracket
    by_value = {item["value"]: token for token, item in mapping.items()}
    pieces: list[str] = []
    at = 0
    for start, stop, value, kind in _spans(text, store, _known(store, extra), mapping):
        token = by_value.get(value)
        if token is None:
            counts[kind] = counts.get(kind, 0) + 1
            token = f"[{kind}_{counts[kind]}_{nonce}]"
            mapping[token], by_value[value] = {"value": value, "kind": kind}, token
        pieces += [text[at:start], token]
        at = stop
    redacted = "".join([*pieces, text[at:]])
    left = TOKEN.sub(" ", redacted)
    if any(item["value"] in left or printed.matches(left, [item["value"]])
           for item in mapping.values()):
        raise Leaked("A mapped value is still in the redacted text")
    return redacted, mapping


def restore(text: str, job: Mapping[str, Mapping[str, str]], *,
            only: Collection[str] | None = None) -> str:
    """Put the real values back for exact tokens of this job. `only` names the kinds this
    field may receive (None: every kind). A token of another kind, an unknown token and any
    token inside a link or address stay as they are."""
    links = [hit.span() for hit in LINK.finditer(text)]

    def back(hit: re.Match[str]) -> str:
        item = job.get(hit[0])
        inside = any(start <= hit.start() < stop for start, stop in links)
        if item is None or inside or (only is not None and item["kind"] not in only):
            return hit[0]
        return item["value"]

    return TOKEN.sub(back, text)
