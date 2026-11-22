"""The production guard (ADR 0006): the real profile store resolves only for a process that
declared production and is not a test run. These tests prove a test run can never reach it,
including the way it once leaked: a test undid its scratch-store setting, then booted an app."""

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from scrublet_pii import terms

SRC = str(Path(__file__).resolve().parents[1] / "src")
WORD = "Alex Example"


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A fake user profile: where the real store would be. Nothing here is the real one."""
    roaming = tmp_path / "profile"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(roaming))
    monkeypatch.setenv("HOME", str(roaming))
    return roaming


def untouched(profile):
    return not (terms.default_home().exists() or terms.default_home("tacitkit").exists())


def declare_everything(monkeypatch):
    terms.production()
    monkeypatch.setenv("SCRUBLET_PRODUCTION", "1")


def child(code, profile, *, keep_test_env=False, **env):
    """Run `code` in a fresh interpreter: not a test run unless keep_test_env is set."""
    base = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTEST_CURRENT_TEST", "SCRUBLET_HOME", "TACITKIT_HOME", "SCRUBLET_PRODUCTION"}
    }
    if keep_test_env:
        base["PYTEST_CURRENT_TEST"] = os.environ.get("PYTEST_CURRENT_TEST", "t::test (call)")
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env={**base, "PYTHONPATH": SRC, **env},
    )


def test_a_test_that_undoes_its_scratch_store_then_boots_an_app_still_cannot_reach_the_real_one(
    profile, monkeypatch
):
    # exactly the leak: the per-test store setting is removed, then production start-up runs
    monkeypatch.undo()
    monkeypatch.setenv("APPDATA", str(profile))  # a fake profile only, so nothing real is at risk
    monkeypatch.setenv("XDG_CONFIG_HOME", str(profile))
    monkeypatch.setenv("HOME", str(profile))
    assert "SCRUBLET_HOME" not in os.environ and "TACITKIT_HOME" not in os.environ

    def boot():  # what an app's real start-up does
        terms.production()
        terms.update("never_send", add=[WORD])

    try:
        with pytest.raises(terms.NotProduction):
            boot()
    finally:
        terms._production = False
    assert untouched(profile)


def test_it_still_refuses_when_the_test_also_removes_the_pytest_environment_variable(
    profile, monkeypatch
):
    monkeypatch.undo()
    monkeypatch.setenv("APPDATA", str(profile))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(profile))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert terms.under_test()  # found through sys.modules, with no variable to remove
    (profile.parent / "words.json").write_text('["Old Word"]', encoding="utf-8")
    monkeypatch.setenv("SCRUBLET_PRODUCTION", "1")
    terms.production()
    try:
        for call in (
            terms.read,
            terms.home,
            terms.problems,
            lambda: terms.update("never_send", add=[WORD]),
            lambda: terms.register_source("a.b", Path.cwd() / "x.json"),
            lambda: terms.import_words(profile.parent / "words.json", "x"),
        ):
            with pytest.raises(terms.NotProduction):
                call()
    finally:
        terms._production = False
    assert untouched(profile)


def test_production_declared_outside_a_test_resolves_the_real_store_and_only_then(profile):
    run = child(
        "from scrublet_pii import terms; terms.production(); terms.update('never_send', add=['Alex Example']);"
        "print(terms.home())",
        profile,
    )
    assert run.returncode == 0, run.stderr
    assert Path(run.stdout.strip()) == terms.default_home()
    stored = json.loads((terms.default_home() / "terms.json").read_text(encoding="utf-8"))
    assert stored["never_send"]


def test_a_process_that_did_not_declare_production_refuses_instead_of_guessing(profile):
    run = child("from scrublet_pii import terms; terms.read()", profile)
    assert run.returncode != 0 and "NotProduction" in run.stderr
    assert untouched(profile)


def test_the_environment_flag_declares_production_for_a_service_that_starts_without_code(profile):
    run = child(
        "from scrublet_pii import terms; print(len(terms.read().never_send))",
        profile,
        SCRUBLET_PRODUCTION="1",
    )
    assert run.returncode == 0, run.stderr and run.stdout.strip() == "0"


def test_a_child_process_of_a_test_cannot_reach_the_real_store_even_if_it_declares_production(
    profile,
):
    run = child(
        "from scrublet_pii import terms; terms.production(); terms.read()",
        profile,
        keep_test_env=True,
        SCRUBLET_PRODUCTION="1",
    )
    assert run.returncode != 0 and "NotProduction" in run.stderr
    assert untouched(profile)


def test_an_explicit_scratch_folder_works_anywhere_including_a_test_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRUBLET_HOME", str(tmp_path / "mine"))
    terms.update("never_send", add=[WORD])
    assert (tmp_path / "mine" / "terms.json").is_file()


def test_an_explicit_path_is_used_as_given_so_a_tool_can_open_any_file(tmp_path):
    target = tmp_path / "elsewhere.json"
    terms.update("never_send", add=[WORD], path=target)
    assert terms.read(target).words("never_send") == (WORD,)


def test_the_old_variable_still_works_for_one_version_with_a_deprecation_warning(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("SCRUBLET_HOME")
    monkeypatch.setenv("TACITKIT_HOME", str(tmp_path / "old"))
    monkeypatch.setattr(terms, "_warned", False)
    with pytest.warns(DeprecationWarning, match="SCRUBLET_HOME"):
        assert terms.home() == tmp_path / "old"


def test_the_new_variable_wins_and_says_nothing_about_the_old_one(tmp_path, monkeypatch):
    monkeypatch.setenv("TACITKIT_HOME", str(tmp_path / "old"))
    monkeypatch.setattr(terms, "_warned", False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert terms.home() == tmp_path / "scratch-store"


# --- the move from the old store folder ------------------------------------------------

OLD = {
    "schema": 1,
    "never_send": [{"text": "Old Word", "scope": "general"}],
    "always_ok": [],
    "sources": [],
    "imports": [],
}


def legacy_store(profile):
    folder = terms.default_home("tacitkit")
    folder.mkdir(parents=True)
    raw = json.dumps(OLD).encode()
    (folder / "terms.json").write_bytes(raw)
    return folder / "terms.json", raw


def test_before_the_move_the_old_store_is_still_the_store_and_nothing_is_created(profile):
    legacy_store(profile)
    run = child(
        "from scrublet_pii import terms; terms.production(); print(terms.read().words('never_send'))",
        profile,
    )
    assert run.returncode == 0, run.stderr
    assert "Old Word" in run.stdout and not terms.default_home().exists()


def test_the_first_write_moves_the_store_losslessly_and_leaves_the_old_one_as_it_was(profile):
    legacy, raw = legacy_store(profile)
    code = "from scrublet_pii import terms; terms.production(); terms.update('never_send', add=['New Word'])"
    assert child(code, profile).returncode == 0
    moved = json.loads((terms.default_home() / "terms.json").read_text(encoding="utf-8"))
    assert {w["text"] for w in moved["never_send"]} == {"Old Word", "New Word"}
    assert legacy.read_bytes() == raw  # the old file is untouched
    assert (terms.default_home() / "migrated-from-tacitkit.json").is_file()


def test_the_move_happens_once_and_a_second_run_changes_nothing_but_its_own_edit(profile):
    legacy_store(profile)
    code = (
        "from scrublet_pii import terms; terms.production(); terms.update('never_send', add=['{}'])"
    )
    child(code.format("One"), profile)
    note = (terms.default_home() / "migrated-from-tacitkit.json").read_text(encoding="utf-8")
    child(code.format("Two"), profile)
    final = json.loads((terms.default_home() / "terms.json").read_text(encoding="utf-8"))
    assert {w["text"] for w in final["never_send"]} == {"Old Word", "One", "Two"}
    assert (terms.default_home() / "migrated-from-tacitkit.json").read_text(
        encoding="utf-8"
    ) == note


def test_when_both_exist_the_new_store_wins_and_the_old_is_never_merged_in(profile):
    legacy_store(profile)
    new = terms.default_home()
    new.mkdir(parents=True)
    (new / "terms.json").write_text(json.dumps({**OLD, "never_send": []}), encoding="utf-8")
    run = child(
        "from scrublet_pii import terms; terms.production(); terms.update('never_send', add=['X Y']);"
        "print(terms.read().words('never_send'))",
        profile,
    )
    assert "Old Word" not in run.stdout and "X Y" in run.stdout


def test_a_damaged_old_store_is_copied_as_it_is_and_stays_unreadable_for_the_owner_to_repair(
    profile,
):
    legacy, _ = legacy_store(profile)
    legacy.write_bytes(b"{broken")
    run = child(
        "from scrublet_pii import terms; terms.production(); terms.update('never_send', add=['A B'])",
        profile,
    )
    assert run.returncode != 0 and "Unreadable" in run.stderr
    assert (terms.default_home() / "terms.json").read_bytes() == b"{broken"
    assert legacy.read_bytes() == b"{broken"


def test_the_move_swaps_a_temp_file_in_and_leaves_no_temp_file_behind(tmp_path):
    old, new = tmp_path / "old" / "terms.json", tmp_path / "new" / "terms.json"
    old.parent.mkdir()
    new.parent.mkdir()
    old.write_bytes(json.dumps(OLD).encode())
    terms._migrate(new, old)
    terms._migrate(new, old)  # idempotent
    assert new.read_bytes() == old.read_bytes()
    assert sorted(p.name for p in new.parent.iterdir()) == [
        "migrated-from-tacitkit.json",
        "terms.json",
    ]


def test_problems_reports_an_app_still_writing_to_the_old_store_after_the_move(profile):
    legacy, _ = legacy_store(profile)
    child(
        "from scrublet_pii import terms; terms.production(); terms.update('never_send', add=['A B'])",
        profile,
    )
    code = "from scrublet_pii import terms; terms.production(); print(terms.problems())"
    assert child(code, profile).stdout.strip() == "{}"
    legacy.write_bytes(legacy.read_bytes() + b"\n")  # an old-library app wrote there
    assert "'legacy': 'changed'" in child(code, profile).stdout


def test_the_old_import_name_still_works_for_one_version_and_is_the_same_module():
    code = (
        "import warnings; warnings.simplefilter('always'); import tacitkit; from tacitkit import terms; "
        "import scrublet_pii.terms as new; print(terms is new, tacitkit.__name__)"
    )
    run = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": SRC},
    )
    assert run.stdout.split()[0] == "True" and "DeprecationWarning" in run.stderr
