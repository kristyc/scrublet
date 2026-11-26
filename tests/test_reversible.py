"""Reversible redaction: the AI sees tokens, the app gets the real values back (ADR 0008)."""

import pytest

from scrublet_pii import reversible
from scrublet_pii.terms import Terms, Word

STORE = Terms(never_send=(Word("Kopi Corner"),))
NAMES = ("Phoebe Example", "Phoebe")


def redact(text, job=None):
    return reversible.redact(text, job, store=STORE, extra=NAMES)


def test_one_person_is_one_token_and_restores_as_their_known_full_name():
    text = "Phoebe asked Phoebe Example to call Phoebe back."
    redacted, job = redact(text)
    assert redacted == "[PERSON_1] asked [PERSON_1] to call [PERSON_1] back."
    assert job == {"[PERSON_1]": {"value": "Phoebe Example", "kind": "PERSON"}}
    assert reversible.restore("Reply to [PERSON_1].", job) == "Reply to Phoebe Example."


def test_a_name_split_across_lines_and_a_possessive_are_hidden():
    redacted, job = redact("Meeting with Phoebe\nExample.\nPhoebe's notes follow.")
    assert "Phoebe" not in redacted and "Example" not in redacted
    assert "'s notes follow" in redacted
    assert "Phoebe" in reversible.restore(redacted, job)


def test_an_email_and_its_owners_name_get_their_own_tokens():
    redacted, job = redact("Email phoebe.example@mail.test, Phoebe will reply.")
    assert "phoebe" not in redacted.casefold() and "mail.test" not in redacted
    kinds = sorted(item["kind"] for item in job.values())
    assert kinds == ["EMAIL", "PERSON"]
    assert reversible.restore(redacted, job) == (
        "Email phoebe.example@mail.test, Phoebe Example will reply.")


def test_tokens_stay_stable_across_texts_in_one_job_and_numbering_continues():
    first, job = redact("Phoebe met us at Kopi Corner.")
    second, job = redact("Kopi Corner again; then Phoebe left.", job)
    token = next(token for token, item in job.items() if item["kind"] == "PERSON")
    place = next(token for token, item in job.items() if item["value"] == "Kopi Corner")
    assert token in first and token in second and place in first and place in second
    third, job = redact("Phoebe Example joined Ann at phoebe@mail.test.", job)
    assert token in third and "[EMAIL_1]" in third and len(job) == 3


def test_ai_output_that_reorders_or_repeats_tokens_restores_and_unknown_tokens_stay():
    _redacted, job = redact("Phoebe owes Kopi Corner money.")
    person = next(token for token, item in job.items() if item["kind"] == "PERSON")
    place = next(token for token, item in job.items() if item["value"] == "Kopi Corner")
    answer = f"Draft to {person}: pay {place}. Remind {person} twice. Ignore [PERSON_99]."
    assert reversible.restore(answer, job) == ("Draft to Phoebe Example: pay Kopi Corner. "
                                              "Remind Phoebe Example twice. Ignore [PERSON_99].")


def test_a_payload_still_holding_a_mapped_value_is_refused_and_bad_maps_are_rejected():
    _redacted, job = redact("Phoebe called.")
    job["[PRIVATE_1]"] = {"value": "!!??!!", "kind": "PRIVATE"}   # no letter or digit to match
    with pytest.raises(reversible.Leaked) as caught:
        reversible.redact("note: !!??!!", job, store=STORE)
    assert "!!??!!" not in str(caught.value)
    with pytest.raises(ValueError):
        reversible.redact("x", {"not-a-token": {"value": "v", "kind": "PERSON"}}, store=STORE)


def test_the_callers_map_is_never_changed_in_place():
    _redacted, job = redact("Phoebe called.")
    before = {token: dict(item) for token, item in job.items()}
    _again, newer = redact("Kopi Corner too.", job)
    assert job == before and len(newer) == len(job) + 1
