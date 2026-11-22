"""The shared corpus and its runner: the data is sound and the runner never passes a leak."""
import re

from tacitkit import corpus


def luhn(digits: str) -> bool:
    total = sum(int(d) if n % 2 == 0 else sum(divmod(int(d) * 2, 10))
                for n, d in enumerate(reversed(digits)))
    return total % 10 == 0


def test_case_ids_are_unique_and_every_secret_and_fact_is_in_its_text():
    ids = [case.id for case in corpus.CASES]
    assert len(ids) == len(set(ids))
    for case in corpus.CASES:
        assert all(corpus.leaks(secret, case.text) for secret in case.secret), case.id
        assert all(kept in case.text for kept in case.keep), case.id
        assert case.expect in corpus.EXPECT and case.path in {"search", "message", "document"}


def test_card_numbers_are_public_test_values():
    for text, kind, secret in corpus.HARD.values():
        if kind == "card":
            assert luhn(secret) and secret[:4] in {"4111", "5555", "3782"}, text


def test_leaks_reads_numbers_by_digits_and_words_folded():
    assert corpus.leaks("4111111111111111", "x 4111-1111\n1111 1111 y")
    assert not corpus.leaks("4111111111111111", "x [card] y 1111")
    assert corpus.leaks("Tan Ah Kow", "PAYMENTTOTAN AH KOW")
    assert not corpus.leaks("Tan Ah Kow", "PAYMENTTO[name]")
    assert not corpus.leaks("", "anything")


def perfect(text):
    """A gate that refuses every listed or hard item and hides nothing else."""
    for case in corpus.CASES:
        if case.text == text and case.kind not in {"everyday", "facts"}:
            return "refused", ""
    return "sent", text


def hiding(text):
    """Hides only digits: misses names, fine for cards."""
    hidden = re.sub(r"\d", "#", text)
    return ("hidden" if hidden != text else "sent"), hidden


def test_a_sound_gate_has_no_misses_and_every_path_runs():
    report = corpus.run(search=perfect, message=lambda t: ("hidden", "[x]")
                        if perfect(t)[0] == "refused" else ("sent", t))
    assert report.ok() and report.skipped == () and report.known == ()
    assert "new misses 0" in corpus.table(report)


def test_leaks_wrong_outcomes_and_lost_facts_are_misses_and_name_no_payload():
    report = corpus.run(search=hiding, message=hiding)
    problems = {miss.id: miss.problem for miss in report.misses}
    assert problems["search.everyday.0"] == "outcome:hidden"          # a search was changed
    assert problems["message.hard.password"] == "leaked"              # letters survived
    assert "message.hard.card" not in problems                        # digits all hidden
    assert problems["document.facts.0"] == "lost a fact"
    assert problems["search.never.0"] == "outcome:sent"
    assert all("Melati" not in line for line in corpus.table(report).splitlines()[1:])


def test_known_misses_are_reported_and_shrink():
    known = {"search.everyday.0", "search.hard.card", "no.such.case"}
    report = corpus.run(search=hiding, known=known)
    assert "search.everyday.0" in report.known
    assert set(report.fixed) == {"search.hard.card", "no.such.case"} and not report.ok()
    assert report.skipped and all(not i.startswith("search.") for i in report.skipped)
