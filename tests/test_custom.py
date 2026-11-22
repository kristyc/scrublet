"""The owner's own patterns and the always-hide list (ADR 0007). Invented words only."""

import json
import time

import pytest

from scrublet_pii import custom, terms


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRUBLET_HOME", str(tmp_path / "home"))
    terms._cache.clear()
    return tmp_path / "home" / "terms.json"


# --- shapes ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sample", "shape"),
    [("ab-123456", "AA-999999"), ("QZ 12 3456", "AA 99 9999"), ("M0000123", "A9999999")],
)
def test_a_shape_keeps_separators_and_generalises_letters_and_digits(sample, shape):
    assert custom.shape_of(sample) == shape


def test_a_shape_matches_its_format_and_not_numbers_that_run_into_other_digits():
    found = custom.compile_pattern("shape", "AA-999999")
    assert found.search("policy QX-482913 renewed") and found.search("zz-000001")
    assert not found.search("QX-4829137") and not found.search("QX-48291")
    assert not found.search("xQX-482913") and not found.search("123456")


@pytest.mark.parametrize("sample", ["", "  ", "12", "ab-12", "x" * 65, "9" + chr(11) + "999999"])
def test_a_shape_too_short_or_odd_is_refused(sample):
    with pytest.raises(custom.Invalid):
        custom.shape_of(sample)


# --- regex grammar ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", [r"[A-Z]{2}\d{6}", r"MEM-\d{4,8}", r"(?:ab|cd)\d{6}", r"\d+-\d+", r"[A-Z]\d{3}[a-z]?"]
)
def test_simple_regexes_are_taken(text):
    assert custom.compile_pattern("regex", text).pattern == text


@pytest.mark.parametrize(
    "text",
    [
        r"(a+)+b",  # nested quantifier
        r"(\d+)*",  # quantifier on a group
        r"(?=x)abc123",  # lookaround
        r"(?i)abc123",  # flags
        r"(\d)\1\d{4}",  # backreference
        r"a*b*c*d*e*",  # too many unbounded repeats
        r"\d{1,999}",  # a huge bound
        r"\d{5,2}",  # backwards bound
        r"a?b?c?d?e?x",  # too many quantifiers
        r"*abc",  # nothing to repeat
        r"a+?b",  # stacked quantifiers
        r"\d*",  # matches nothing: the empty string
        r"[a-z",  # not closed
        "x" * 201,
        "",
    ],
)
def test_dangerous_or_empty_regexes_are_refused_without_quoting_them(text):
    with pytest.raises(custom.Invalid) as error:
        custom.compile_pattern("regex", text)
    assert text not in str(error.value) or text == ""


def test_matching_a_long_hostile_input_stays_fast_for_every_accepted_pattern():
    for text in (r"[A-Z]{2}\d{6}", r"\d+-\d+", r"a+b+", r"(?:x|y)\d+z+"):
        found = custom.compile_pattern("regex", text)
        started = time.perf_counter()
        found.search("a" * 5000 + "1" * 5000 + "-" * 5000)
        assert time.perf_counter() - started < 1.0


def test_an_unknown_kind_is_refused():
    with pytest.raises(custom.Invalid):
        custom.compile_pattern("glob", "AA-999999")


# --- the store -------------------------------------------------------------------------


def test_patterns_are_stored_once_by_a_stable_id_and_removed_by_it(store):
    first = terms.add_pattern("AA-999999")
    again = terms.add_pattern(" AA-999999 ")
    assert first.id == again.id and first.id.startswith("p-") and first.at.endswith("Z")
    assert terms.read().patterns() == (first,)
    saved = json.loads(store.read_text(encoding="utf-8"))
    assert saved["schema"] == 2 and saved["custom_patterns"][0]["text"] == "AA-999999"
    terms.add_pattern(r"MEM-\d{4,8}", kind="regex")
    terms.add_pattern("AA-999999", scope="work")
    assert len(terms.read().custom_patterns) == 3 and len(terms.read().patterns("work")) == 1
    terms.remove_pattern(first.id)
    assert [i.text for i in terms.read().patterns()] == [r"MEM-\d{4,8}"]
    terms.remove_pattern("p-unknown")
    assert len(terms.read().custom_patterns) == 2


def test_a_bad_pattern_is_refused_before_anything_is_written(store):
    for kind, text in (("regex", "(a+)+b"), ("shape", "12"), ("glob", "AA-999999")):
        with pytest.raises(custom.Invalid):
            terms.add_pattern(text, kind=kind)
    with pytest.raises(terms.Refused):
        terms.add_pattern("AA-999999", scope="")
    assert not store.exists()


def test_the_pattern_count_is_capped(store):
    for index in range(terms.MAX_PATTERNS):
        terms.add_pattern(f"MEM{index:03d}-\\d{{6}}", kind="regex")
    with pytest.raises(terms.Refused):
        terms.add_pattern("ZZ-999999")
    assert len(terms.read().custom_patterns) == terms.MAX_PATTERNS


# --- the always-hide list --------------------------------------------------------------


def test_always_hide_is_a_third_list_and_hiding_wins_over_always_ok(store):
    terms.update("always_ok", add=["Sam Recipient"])
    terms.update("always_hide", add=["Sam Recipient", "Alex Example"])
    found = terms.read()
    assert found.words("always_hide") == ("Sam Recipient", "Alex Example")
    assert found.words("always_ok") == ()  # hiding wins: it left always-OK
    with pytest.raises(terms.Refused):
        terms.update("always_ok", add=["alex example"])
    terms.update("always_hide", remove=["ALEX EXAMPLE"])
    assert terms.read().words("always_hide") == ("Sam Recipient",)
    terms.update("always_ok", add=["Alex Example"])  # no longer hidden, so it may be OK again
    assert terms.read().words("always_ok") == ("Alex Example",)


def test_always_hide_and_never_send_are_independent_lists(store):
    terms.update("never_send", add=["Pat Placeholder"])
    terms.update("always_hide", add=["Pat Placeholder"])
    found = terms.read()
    assert found.words("never_send") == found.words("always_hide") == ("Pat Placeholder",)


def test_a_store_without_the_newer_lists_stays_schema_1_for_older_libraries(store):
    terms.update("never_send", add=["Alex Example"])
    saved = json.loads(store.read_text(encoding="utf-8"))
    assert saved["schema"] == 1 and "always_hide" not in saved and "custom_patterns" not in saved
    terms.update("always_hide", add=["Sam Recipient"])
    assert json.loads(store.read_text(encoding="utf-8"))["schema"] == 2
    terms.update("always_hide", remove=["Sam Recipient"])
    assert json.loads(store.read_text(encoding="utf-8"))["schema"] == 1


def test_a_schema_1_store_written_by_an_older_library_still_reads(store):
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps({"schema": 1, "never_send": [{"text": "Alex Example", "scope": "general"}]}),
        encoding="utf-8",
    )
    found = terms.read()
    assert found.words("never_send") == ("Alex Example",)
    assert found.always_hide == () and found.custom_patterns == ()


def test_a_hand_edited_unsafe_pattern_makes_the_store_unreadable_not_active(store):
    store.parent.mkdir(parents=True)
    raw = {"schema": 2, "custom_patterns": [{"id": "p-x", "kind": "regex", "text": "(a+)+b"}]}
    store.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(terms.Unreadable):
        terms.read()
    assert terms.problems() == {"store": "unreadable"}


def test_the_new_writers_obey_the_production_guard(monkeypatch):
    monkeypatch.delenv("SCRUBLET_HOME")
    for call in (
        lambda: terms.add_pattern("AA-999999"),
        lambda: terms.remove_pattern("p-x"),
        lambda: terms.update("always_hide", add=["Alex Example"]),
    ):
        with pytest.raises(terms.NotProduction):
            call()


def test_status_counts_the_newer_lists_and_import_accepts_always_hide(store, tmp_path, capsys):
    terms.update("always_hide", add=["Alex Example"])
    terms.add_pattern("AA-999999")
    assert terms.main(["status"]) == 0
    assert "1 always-hide, 1 patterns" in capsys.readouterr().out
    words = tmp_path / "words.json"
    words.write_text(json.dumps(["Sam Recipient"]), encoding="utf-8")
    assert terms.main(["import-words", str(words), "--id", "t1", "--list", "always_hide"]) == 0
    assert terms.read().words("always_hide") == ("Alex Example", "Sam Recipient")
