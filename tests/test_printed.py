"""The merged name matcher (ADR 0003). Synthetic names only."""

import pytest

from scrublet_pii import corpus, printed

NAME = "Tan Ah Kow"


def found(text, values=(NAME,), whole=frozenset()):
    return sorted({text[a:b] for a, b, _v in printed.matches(text, values, whole)})


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("TAN\nAH  KOW paid", "TAN\nAH  KOW"),  # split and spaced
        ("PAYMENTTOTAN AH KOW", "TAN AH KOW"),  # glued, whole value of 8+
        ("TAN AH K", "TAN AH K"),  # cut at the field width
        ("AH KOW TAN", "AH KOW TAN"),  # reordered
        ("KOW, TAN AH", "KOW, TAN AH"),
        ("T. AH KOW", "T. AH KOW"),  # an initial
        ("KOW A T", "KOW A T"),  # reversed with initials
    ],
)
def test_a_name_is_found_as_statements_print_it(text, hit):
    assert hit in found(text)


@pytest.mark.parametrize(
    "text",
    [
        "STANDUP AH KOWLOON",  # no word edge
        "tahkow",  # an initial must be a capital standing alone
        "TAHKOW",
        "Dr Tan said so",  # one short word of the name
        "A K",  # never every word an initial
    ],
)
def test_no_match_inside_words_or_on_initials_alone(text):
    assert found(text) == []


def test_markers_stay_out_of_the_extra_forms_and_short_words_need_their_marker():
    name = "Kumar a/p Raj"
    assert "RAJ KUMAR" in found("RAJ KUMAR", (name,))
    assert "KUMAR A / P RAJ" in found("KUMAR A / P RAJ", (name,))
    assert found("Siti Aminah BT ABU", ("Siti Aminah binti Abu",))
    assert found("Abu Dhabi trip", ("Siti Aminah binti Abu",)) == []


def test_a_whole_phrase_value_gets_no_extra_forms():
    whole = frozenset({NAME})
    assert found("TAN AH KOW", whole=whole) == ["TAN AH KOW"]
    assert found("AH KOW TAN", whole=whole) == [] and found("T. AH KOW", whole=whole) == []
    shop = "Kedai Malaysian Trading"
    assert found("Malaysian", (shop,), frozenset({shop})) == []
    assert found("Malaysian", (shop,)) == ["Malaysian"]


def test_numbers_match_on_digits_inside_a_run():
    assert found("REF0051401234567800", ("5140 1234 5678",)) == ["514012345678"]


def test_long_names_use_listed_and_reversed_orders_only():
    name = "Alpha Bravo Charlie Delta Echo"
    assert len({needle for needle, initials in printed.forms(name) if not initials}) == 1
    assert printed.forms("Alpha") == () and printed.forms("12 Jalan Alpha") == ()


def test_every_printed_and_never_send_corpus_text_is_found():
    values = (*corpus.NEVER_SEND, *corpus.LINKED)
    texts = [
        text for text, secret in (*corpus.NEVER, *corpus.LINKED_TEXT, *corpus.PRINTED) if secret
    ]
    assert [text for text in texts if not printed.matches(text, values)] == []
