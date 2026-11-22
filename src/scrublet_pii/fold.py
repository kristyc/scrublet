"""Messy-text folding: letters and digits only, case-folded, with an index map back to the
original text, so a name split across lines or spaced oddly is found where it was printed."""

from __future__ import annotations


def fold(text: str) -> tuple[str, list[int]]:
    """Letters and digits only, case-folded, with each folded char's original index."""
    chars: list[str] = []
    index: list[int] = []
    for position, char in enumerate(text):
        if char.isalnum():
            for folded in char.casefold():
                chars.append(folded)
                index.append(position)
    return "".join(chars), index
