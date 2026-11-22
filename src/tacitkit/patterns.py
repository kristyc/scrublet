"""Hard detectors: secrets and keys, cards, ID numbers, passports, bank accounts, phones,
emails and addresses. Each hit carries a value-free name ("pattern.card"), never the value.

The Malaysian pack ("my") is first; each pack is an ordered tuple of Detector, and an app maps
a detector's group to its own categories and its name to its own tier (hide, liftable or hard).
Moved from the owner's assistant app's gate unchanged (ADR 0002), so its tests still hold.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from typing import NamedTuple


def luhn(digits: str) -> bool:
    """The card checksum; order, parcel and booking numbers almost never pass it."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


class Hit:
    """A span found by code rather than one regex, read like a match (span, start, [0])."""
    def __init__(self, text: str, start: int, stop: int) -> None:
        self.text, self._span = text, (start, stop)

    def __getitem__(self, group: int) -> str:
        return self.text[slice(*self._span)]

    def start(self) -> int:
        return self._span[0]

    def span(self) -> tuple[int, int]:
        return self._span


class Cards:
    """A card number only if it starts with a card network's prefix and passes Luhn, so a
    13-19 digit order or tracking number is no hard block. Same search/finditer as a regex.

    Digits are read in printed groups, with up to 3 separators between groups: spaces (also
    non-breaking), a dash or a line break, so double spaces, column gaps and a number split
    over lines are one card (review HIGH #1, #2). A card starts and ends at a group's edge,
    and a 16-digit card glued to other digits ("REF 4111...11110001") is read at either end
    of its run only, so a long reference is rarely a card by chance."""
    run = re.compile(r"(?<!\d)\d+(?:[\s-]{1,3}\d+)*(?!\d)")
    group = re.compile(r"\d+")
    # Visa 4; Mastercard 51-55 and 22-27; Amex 34/37; Diners and JCB 30/35/36/38/39;
    # Discover 6011/644-649/65; UnionPay 62.
    networks = re.compile(r"4|5[1-5]|2[2-7]|3[045689]|37|6011|64[4-9]|65|62")

    def card(self, digits: str) -> bool:
        return 13 <= len(digits) <= 19 and bool(self.networks.match(digits)) and luhn(digits)

    def finditer(self, text: str) -> Iterator[Hit]:
        for run in self.run.finditer(text):
            groups = [match.span() for match in self.group.finditer(text, *run.span())]
            yield from self._in(text, groups)

    def _in(self, text: str, groups: list[tuple[int, int]]) -> Iterator[Hit]:
        first = 0
        while first < len(groups):
            digits, found = "", None
            for last in range(first, len(groups)):   # the longest card from this group
                digits += text[slice(*groups[last])]
                if len(digits) > 19:
                    break
                # A card prints in groups of at most 6 (4-4-4-4, 4-6-5), or as one run: an
                # order number's 7-digit groups ("123-4567890-1234567") are no card.
                if last > first and any(b - a > 6 for a, b in groups[first:last + 1]):
                    break
                if self.card(digits):
                    found = last
            start, stop = groups[first]
            if found is not None:
                yield Hit(text, start, groups[found][1])
                first = found
            elif stop - start > 16 and any(self.card(text[at:at + 16])
                                           for at in (start, stop - 16)):
                yield Hit(text, start, stop)
            first += 1

    def search(self, text: str) -> Hit | None:
        return next(self.finditer(text), None)


class Valued:
    """A regex whose label is context only: a hit is the named group that matched (the
    number), so "IC 900101-14-5678" hides the number and keeps the word IC."""
    def __init__(self, pattern: re.Pattern[str]) -> None:
        self.pattern = pattern

    def finditer(self, text: str) -> Iterator[Hit]:
        for match in self.pattern.finditer(text):
            name = match.lastgroup or 0
            yield Hit(text, match.start(name), match.end(name))

    def search(self, text: str) -> Hit | None:
        return next(self.finditer(text), None)


class Detector(NamedTuple):
    name: str           # value-free, e.g. "pattern.card"
    group: str          # "identity", "financial" or "credential"
    finder: re.Pattern[str] | Cards | Valued


CARD = Cards()
# Bank names that mark nearby digits as an account number. A space means an optional space.
MY_BANKS = ("maybank", "cimb", "public bank", "rhb", "hong leong", "ambank", "bsn",
            "bank islam", "bank rakyat", "affin", "alliance bank", "ocbc", "hsbc",
            "uob", "standard chartered", "agrobank", "muamalat", "mbsb")
BANKS = "|".join(re.escape(name).replace(r"\ ", " ?") for name in MY_BANKS)
YYMMDD = r"\d\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
_NOT_ACCOUNT = r"order|booking|tracking|member|membership|invoice|policy|ref\b|reference|receipt"
# Between an account word and its number: up to 40 characters on the label's line, then at
# most one line break and 40 more, never across an order/booking/member word.
_GAP = (r"(?:(?!" + _NOT_ACCOUNT + r")[^\n\d]){0,40}?"
        r"(?:\n(?:(?!" + _NOT_ACCOUNT + r")[^\n\d]){0,40}?)?")
MY: tuple[Detector, ...] = (
    # Emails as printed or typed, including a space either side of "@" (ADR 204 benchmark).
    Detector("pattern.email", "identity", re.compile(
        r"(?<![\w.+-])[\w.+-]+ ?@ ?[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}")),
    Detector("pattern.phone", "identity", re.compile(r"(?<!\w)\+?\d[\d ().-]{7,32}\d(?!\w)")),
    # A street line (number + Malaysian road word) and a postcode + town (ADR 204).
    Detector("pattern.street", "identity", re.compile(
        r"(?i)\b(?:no\.? ?)?\d{1,4}[a-z]?,? (?:jalan|jln|lorong|lrg|persiaran|lebuh|"
        r"taman|tmn)\b[^\n,]{0,40}")),
    Detector("pattern.postcode", "identity", re.compile(r"\b\d{5} [A-Z][a-z]+(?: [A-Z][a-z]+)?")),
    # IC (review #7, #8): its first 6 digits are a birth date (YYMMDD), and it is an IC only
    # when printed in its 6-2-4 groups (up to 3 spaces, dots, dashes or a line break between
    # them: "900101 - 14 - 5678", "900101-\n14-5678") or after an IC word. A bare 12-digit
    # run starting with a date ("Lazada order 261122123456") is an order: the phone pattern.
    Detector("pattern.ic", "identity", Valued(re.compile(
        r"(?<!\d)(?P<grouped>" + YYMMDD + r"[\s.-]{1,3}\d{2}[\s.-]{1,3}\d{4})(?!\d)"
        r"|(?i:\b(?:ic|nric|mykad|k/p|kp|kad pengenalan)\b)[^\d]{0,20}?"
        r"(?<!\d)(?P<labelled>" + YYMMDD + r"[\s.-]{0,3}\d{2}[\s.-]{0,3}\d{4})(?!\d)"))),
    # Passports: 1-2 letters + 6-9 digits after the word passport/pasport (a line break
    # allowed between). A letter + 8 digits alone ("receipt K12345678") is a receipt or parcel
    # code as often as a passport: pattern.id_shape below, hidden but never a hard block.
    Detector("pattern.passport", "identity", re.compile(
        r"(?i)\bpas{1,2}port\b[^\d]{0,30}?(?<![a-z])[a-z]{1,2}[\s-]?\d(?:[\s-]?\d){5,8}(?!\d)")),
    Detector("pattern.card", "financial", CARD),
    # Bank accounts, HARD only in account context: an account word or a bank's name before
    # the digits, the number on the same line or the line below its label (review #8). An
    # order, booking, tracking, member or reference word between them makes it no account
    # ("account order 123-...", "Star Alliance member 123..."; review #7). A bare digit run
    # (phones, parcels, orders) is the phone pattern: liftable and hidden on private paths,
    # never checked on a search (supervisor, 22 Nov). A bank's name counts only for 10-16
    # digits with no phone word between, never a 1300/1800 hotline. engine/strings/banks.json.
    Detector("pattern.account", "financial", re.compile(
        r"(?i)\b(?:account|acct|acc|a/c|akaun)\b" + _GAP + r"\d(?:[\s-]?\d){5,17}(?!\d)"
        r"|\b(?:" + BANKS + r")\b"
        r"(?:(?!hotline|call|tel|phone|contact|careline|whatsapp|fax|" + _NOT_ACCOUNT + r")"
        r"[^\n\d]){0,25}(?!1[38]00)\d(?:[\s-]?\d){9,15}(?!\d)")),
    Detector("pattern.amount", "financial", re.compile(
        r"(?i)(?:\b(?:RM|MYR|USD|EUR|GBP)\s*|[$€£])\d[\d,]*(?:\.\d+)?")),
    # Quoted values (password="x", JSON "password":"x", escaped quotes) are
    # covered whole, even unterminated; bare values stop at a delimiter (R3).
    Detector("pattern.credential", "credential", re.compile(
        r"(?i)\b(?:password|passwd|passcode|pwd|api[ _-]?key|secret|token|otp|totp)[\"']?"
        r"\s*(?:[:=]|\bis\b)\s*(?:\"(?:[^\"\\\n]|\\.){1,512}\"?|'(?:[^'\\\n]|\\.){1,512}'?"
        r"|[^\s\"'\\,}]+)")),
    # Keys and tokens by their own shape, so a hard item never depends on the name model
    # (22 Nov gap): provider prefixes, Bearer tokens, JWTs, PEM private keys, and a long
    # base64/hex run after a key, token, secret or password word.
    Detector("pattern.key", "credential", re.compile(
        r"(?<![\w-])(?:sk-(?:ant-|proj-)?[\w-]{16,}|AIza[\w-]{30,}|(?:ghp|gho|ghu|ghs|ghr)_\w{30,}"
        r"|github_pat_\w{30,}|xox[abpr]-[\w-]{10,}|(?:AKIA|ASIA)[A-Z0-9]{16}"
        r"|eyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{8,})"
        r"|(?i:\bbearer\s+[\w.~+/-]{16,}=*)"
        r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]{0,8192}?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"
        r"|(?i:\b(?:key|token|secret|password|passwd)\b)[^\n\w]{0,20}"
        r"(?:\w+[^\n\w]{1,3}){0,3}?(?=[A-Za-z0-9+/_=-]{24,})(?=[^\s]*\d)[A-Za-z0-9+/_=-]{24,}")),
    # A letter + 8 digits standing alone (a Malaysian passport's shape, and many receipt and
    # parcel codes): hidden where private content goes, never a hard block (review #7).
    Detector("pattern.id_shape", "identity", re.compile(
        r"(?i)(?<![a-z0-9])[ahk][\s-]?\d(?:[\s-]?\d){7}(?!\d)")),
)


PACKS = {"my": MY}


def pack(name: str = "my") -> tuple[Detector, ...]:
    return PACKS[name]


def find(text: str, packs: tuple[str, ...] = ("my",)) -> list[tuple[int, int, str]]:
    """Every (start, stop, name) a detector finds, in pack order. Never a value."""
    return [(*hit.span(), detector.name) for name in packs for detector in PACKS[name]
            for hit in detector.finder.finditer(text)]


def kinds(text: str, packs: tuple[str, ...] = ("my",)) -> tuple[str, ...]:
    """Which detectors match `text`: names only."""
    return tuple(detector.name for name in packs for detector in PACKS[name]
                 if detector.finder.search(text))
