"""The global word store (ADR 0001). Synthetic words only."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from scrublet_pii import terms

SECRET = "Alex Example"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRUBLET_HOME", str(tmp_path / "home"))
    terms._cache.clear()
    return tmp_path / "home" / "terms.json"


def test_a_missing_store_is_an_explicit_empty(store):
    found = terms.read()
    assert found == terms.Terms() and found.words("never_send") == ()
    assert not store.exists() and terms.problems() == {}


def test_home_uses_the_override_and_the_real_default_is_the_users_config_folder(
    monkeypatch, tmp_path
):
    assert terms.home() == tmp_path / "home"
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    expected = {"nt": tmp_path / "roaming"}.get(os.name, tmp_path / "xdg")
    if sys.platform == "darwin":
        expected = Path.home() / "Library" / "Application Support"
    assert terms.default_home() == expected / "scrublet"
    assert terms.default_home("tacitkit") == expected / "tacitkit"


def test_add_and_remove_ignore_case_and_spacing_and_keep_the_first_spelling(store):
    terms.update("never_send", add=[" Alex   Example ", "alex example", "S1234567A"])
    assert terms.read().words("never_send") == (SECRET, "S1234567A")
    terms.update("never_send", remove=["ALEX EXAMPLE"])
    assert terms.read().words("never_send") == ("S1234567A",)
    saved = json.loads(store.read_text(encoding="utf-8"))
    assert saved["schema"] == 1 and saved["never_send"] == [
        {"text": "S1234567A", "scope": "general"}
    ]


def test_scope_keeps_lists_apart():
    terms.update("never_send", add=[SECRET], scope="work")
    assert terms.read().words("never_send") == ()
    assert terms.read().words("never_send", scope="work") == (SECRET,)


def test_never_send_wins_over_always_ok():
    terms.update("always_ok", add=["Example Holdings"])
    terms.update("never_send", add=["example holdings"])
    assert terms.read().words("always_ok") == ()
    with pytest.raises(terms.Refused) as refused:
        terms.update("always_ok", add=["EXAMPLE HOLDINGS"])
    assert "xample" not in str(refused.value)


@pytest.mark.parametrize("word", ["", "   ", "***", "x" * 201, 5])
def test_a_word_needs_a_letter_or_digit_and_a_sane_length(word):
    with pytest.raises(terms.Refused):
        terms.update("never_send", add=[word])


@pytest.mark.parametrize(
    "content",
    [
        b"{not json",
        b"\xff\xfe",
        b"[]",
        b'{"schema": 2}',
        b'{"schema": 1, "never_send": "x"}',
        b'{"schema": 1, "never_send": [{"text": 5}]}',
        b'{"schema": 1, "sources": [{"id": "a"}]}',
        b'{"schema": 1, "sources": "a"}',
        b'{"schema": 1, "imports": [1]}',
    ],
)
def test_a_damaged_store_is_unreadable_and_never_overwritten(store, content):
    store.parent.mkdir(parents=True)
    store.write_bytes(content)
    with pytest.raises(terms.Unreadable) as error:
        terms.read()
    assert error.value.what == "store" and terms.problems() == {"store": "unreadable"}
    with pytest.raises(terms.Unreadable):
        terms.update("never_send", add=[SECRET])
    assert store.read_bytes() == content


def test_the_error_never_quotes_the_file(store):
    store.parent.mkdir(parents=True)
    store.write_text('{"schema": 1, "never_send": [' + SECRET, encoding="utf-8")
    with pytest.raises(terms.Unreadable) as error:
        terms.read()
    assert SECRET not in str(error.value) and error.value.__cause__ is None


def test_reads_are_cached_until_the_file_changes(store, monkeypatch):
    terms.update("never_send", add=[SECRET])
    first = terms.read()
    with monkeypatch.context() as patch:
        patch.setattr(terms, "_load", lambda _p: pytest.fail("re-read an unchanged file"))
        assert terms.read() is first
    terms.update("never_send", add=["Sam Recipient"])
    assert terms.read().words("never_send") == (SECRET, "Sam Recipient")


def test_two_writers_in_one_app_lose_nothing_and_readers_never_see_half_a_file(store):
    errors = []

    def writer(prefix):
        for n in range(25):
            terms.update("never_send", add=[f"{prefix} {n}"])

    def reader():
        for _ in range(200):
            try:
                terms.read()
            except Exception as error:
                errors.append(type(error).__name__)

    threads = [threading.Thread(target=writer, args=(p,)) for p in ("Settings", "Upload")]
    threads.append(threading.Thread(target=reader))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [] and len(terms.read().never_send) == 50
    assert sorted(p.name for p in store.parent.iterdir()) == ["terms.json", "terms.json.lock"]


def test_two_apps_writing_at_once_lose_nothing(store):
    code = (
        "import sys; from scrublet_pii import terms\n"
        "for n in range(15): terms.update('never_send', add=[f'{sys.argv[1]} {n}'])\n"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(terms.__file__).parents[1])}
    apps = [
        subprocess.Popen([sys.executable, "-c", code, name], env=env)
        for name in ("First app", "Second app")
    ]
    assert [app.wait(60) for app in apps] == [0, 0]
    assert len(terms.read().never_send) == 30


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_import_is_idempotent_skips_duplicates_and_never_writes_the_old_file(tmp_path):
    old = write_json(tmp_path / "app" / "words.json", [SECRET, "alex  example", "", "Acme Pte"])
    before = (old.read_bytes(), old.stat().st_mtime_ns)
    terms.update("never_send", add=["ACME PTE"])
    assert terms.import_words(old, "app:words") == 1
    assert terms.read().words("never_send") == ("ACME PTE", SECRET)
    terms.update("never_send", remove=[SECRET])
    assert terms.import_words(old, "app:words") == 0
    assert terms.read().words("never_send") == ("ACME PTE",)
    assert terms.read().imports == ("app:words",)
    assert (old.read_bytes(), old.stat().st_mtime_ns) == before


@pytest.mark.parametrize("value", [[SECRET, 7], {"words": [SECRET]}, [SECRET, "***"]])
def test_a_failed_import_leaves_the_store_as_it_was(tmp_path, store, value):
    terms.update("never_send", add=["Sam Recipient"])
    before = store.read_bytes()
    old = write_json(tmp_path / "app" / "words.json", value)
    with pytest.raises((terms.Unreadable, terms.Refused)):
        terms.import_words(old, "app:words")
    assert store.read_bytes() == before and terms.read().imports == ()
    with pytest.raises(terms.Unreadable):
        terms.import_words(tmp_path / "absent.json", "app:words")


def test_sources_are_read_live_fullest_name_first(tmp_path):
    cards = write_json(
        tmp_path / "app" / "cards.json",
        [{"cardholder": "ALEX EXAMPLE", "holder": "Alex"}, {"holder": "Sam  Q Recipient"}, "x"],
    )
    plain = write_json(tmp_path / "app" / "people.json", ["alex example", "Jo"])
    terms.register_source("app:cards", cards, ["cardholder", "holder"])
    terms.register_source("app:people", plain)
    assert terms.names() == ("Sam Q Recipient", "ALEX EXAMPLE", "Alex", "Jo")
    write_json(cards, [{"cardholder": "Pat Sample"}])
    os.utime(cards, ns=(1, 1))
    assert "Pat Sample" in terms.names() and "Sam Q Recipient" not in terms.names()
    assert terms.read().sources[0] == terms.Source(
        "app:cards", str(cards), ("cardholder", "holder")
    )


def test_a_source_missing_its_file_is_empty_but_a_lost_folder_or_bad_file_is_a_problem(tmp_path):
    folder = tmp_path / "app"
    folder.mkdir()
    terms.register_source("app:accounts", folder / "accounts.json", ["holder"])
    assert terms.names() == () and terms.problems() == {}
    write_json(folder / "accounts.json", {"holder": SECRET})
    with pytest.raises(terms.Unreadable) as error:
        terms.names()
    assert error.value.what == "source:app:accounts"
    assert terms.problems() == {"app:accounts": "unreadable"}
    terms.register_source("app:accounts", tmp_path / "gone" / "accounts.json", ["holder"])
    assert terms.problems() == {"app:accounts": "missing"}
    terms.unregister_source("app:accounts")
    assert terms.read().sources == ()


@pytest.mark.parametrize(
    ("source_id", "file"), [("App", "/x.json"), ("a b", "/x.json"), ("app", "relative.json")]
)
def test_a_source_needs_a_plain_id_and_an_absolute_path(source_id, file):
    with pytest.raises(terms.Refused):
        terms.register_source(source_id, file if file != "/x.json" else Path.cwd() / "x.json")


def test_the_command_line_prints_counts_never_words(tmp_path, capsys, store):
    old = write_json(tmp_path / "app" / "words.json", [SECRET])
    assert terms.main(["import-words", str(old), "--id", "app:words"]) == 0
    assert terms.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Imported 1 new words." in out and "1 never-send" in out and SECRET not in out
    store.write_text("{", encoding="utf-8")
    assert terms.main(["status"]) == 1 and "unreadable" in capsys.readouterr().out
    assert terms.main([]) == 2
