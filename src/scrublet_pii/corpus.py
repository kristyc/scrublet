"""A synthetic test corpus for privacy gates, and a runner every app calls with its own gate.

No real person, account or number: card numbers are public test values, the names and
places are invented or public. The first pack is Malaysian (country packs follow
scrublet_pii.patterns). Each app gives the runner one function per path it has:

    def search(text) -> (outcome, payload)    # a web search query
    def message(text) -> (outcome, payload)   # the owner's own text going to a model
    def document(text) -> (outcome, payload)  # a document line (defaults to message)

outcome is "sent" (unchanged), "hidden" (changed) or "refused"; payload is the text that
would leave. Load NEVER_SEND into the app's own never-send list and LINKED into its linked
list (or its own list, if it has no linked tier) before running.

run() returns every miss. A case the app knowingly misses goes in `known` with a reason in
the app's test, so the list is visible and shrinks: a known case that passes is reported too.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from typing import NamedTuple

from scrublet_pii.fold import fold as folded

Gate = Callable[[str], tuple[str, str]]


class Case(NamedTuple):
    id: str
    path: str  # "search", "message" or "document"
    text: str
    expect: str  # a key of EXPECT
    secret: tuple[str, ...] = ()  # must not be in the payload (folded)
    keep: tuple[str, ...] = ()  # must be in the payload, as written
    kind: str = ""  # value-free category, for reports


EXPECT = {
    "sent": lambda outcome: outcome == "sent",
    "not_refused": lambda outcome: outcome != "refused",
    "withheld": lambda outcome: outcome in {"refused", "hidden"},
    "refused": lambda outcome: outcome == "refused",
    "hidden": lambda outcome: outcome == "hidden",
}

# Web searches as typed: must reach the provider byte-identical.
SEARCHES = (
    "Lazada order 312345678901234 delivery status",  # long numbers that are no card
    "J&T tracking 6300123456789",
    "PosLaju tracking EN1234567890123MY",
    "track J&T parcel 630012345678",  # digits that are no account or IC
    "Shopee order 2411220ABCD123 status",
    "Maybank hotline 1300 88 6688",
    "opening hours of the National Library of Malaysia",
    "Pavilion Kuala Lumpur opening hours today",
    "Mid Valley Megamall parking rates",
    "Sunway Pyramid ice skating rink price",
    "Maybank branch opening hours Saturday Petaling Jaya",
    "CIMB Bank Bangsar branch phone number",
    "Public Bank customer service hotline",
    "Grab fare from KLCC to KLIA",
    "Grab Food delivery fee Subang Jaya",
    "JPJ Wangsa Maju opening hours",
    "Jabatan Imigresen Putrajaya passport renewal appointment",
    "LHDN e-Filing deadline 2026",
    "KWSP Kelana Jaya branch address",
    "Klinik Kesihatan Petaling Jaya walk-in hours",
    "Gleneagles Kuala Lumpur cardiology clinic hours",
    "Sunway Medical Centre visiting hours",
    "Village Grocer Bangsar Shopping Centre opening time",
    "Nando's Mid Valley halal status",
    "Restoran Rebung Chef Ismail menu",
    "Jalan Alor food street best time to visit",
    "MRT Kajang line first train time",
    "KTM Komuter Port Klang line schedule",
    "Touch n Go eWallet reload limit",
    "Petronas Twin Towers skybridge tickets",
    "Batu Caves Thaipusam 2027 date",
    "Tun Dr Mahathir Mohamad biography",
    "Anwar Ibrahim speech on budget 2026",
    "Lee Chong Wei badminton academy Bukit Jalil",
    "Uniqlo Sunway Velocity return policy",
    "IKEA Tebrau delivery to Johor Bahru",
    "Shopee Mall refund process",
    "TNB bill payment due date",
    "Unifi fibre outage Cheras today",
    "weather forecast Genting Highlands this weekend",
    "Lazada order 261122123456 status",  # 12 digits starting with a date: no IC
    "Watsons receipt K12345678 refund",  # a letter + 8 digits: no passport
    "Star Alliance member 1234567890 lounge access",
    "my amazon account order 123-4567890-1234567 not delivered",
)

# The owner's own messages and drafts: may be hidden, never refused.
MESSAGES = (
    "My Shopee order 241122012345678 hasn't arrived",
    "Booking ref 7012345678901234 for the hotel",
    "Call the clinic back on 012-345 6789 tomorrow",  # a phone: hidden, never refused
    "Where is my Lazada order 2411220ABCD123?",
    "Remind me to call Aisyah about the Q3 slides tomorrow at 10am",
    "Draft a thank-you note to Wei Ling for covering the client call",
    "Tell Raj the vendor demo moved to Thursday afternoon",
    "Summarise what Siti said about the budget in today's meeting",
    "Book a table for four at Restoran Rebung on Friday night",
    "What time does the Pavilion KL Apple Store open?",
    "Find a paediatric clinic near Damansara Heights open on Sunday",
    "Remind me to pay the TNB bill before the 25th",
    "Write a short update for Daniel: the migration finished, two issues left",
    "Ask Mei Ling whether the Penang offsite is still on",
    "Plan a Saturday in Ipoh with my parents: breakfast, caves and dinner",
    "Compare Grab and AirAsia Ride for a trip to the airport at 6am",
    "Draft a polite reminder to Farah about the expense claims",
    "Check if the National Library of Malaysia is open on public holidays",
    "Add a note: Dr Tan at Gleneagles said follow-up in three months",
    "Tell Hafiz I'll be 15 minutes late to the standup",
    "Draft the weekly update: Priya closed two tickets, Ahmad is on leave",
    "What's the dress code for the Mandarin Oriental KL high tea?",
    "Remind me to renew my driving licence at JPJ next month",
)

# Hard items: never sent on any path. id -> (text, kind, secret). Messy layouts on purpose.
HARD = {
    "password": ("My password is Kopi-Ais#2026 for the portal", "password", "Kopi-Ais#2026"),
    "api_key": (
        "Use this key sk-ant-api03-SYNTHETICabcdefghijklmnopqrstuvwxyz0123456789",
        "api_key",
        "SYNTHETICabcdefghijklmnopqrstuvwxyz0123456789",
    ),
    "otp": ("The OTP is 482913, enter it now", "otp", "482913"),
    "ic": ("My IC is 900101-14-5678", "ic", "900101145678"),
    "ic_spaced": ("IC no 900101 14 5678", "ic", "900101145678"),
    "ic_spaced_dash": ("IC no 900101 - 14 - 5678", "ic", "900101145678"),
    "ic_line_split": ("NO. KP: 900101-\n14-5678", "ic", "900101145678"),
    "passport": ("Passport number A12345678 expires 2030", "passport", "12345678"),
    "card": ("Card 4111 1111 1111 1111 exp 12/29", "card", "4111111111111111"),
    "card_dashed": ("4111-1111-1111-1111", "card", "4111111111111111"),
    "card_mastercard": ("pay with 5555 5555 5555 4444", "card", "5555555555554444"),
    "card_line_split": ("Card no 4111\n1111\n1111\n1111 exp 12/29", "card", "4111111111111111"),
    "card_nbsp": ("CARD NO 4111\u00a01111\u00a01111\u00a01111", "card", "4111111111111111"),
    "card_double_space": ("4111  1111  1111  1111   RM 12.34", "card", "4111111111111111"),
    "card_glued": ("TXN REF 41111111111111110001", "card", "4111111111111111"),
    "card_amex_465": ("AMEX 3782 822463 10005", "card", "378282246310005"),
    "card_mastercard_mixed": ("5555 5555-5555 4444", "card", "5555555555554444"),
    "bank_account": ("Transfer to account 5140 1234 5678 at Maybank", "account", "514012345678"),
    "account_label_above": ("Account No.\n5140 1234 5678", "account", "514012345678"),
    "account_cell_padded": ("ACCOUNT NUMBER     :     5140-1234-5678", "account", "514012345678"),
}

# The owner's never-send list for the corpus, and linked names (another app's list).
NEVER_SEND = ("Melati Cafe", "Siti Aminah binti Abu", "Kumar a/p Raj")
LINKED = ("Tan Ah Kow", "Kedai Runcit Bunga")

# Text naming a listed item: a search stops; a message never carries it. (text, secret)
NEVER = (
    ("Melati Cafe opening hours", "Melati Cafe"),
    ("Book Melati Cafe for Friday", "Melati Cafe"),
    ("SITI AMINAH BT ABU", "SITI AMINAH"),  # marker family (binti, bt)
    ("KUMAR A / P RAJ", "KUMAR"),  # spaced marker
)
LINKED_TEXT = (
    ("TAN AH KOW birthday gift ideas", "TAN AH KOW"),
    ("Draft a note to Kedai Runcit Bunga", "Kedai Runcit Bunga"),
    ("PAYMENTTOTAN AH KOW", "TAN AH KOW"),  # glued at the start
    ("TAN AH KOWMAYBANK 5140", "TAN AH KOW"),  # glued at the end
)
# How statements print a listed name: never sent on any path. (text, secret)
PRINTED = (
    ("DUITNOW TRF TAN AH KOW 12.34", "TAN AH KOW"),  # a transfer row is not a merchant
    ("AH KOW TAN", "AH KOW TAN"),  # reordered
    ("T. AH KOW", "AH KOW"),  # an initial
    ("TAN AH K", "TAN AH K"),  # cut at the field width
    ("PAYMENT THANK YOU CR ACME BANK A/P", ""),  # the marker alone, name cut off
)
# Document lines whose facts must survive. (text, kept)
DOCUMENTS = (
    ("02-01-26 03-01-26 GRAB*RIDES KUALA LUMPUR 12.34", ("02-01-26", "12.34", "GRAB")),
    ("Statement date 22-11-2026  Minimum payment RM 12.34", ("22-11-2026",)),
    ("Office hours 10.30 - 11.45", ("10.30 - 11.45",)),
)


def _cases() -> tuple[Case, ...]:
    cases = [
        Case(f"search.everyday.{n}", "search", text, "sent", kind="everyday")
        for n, text in enumerate(SEARCHES)
    ]
    cases += [
        Case(f"message.everyday.{n}", "message", text, "not_refused", kind="everyday")
        for n, text in enumerate(MESSAGES)
    ]
    for name, (text, kind, secret) in HARD.items():
        cases += [
            Case(f"{path}.hard.{name}", path, text, "withheld", (secret,), kind=kind)
            for path in ("search", "message")
        ]
    for group, items, hidden in (("never", NEVER, "withheld"), ("linked", LINKED_TEXT, "hidden")):
        for n, (text, secret) in enumerate(items):
            cases += [
                Case(f"search.{group}.{n}", "search", text, "refused", kind=group),
                Case(f"message.{group}.{n}", "message", text, hidden, (secret,), kind=group),
            ]
    for n, (text, secret) in enumerate(PRINTED):
        cases += [
            Case(
                f"{path}.printed.{n}",
                path,
                text,
                "withheld",
                (secret,) if secret else (),
                kind="printed",
            )
            for path in ("search", "document")
        ]
    cases += [
        Case(f"document.facts.{n}", "document", text, "not_refused", keep=kept, kind="facts")
        for n, (text, kept) in enumerate(DOCUMENTS)
    ]
    return tuple(cases)


CASES = _cases()


def fold(text: str) -> str:
    """Letters and digits only, case-folded, compatibility-normalised."""
    return folded(unicodedata.normalize("NFKC", text))[0]


def leaks(secret: str, payload: str) -> bool:
    """Whether the secret survives in the payload: by digits for a number of six or more
    digits (separators and line breaks ignored); else whole (folded), or any word of it of
    three or more characters standing as a word in the payload ("Kopi" of a password)."""
    digits = "".join(ch for ch in secret if ch.isdigit())
    if len(digits) >= 6 and len(digits) * 2 >= len(fold(secret)):
        return digits in "".join(ch for ch in payload if ch.isdigit())
    if fold(secret) and fold(secret) in fold(payload):
        return True
    words = set(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", payload).casefold()))
    return any(word in words for word in re.findall(r"[^\W_]{3,}", secret.casefold()))


class Miss(NamedTuple):
    id: str
    kind: str
    problem: str  # "outcome:<outcome>", "leaked" or "lost a fact"; never the payload


class Report(NamedTuple):
    misses: tuple[Miss, ...]  # new misses: the app's test fails on these
    known: tuple[str, ...]  # known misses that still miss
    fixed: tuple[str, ...]  # known misses that now pass: drop them from `known`
    skipped: tuple[str, ...]  # cases for a path the app didn't give
    counts: dict  # {(path, kind): {outcome: n}}

    def ok(self) -> bool:
        return not self.misses and not self.fixed


def _check(case: Case, outcome: str, payload: str) -> str | None:
    if not EXPECT[case.expect](outcome):
        return f"outcome:{outcome}"
    if outcome != "refused" and any(leaks(secret, payload) for secret in case.secret):
        return "leaked"
    if any(kept not in payload for kept in case.keep):
        return "lost a fact"
    return None


def run(
    search: Gate | None = None,
    message: Gate | None = None,
    document: Gate | None = None,
    known: Iterable[str] = (),
    cases: Iterable[Case] = CASES,
) -> Report:
    """Every case through the app's gates. `known`: case ids the app knowingly misses."""
    gates = {"search": search, "message": message, "document": document or message}
    known = set(known)
    misses, still, fixed, skipped, counts = [], [], [], [], {}
    for case in cases:
        gate = gates[case.path]
        if gate is None:
            skipped.append(case.id)
            continue
        outcome, payload = gate(case.text)
        tally = counts.setdefault((case.path, case.kind), {})
        tally[outcome] = tally.get(outcome, 0) + 1
        problem = _check(case, outcome, payload)
        if problem and case.id in known:
            still.append(case.id)
        elif problem:
            misses.append(Miss(case.id, case.kind, problem))
        elif case.id in known:
            fixed.append(case.id)
    unknown = known - {case.id for case in cases}
    fixed += sorted(unknown)  # a stale id is reported, never silently ignored
    return Report(tuple(misses), tuple(still), tuple(fixed), tuple(skipped), counts)


def table(report: Report) -> str:
    """A value-free summary to print in an app's test run."""
    lines = [
        f"{path:<9} {kind:<9} {dict(sorted(tally.items()))}"
        for (path, kind), tally in sorted(report.counts.items())
    ]
    lines.append(
        f"new misses {len(report.misses)}, known {len(report.known)}, "
        f"fixed {len(report.fixed)}, skipped {len(report.skipped)}"
    )
    lines += [f"  miss {miss.id}: {miss.problem}" for miss in report.misses]
    return "\n".join(lines)
