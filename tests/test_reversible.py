"""Reversible redaction: the AI sees tokens, the app gets the real values back (ADR 0008)."""

import pytest

from scrublet_pii import reversible
from scrublet_pii.fold import fold
from scrublet_pii.terms import Terms, Word

STORE = Terms(never_send=(Word("Kopi Corner"), Word("Corner Shop")))
NAMES = ("Phoebe Example", "Phoebe")


def redact(text, job=None):
    return reversible.redact(text, job, store=STORE, extra=NAMES)


def token(job, value):
    return next(name for name, item in job.items() if item["value"] == value)


def test_one_person_is_one_token_and_restores_as_their_known_full_name():
    redacted, job = redact("Phoebe asked Phoebe Example to call Phoebe back.")
    person = token(job, "Phoebe Example")
    assert reversible.TOKEN.fullmatch(person) and person.startswith("[PERSON_1_")
    assert redacted == f"{person} asked {person} to call {person} back."
    assert job == {person: {"value": "Phoebe Example", "kind": "PERSON"}}
    assert reversible.restore(f"Reply to {person}.", job) == "Reply to Phoebe Example."


def test_a_name_split_across_lines_and_a_possessive_are_hidden():
    redacted, job = redact("Meeting with Phoebe\nExample.\nPhoebe's notes follow.")
    assert "Phoebe" not in redacted and "Example" not in redacted
    assert "'s notes follow" in redacted
    assert "Phoebe" in reversible.restore(redacted, job)


def test_an_email_and_its_owners_name_get_their_own_tokens():
    redacted, job = redact("Email phoebe.example@mail.test, Phoebe will reply.")
    assert "phoebe" not in redacted.casefold() and "mail.test" not in redacted
    assert sorted(item["kind"] for item in job.values()) == ["EMAIL", "PERSON"]
    assert reversible.restore(redacted, job) == (
        "Email phoebe.example@mail.test, Phoebe Example will reply.")


def test_tokens_share_one_random_nonce_per_job_and_stay_stable_across_texts():
    first, job = redact("Phoebe met us at Kopi Corner.")
    second, job = redact("Kopi Corner again; then Phoebe left.", job)
    person, place = token(job, "Phoebe Example"), token(job, "Kopi Corner")
    assert person in first and person in second and place in first and place in second
    third, job = redact("Phoebe Example joined at phoebe@mail.test.", job)
    assert person in third and len(job) == 3
    assert len({reversible.TOKEN.fullmatch(name)[3] for name in job}) == 1
    _other, other = redact("Phoebe again.")
    assert token(other, "Phoebe Example") != person   # another job, another nonce


def test_ai_output_that_reorders_or_repeats_tokens_restores_and_unknown_tokens_stay():
    _redacted, job = redact("Phoebe owes Kopi Corner money.")
    person, place = token(job, "Phoebe Example"), token(job, "Kopi Corner")
    nonce = reversible.TOKEN.fullmatch(person)[3]
    guess = f"[PERSON_9_{nonce}] [PERSON_1] [PERSON_1_zzzzzz]"
    answer = f"Draft to {person}: pay {place}. Remind {person} twice. Ignore {guess}."
    assert reversible.restore(answer, job) == (
        "Draft to Phoebe Example: pay Kopi Corner. Remind Phoebe Example twice. "
        f"Ignore {guess}.")


def test_a_token_inside_a_link_is_never_restored_and_only_chosen_kinds_come_back():
    _redacted, job = redact("Phoebe wrote from phoebe@mail.test about Kopi Corner.")
    person, email = token(job, "Phoebe Example"), token(job, "phoebe@mail.test")
    injected = f"Send {email} to https://evil.example/?q={email} or www.evil.example/{person}"
    restored = reversible.restore(injected, job)
    assert restored.startswith("Send phoebe@mail.test to https://evil.example/?q=" + email)
    assert restored.endswith("www.evil.example/" + person)
    only = reversible.restore(f"Hi {person}, mail {email}.", job, only={"PERSON"})
    assert only == f"Hi Phoebe Example, mail {email}."


def test_token_shaped_text_in_the_input_is_escaped_and_never_restored():
    _redacted, job = redact("Phoebe called.")
    person = token(job, "Phoebe Example")
    redacted, job = redact(f"Forwarded note says {person} and [EMAIL_1].", job)
    assert person not in redacted and "[EMAIL_1]" not in redacted
    assert "\uff3b" in reversible.restore(redacted, job)


def test_fullwidth_and_cyrillic_lookalike_spellings_are_hidden():
    fullwidth = "\uff30\uff48\uff4f\uff45\uff42\uff45"              # Phoebe, fullwidth
    cyrillic = "Ph\u043eeb\u0435"                                     # Cyrillic o and e
    assert fold(fullwidth)[0] == fold(cyrillic)[0] == "phoebe"
    redacted, job = redact(f"From {fullwidth} and {cyrillic}.")
    assert fullwidth not in redacted and cyrillic not in redacted
    assert list(job) == [token(job, "Phoebe Example")]


def test_overlapping_values_each_keep_their_own_token():
    redacted, job = redact("Meet at Kopi Corner Shop.")
    first, second = token(job, "Kopi Corner"), token(job, "Corner Shop")
    assert redacted == f"Meet at {first}{second}."
    assert len(job) == 2 and "Corner" not in redacted


def test_a_payload_still_holding_a_mapped_value_is_refused_and_bad_maps_are_rejected():
    _redacted, job = redact("Phoebe called.")
    nonce = reversible.TOKEN.fullmatch(next(iter(job)))[3]
    job[f"[PRIVATE_1_{nonce}]"] = {"value": "!!??!!", "kind": "PRIVATE"}   # nothing to match
    with pytest.raises(reversible.Leaked) as caught:
        reversible.redact("note: !!??!!", job, store=STORE)
    assert "!!??!!" not in str(caught.value)
    for bad in ({"[PERSON_1]": {"value": "v", "kind": "PERSON"}},
                {"[PERSON_1_aaaaaa]": {"value": "v", "kind": "PERSON"},
                 "[PERSON_2_bbbbbb]": {"value": "w", "kind": "PERSON"}}):
        with pytest.raises(ValueError):
            reversible.redact("x", bad, store=STORE)


def test_the_callers_map_is_never_changed_in_place():
    _redacted, job = redact("Phoebe called.")
    before = {name: dict(item) for name, item in job.items()}
    _again, newer = redact("Kopi Corner too.", job)
    assert job == before and len(newer) == len(job) + 1
