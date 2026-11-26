"""Messy-text folding: letters and digits only, case-folded, with an index map back to the
original text, so a name split across lines or spaced oddly is found where it was printed.

Each character is NFKC-normalised (fullwidth and styled letters become plain ones) and
Cyrillic and Greek letters that look Latin are read as the Latin letter, so a lookalike
spelling of a name folds to the same text as the name (ADR 0008).
"""

from __future__ import annotations

import unicodedata

# Lowercase Cyrillic and Greek letters drawn like a Latin letter (after case-folding).
LOOKALIKE = str.maketrans({
    "\u0430": "a", "\u0432": "b", "\u0435": "e", "\u043a": "k", "\u043c": "m", "\u043d": "h",
    "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0442": "t", "\u0443": "y", "\u0445": "x",
    "\u0456": "i", "\u0458": "j", "\u0455": "s", "\u0501": "d", "\u051b": "q", "\u051d": "w",
    "\u04af": "y", "\u04cf": "l", "\u03b1": "a", "\u03b2": "b", "\u03b5": "e", "\u03b6": "z",
    "\u03b7": "h", "\u03b9": "i", "\u03ba": "k", "\u03bc": "m", "\u03bd": "v", "\u03bf": "o",
    "\u03c1": "p", "\u03c4": "t", "\u03c5": "u", "\u03c7": "x",
})


def fold(text: str) -> tuple[str, list[int]]:
    """Letters and digits only, case-folded, with each folded char's original index."""
    chars: list[str] = []
    index: list[int] = []
    for position, char in enumerate(text):
        for folded in unicodedata.normalize("NFKC", char).casefold().translate(LOOKALIKE):
            if folded.isalnum():
                chars.append(folded)
                index.append(position)
    return "".join(chars), index
