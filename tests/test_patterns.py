"""Hard detectors (ADR 0002), measured on the shared corpus. Public test numbers only."""

import pytest

from scrublet_pii import corpus, fold, patterns

HARD = {
    "pattern.credential",
    "pattern.card",
    "pattern.ic",
    "pattern.passport",
    "pattern.account",
    "pattern.key",
}


@pytest.mark.parametrize("name", sorted(corpus.HARD))
def test_every_hard_corpus_item_is_found_and_its_secret_is_covered(name):
    text, _kind, secret = corpus.HARD[name]
    assert set(patterns.kinds(text)) & HARD, name
    covered = "".join(
        ch if any(a <= at < b for a, b, _n in patterns.find(text)) else " "
        for at, ch in enumerate(text)
    )
    assert corpus.leaks(secret, covered), name  # the hits span the whole secret


@pytest.mark.parametrize("query", corpus.SEARCHES)
def test_an_everyday_search_has_no_hard_item(query):
    assert not set(patterns.kinds(query)) & HARD, query


@pytest.mark.parametrize(
    ("text", "card"),
    [
        ("4111 1111 1111 1111", True),
        ("order 123-4567890-1234567", False),
        ("Lazada order 312345678901234", False),
        ("REF 41111111111111110001", True),
        ("4111 1111 1111 1112", False),
    ],
)
def test_a_card_needs_a_network_prefix_luhn_and_printed_groups(text, card):
    assert (patterns.CARD.search(text) is not None) is card


def test_an_ic_needs_its_groups_or_an_ic_word_and_the_label_is_kept():
    assert "pattern.ic" not in patterns.kinds("order 261122123456")
    text = "IC 900101145678"
    ((start, stop, _name),) = [hit for hit in patterns.find(text) if hit[2] == "pattern.ic"]
    assert text[start:stop] == "900101145678"


def test_names_are_unique_value_free_and_grouped():
    names = [d.name for d in patterns.pack("my")]
    assert len(names) == len(set(names)) and all(n.startswith("pattern.") for n in names)
    assert {d.group for d in patterns.pack("my")} == {"identity", "financial", "credential"}


def test_fold_keeps_an_index_back_to_the_printed_text():
    folded, index = fold.fold("TAN\nAh  Kow")
    assert folded == "tanahkow" and index[3] == 4 and index[-1] == 10
