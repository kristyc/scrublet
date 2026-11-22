"""Find known values the way documents print them (ADR 0003): one matcher for every app.

From the first app's gate, unchanged: case, punctuation and spacing are ignored, so names
split across lines match. A name cut at a field width matches by a long prefix ending at a
word edge. Each word of a multi-word name of 4+ letters matches alone; a shorter word matches
together with its marker (A/P, A/L, S/O, D/O, BIN, BINTI, BT). Values with digits, such as
addresses, match only whole. Numbers match on their digits, even inside a longer run. Letters
need a non-letter edge so a short name never matches inside another word, except a whole
value of 8 or more letters and digits, which matches glued to the text around it.

From the second app's matcher: a name of 2+ words also matches in any order (up to 4 words;
past that, as listed and reversed) and with initials ("T. AH KOW", "KOW A T"), on the listed
and reversed orders. An initial is a capital with no letter after it, at least one word of
3+ letters stays whole, and markers are left out of these forms. Values in `whole` (a linked
list's phrases) get none of this: they match as the whole phrase only.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable
from functools import lru_cache
from itertools import permutations

from tacitkit.fold import fold

# Printed forms of one marker family are interchangeable: BINTI is often BT.
FAMILIES = (frozenset({"bin", "binti", "bt", "bte"}), frozenset({"ap", "al"}),
            frozenset({"so", "do"}))
MARKERS = frozenset().union(*FAMILIES)
SLASHED = re.compile(r"\b([asd])\s*/\s*([plo])\b", re.IGNORECASE)
WORD = re.compile(r"[^\W_]+")
GLUED = 8   # a whole value this long matches with no word edge


@lru_cache(maxsize=8192)
def variants(value: str) -> tuple[tuple[str, str, int], ...]:
    """(kind, needle, shortest accepted match) for one known value."""
    folded = fold(value)[0]
    if not folded:
        return ()
    digits = "".join(char for char in folded if char.isdigit())
    if len(digits) >= 4 and len(digits) >= 0.6 * len(folded):
        return (("digits", digits, len(digits)),)
    shortest = len(folded) if len(folded) < 8 else max(6, math.ceil(0.6 * len(folded)))
    found = [("text", folded, shortest)]
    words = [fold(word)[0] for word in WORD.findall(SLASHED.sub(r"\1\2", value))]
    if len(words) > 1 and not digits:   # names, not addresses: 'Jalan' alone is common
        for position, word in enumerate(words):
            if word in MARKERS:
                continue
            if len(word) >= 4:
                found.append(("text", word, len(word)))
            elif position and words[position - 1] in MARKERS and len(word) >= 2:
                # A short name only with its marker: "BINTI ABU", never "Abu Dhabi".
                family = next(item for item in FAMILIES if words[position - 1] in item)
                found += [("text", marker + word, len(marker + word)) for marker in family]
    return tuple(dict.fromkeys(found))


ALL_ORDERS_UP_TO = 4   # past this many words, as listed and reversed only


def _words(value: str) -> list[str]:
    return [fold(word)[0] for word in WORD.findall(SLASHED.sub(r"", value))]


@lru_cache(maxsize=8192)
def _gate(value: str) -> tuple[str, ...]:
    """The whole words (3+ letters) one of which every extra form contains; () when none."""
    return tuple(word for word in _words(value) if len(word) >= 3) if forms(value) else ()


@lru_cache(maxsize=8192)
def forms(value: str) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """A name's other printed forms: (folded needle, offsets of its initials)."""
    if any(char.isdigit() for char in value):
        return ()
    words = [word for word in _words(value) if word and word not in MARKERS]
    if len(words) < 2:
        return ()
    listed = tuple(words)
    orders = (list(dict.fromkeys(permutations(words))) if len(words) <= ALL_ORDERS_UP_TO
              else [listed, listed[::-1]])
    found = [("".join(order), ()) for order in orders if order != listed]
    for order in dict.fromkeys((listed, listed[::-1])):
        for mask in range(1, 2 ** len(order) - 1):
            if not any(len(word) >= 3 for i, word in enumerate(order) if not mask >> i & 1):
                continue
            needle, initials = "", []
            for i, word in enumerate(order):
                if mask >> i & 1:
                    initials.append(len(needle))
                needle += word[0] if mask >> i & 1 else word
            found.append((needle, tuple(initials)))
    return tuple(dict.fromkeys(found))


def _formed(text: str, folded: str, index: list[int], value: str) -> list[tuple[int, int, str]]:
    found = []
    if not any(word in folded for word in _gate(value)):
        return found   # cheap gate: no whole word of the name is here
    for needle, initials in forms(value):
        at = folded.find(needle)
        while at >= 0:
            start, stop = index[at], index[at + len(needle) - 1] + 1
            if (not _letter(text, start - 1) and not _letter(text, stop) and all(
                    text[index[at + k]].isupper() and not _letter(text, index[at + k] + 1)
                    for k in initials)):
                found.append((start, stop, value))
            at = folded.find(needle, at + 1)
    return found


def _letter(text: str, position: int) -> bool:
    return 0 <= position < len(text) and text[position].isalpha()


def matches(text: str, values: Iterable[str],
            whole: frozenset[str] = frozenset()) -> list[tuple[int, int, str]]:
    """Every (start, stop, value) where a known value appears as printed. Values in `whole`
    (a linked list's phrases and holder names) match as the whole phrase only, never one
    word of it alone: a company phrase must not hide every "Malaysian" or "Trading"."""
    folded, index = fold(text)
    digits = "".join(char for char in folded if char.isdigit())
    digit_index = [index[position] for position, char in enumerate(folded) if char.isdigit()]
    found: list[tuple[int, int, str]] = []
    for value in values:
        full = variants(value)[0][1] if variants(value) else ""
        for kind, needle, shortest in variants(value)[:1] if value in whole else variants(value):
            if kind == "digits":
                at = digits.find(needle)
                while at >= 0:
                    start, stop = digit_index[at], digit_index[at + len(needle) - 1] + 1
                    if stop - start <= 3 * len(needle) + 10:   # one printed number, not a page
                        found.append((start, stop, value))
                    at = digits.find(needle, at + 1)
                continue
            at = folded.find(needle[:shortest])
            while at >= 0:
                length = shortest
                while (length < len(needle) and at + length < len(folded)
                       and folded[at + length] == needle[length]):
                    length += 1
                start, stop = index[at], index[at + length - 1] + 1
                # A whole value of 8+ letters and digits matches glued into the words around
                # it ("PAYMENTTOTAN AH KOW", "TAN AH KOWMAYBANK"; review #12), as statement
                # text prints them. Shorter or partial ones keep the letter-edge rule, so a short
                # name never matches inside another word.
                glued = length == len(needle) >= GLUED and needle == full
                if glued or (not _letter(text, start - 1) and not _letter(text, stop)):
                    found.append((start, stop, value))
                at = folded.find(needle[:shortest], at + 1)
        if value not in whole:
            found += _formed(text, folded, index, value)
    return found
