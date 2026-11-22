"""The owner's own patterns (ADR 0007): a shape such as "AA-9999999", or a bounded regex.

A person teaches the library a number format it doesn't know (a policy or member number) by
hiding one example. `shape_of` turns that example into a shape (letters "A", digits "9", other
characters kept), `compile_pattern` turns a shape or a regex into a compiled pattern. Both are
bounded so a stored pattern can't make matching slow: a length cap, a quantifier cap, and a
restricted regex grammar with no nested quantifiers, backreferences or lookaround.

Pure standard library, no I/O. Nothing here logs and no error carries a pattern or a sample.
"""

from __future__ import annotations

import re
from typing import NamedTuple

MAX_CHARS = 200  # a pattern's text
MAX_SAMPLE = 64  # a sample to derive a shape from
MIN_SIGNIFICANT = 6  # letters and digits a shape needs, so "99" can't match every pair of digits
MAX_QUANTIFIERS = 4  # quantifiers in one regex
MAX_UNBOUNDED = 1  # of those, how many may be unbounded (*, + or {m,}): two can overlap
MAX_REPEAT = 64  # the largest number in a {m,n}
KINDS = ("shape", "regex")
_EDGE_BEFORE, _EDGE_AFTER = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"  # numbers that run on


class Pattern(NamedTuple):
    """One stored pattern. `id` is derived from kind, text and scope, so adding it twice is
    one pattern and removing it is by a stable id. `at` is when the owner added it."""

    id: str
    kind: str
    text: str
    scope: str = "general"
    at: str = ""


class Invalid(ValueError):
    """A pattern the library won't take. The message names the rule, never the pattern."""


def shape_of(sample: str) -> str:
    """The shape of one example: each letter becomes A, each digit 9, anything else stays.
    "ab-123456" is "AA-999999". Refused when it is too short to be distinctive."""
    if type(sample) is not str or not sample.strip() or len(sample.strip()) > MAX_SAMPLE:
        raise Invalid(f"an example needs 1 to {MAX_SAMPLE} characters")
    shape = "".join(
        "9" if char.isdigit() else "A" if char.isalpha() else char for char in sample.strip()
    )
    _check_shape(shape)
    return shape


def _check_shape(shape: str) -> None:
    if (
        type(shape) is not str
        or not shape
        or len(shape) > MAX_CHARS
        or sum(char in "A9" for char in shape) < MIN_SIGNIFICANT
    ):
        raise Invalid(f"a shape needs at least {MIN_SIGNIFICANT} letters or digits")
    if any(char.isspace() and char != " " for char in shape) or not shape.isprintable():
        raise Invalid("a shape holds printable characters only")


def _from_shape(shape: str) -> str:
    _check_shape(shape)
    parts: list[str] = []
    index = 0
    while index < len(shape):
        char = shape[index]
        run = 1
        while char in "A9" and index + run < len(shape) and shape[index + run] == char:
            run += 1
        piece = r"[A-Za-z]" if char == "A" else r"\d" if char == "9" else re.escape(char)
        parts.append(piece + (f"{{{run}}}" if run > 1 else ""))
        index += run
    return _EDGE_BEFORE + "".join(parts) + _EDGE_AFTER


def _check_regex(text: str) -> None:
    """A deliberately small grammar. Quantifiers apply to one atom only (never a group), so
    nested quantifiers can't exist; no backreferences, lookaround or conditionals."""
    if type(text) is not str or not text or len(text) > MAX_CHARS or not text.isprintable():
        raise Invalid(f"a pattern needs 1 to {MAX_CHARS} printable characters")
    quantifiers = unbounded = 0
    index, previous = 0, "start"  # previous: start, atom, group_end, quantifier
    while index < len(text):
        char = text[index]
        if char == "\\":
            follower = text[index + 1 : index + 2]
            if not follower or follower.isdigit() or follower in "kg":
                raise Invalid("backreferences are not allowed")
            index, previous = index + 2, "atom"
        elif char == "[":
            index = _skip_class(text, index)
            previous = "atom"
        elif char == "(":
            if text[index + 1 : index + 2] == "?" and text[index + 1 : index + 3] != "?:":
                raise Invalid("lookaround and flags are not allowed")
            index, previous = index + (3 if text[index + 1 : index + 3] == "?:" else 1), "start"
        elif char == ")":
            index, previous = index + 1, "group_end"
        elif char in "*+?{":
            if previous in {"start", "quantifier", "group_end"}:
                raise Invalid("a quantifier must follow one character or class")
            index, wide = _quantifier(text, index)
            quantifiers += 1
            unbounded += wide
            if quantifiers > MAX_QUANTIFIERS or unbounded > MAX_UNBOUNDED:
                raise Invalid("too many repeats in one pattern")
            previous = "quantifier"
        else:
            index, previous = index + 1, "start" if char == "|" else "atom"


def _skip_class(text: str, index: int) -> int:
    index += 1
    if text[index : index + 1] == "^":
        index += 1
    if text[index : index + 1] == "]":
        index += 1
    while index < len(text) and text[index] != "]":
        index += 2 if text[index] == "\\" else 1
    if index >= len(text):
        raise Invalid("a character class is not closed")
    return index + 1


def _quantifier(text: str, index: int) -> tuple[int, int]:
    """(the index after the quantifier, 1 if it is unbounded)."""
    if text[index] in "*+":
        return index + 1, 1
    if text[index] == "?":
        return index + 1, 0
    found = re.compile(r"\{(\d{1,3})(,(\d{0,3}))?\}").match(text, index)
    if found is None:
        raise Invalid("a repeat is {m}, {m,} or {m,n}")
    low, comma, high = int(found[1]), found[2], found[3]
    if low > MAX_REPEAT or (high and int(high) > MAX_REPEAT) or (high and int(high) < low):
        raise Invalid(f"a repeat counts up to {MAX_REPEAT}")
    return found.end(), 1 if comma and not high else 0


def compile_pattern(kind: str, text: str) -> re.Pattern[str]:
    """The compiled pattern for a stored shape or regex. Raises Invalid, never a pattern."""
    if kind not in KINDS:
        raise Invalid("a pattern is a shape or a regex")
    if kind == "shape":
        source = _from_shape(text)
    else:
        _check_regex(text)
        source = text
    try:
        compiled = re.compile(source)
    except re.error:
        raise Invalid("that is not a valid pattern") from None
    if compiled.search("") is not None:
        raise Invalid("a pattern may not match nothing")
    return compiled
