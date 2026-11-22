"""One word store for every app: never-send words, always-OK words, always-hide words, the owner's
own patterns and name sources (ADR 0001, ADR 0007).

The store is one JSON file in the user's config folder. Every change goes through change():
lock, re-read, edit, then write a temp file that os.replace swaps in. A missing store is an
explicit empty; a damaged one raises Unreadable and is never overwritten. Nothing here logs,
and no error or output carries a word.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import warnings
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

from . import custom
from .custom import Pattern

SCHEMA = 1  # what a store without the newer lists writes
SCHEMA_WITH_HIDE = 2  # written once the store holds always-hide words or custom patterns
READABLE = (SCHEMA, SCHEMA_WITH_HIDE)
LISTS = ("never_send", "always_ok", "always_hide")
MAX_PATTERNS = 50
GENERAL = "general"
MAX_CHARS = 200
LOCK_SECONDS = 10.0
_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,63}")


class Unreadable(Exception):
    """The store, a source or an import file exists but can't be trusted. Callers hold
    private content. `what` is "store", "import" or "source:<id>", never a value."""

    def __init__(self, what: str) -> None:
        super().__init__(f"{what} unreadable")
        self.what = what


class Refused(ValueError):
    """A change the store won't make. The message names the rule, never the word."""


class Word(NamedTuple):
    text: str
    scope: str = GENERAL


class Source(NamedTuple):
    """A read-only name source: a JSON list in another app's file. With `fields`, each item
    is a mapping and those fields are names; without, each item is a name."""

    id: str
    path: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class Terms:
    never_send: tuple[Word, ...] = ()
    always_ok: tuple[Word, ...] = ()
    always_hide: tuple[Word, ...] = ()
    custom_patterns: tuple[Pattern, ...] = ()
    sources: tuple[Source, ...] = ()
    imports: tuple[str, ...] = ()

    def words(self, name: str, scope: str = GENERAL) -> tuple[str, ...]:
        return tuple(word.text for word in getattr(self, _list(name)) if word.scope == scope)

    def patterns(self, scope: str = GENERAL) -> tuple[Pattern, ...]:
        return tuple(item for item in self.custom_patterns if item.scope == scope)


class NotProduction(RuntimeError):
    """The real profile store was asked for by a process that has not declared production, or
    by a test run. Nothing is read or written. Set SCRUBLET_HOME to a scratch folder instead."""


_production = False
_warned = False
LEGACY_NAME = "tacitkit"  # the store's folder before the rename to scrublet (v0.7.0)


def production() -> None:
    """The app's real start-up declares itself: only now can the REAL profile store resolve
    (ADR 0006). One rule, one home: every app calls this once at its real start-up and nothing
    else resolves the real store. It has no effect in a test run, whatever else is set."""
    global _production  # noqa: PLW0603 -- one declaration per process
    _production = True


def under_test() -> bool:
    """A test run, found without leaning on environment variables a test can remove: pytest is
    loaded (sys.modules) or sets PYTEST_CURRENT_TEST (which child processes inherit)."""
    return "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ


def default_home(name: str = "scrublet") -> Path:
    """Where the real profile store lives. Pure: it resolves nothing and checks nothing."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / name


def _resolve() -> tuple[Path, bool]:
    """(the store's folder, whether it is the real profile store). SCRUBLET_HOME is an explicit
    scratch or custom folder and works anywhere; the old TACITKIT_HOME still works for one
    version with a deprecation warning. The real profile store resolves only for a process that
    declared production and is not a test run; anything else raises NotProduction."""
    explicit = os.environ.get("SCRUBLET_HOME")
    if explicit:
        return Path(explicit), False
    old = os.environ.get("TACITKIT_HOME")
    if old:
        global _warned  # noqa: PLW0603
        if not _warned:
            _warned = True
            warnings.warn(
                "TACITKIT_HOME is deprecated; set SCRUBLET_HOME (read for one more version)",
                DeprecationWarning,
                stacklevel=3,
            )
        return Path(old), False
    if under_test():
        raise NotProduction(
            "a test run can never reach the real store: set SCRUBLET_HOME to a temp folder"
        )
    if not (_production or os.environ.get("SCRUBLET_PRODUCTION") == "1"):
        raise NotProduction(
            "the real store resolves only after the app declares production "
            "(scrublet_pii.terms.production()); set SCRUBLET_HOME for a scratch store"
        )
    return default_home(), True


def home() -> Path:
    """The store's folder (see _resolve)."""
    return _resolve()[0]


def _file(path: Path | str | None) -> Path:
    return _target(path)[0]


def _target(path: Path | str | None) -> tuple[Path, Path | None]:
    """(the store file, the pre-rename store file to migrate from or None). An explicit path
    is used as given; only the real profile store has a legacy one."""
    if path:
        return Path(path), None
    folder, real = _resolve()
    return folder / "terms.json", (default_home(LEGACY_NAME) / "terms.json" if real else None)


def _migrate(path: Path, legacy: Path) -> None:
    """Move the real profile store from %APPDATA%/tacitkit to %APPDATA%/scrublet, once. The
    caller holds the new store's lock, so two apps starting together migrate once. Lossless
    (the bytes are copied as they are, damaged or not), atomic (a temp file swapped in) and
    idempotent (nothing happens when the new store exists or there is no old one). The old
    file is left in place; an app still on the old library keeps using it, which is why
    problems() reports a change to it after the move."""
    if path.exists() or not legacy.is_file():
        return
    data = legacy.read_bytes()
    stamp = legacy.stat()
    descriptor, temp = tempfile.mkstemp(dir=path.parent, prefix=".migrate-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    note = {"at": time.time(), "legacy_mtime_ns": stamp.st_mtime_ns, "legacy_size": stamp.st_size}
    (path.parent / "migrated-from-tacitkit.json").write_text(json.dumps(note), encoding="utf-8")
    with contextlib.suppress(OSError):  # a note for a person; never required
        (legacy.parent / "MOVED-TO-SCRUBLET.txt").write_text(
            "This store moved to the scrublet folder next to this one.\n"
            "Apps on scrublet use that one.\n",
            encoding="utf-8",
        )


def _list(name: str) -> str:
    if name not in LISTS:
        raise Refused("unknown list")
    return name


def _clean(text: str) -> str:
    cleaned = " ".join(text.split()) if type(text) is str else ""
    if not cleaned or len(cleaned) > MAX_CHARS or not any(ch.isalnum() for ch in cleaned):
        raise Refused(f"each word needs a letter or digit and at most {MAX_CHARS} characters")
    return cleaned


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


# --- reading ---------------------------------------------------------------------------

_cache: dict[str, tuple[tuple[int, int], object]] = {}


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _json(path: Path, what: str):
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError):
        raise Unreadable(what) from None  # never the parser's text: it can quote the file


def _strings(value, what: str) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise Unreadable(what)
    return tuple(value)


def _parse(raw) -> Terms:
    what = "store"
    if type(raw) is not dict or raw.get("schema") not in READABLE:
        raise Unreadable(what)
    lists = {}
    for name in LISTS:
        entries = raw.get(name, [])
        if type(entries) is not list:
            raise Unreadable(what)
        words = []
        for entry in entries:
            if (
                type(entry) is not dict
                or type(entry.get("text")) is not str
                or type(entry.get("scope", GENERAL)) is not str
            ):
                raise Unreadable(what)
            words.append(Word(entry["text"], entry.get("scope", GENERAL)))
        lists[name] = tuple(words)
    sources, entries = [], raw.get("sources", [])
    if type(entries) is not list:
        raise Unreadable(what)
    for entry in entries:
        if (
            type(entry) is not dict
            or type(entry.get("id")) is not str
            or type(entry.get("path")) is not str
        ):
            raise Unreadable(what)
        sources.append(Source(entry["id"], entry["path"], _strings(entry.get("fields", []), what)))
    return Terms(
        **lists,
        custom_patterns=_parse_patterns(raw.get("custom_patterns", []), what),
        sources=tuple(sources),
        imports=_strings(raw.get("imports", []), what),
    )


def _parse_patterns(entries, what: str) -> tuple[Pattern, ...]:
    """Stored patterns are checked again on every read: a damaged or hand-edited entry makes the
    store unreadable (private content is held), never a pattern that was not vetted."""
    if type(entries) is not list or len(entries) > MAX_PATTERNS:
        raise Unreadable(what)
    found = []
    for entry in entries:
        if (
            type(entry) is not dict
            or any(type(entry.get(key)) is not str for key in ("id", "kind", "text"))
            or type(entry.get("scope", GENERAL)) is not str
            or type(entry.get("at", "")) is not str
        ):
            raise Unreadable(what)
        item = Pattern(
            entry["id"],
            entry["kind"],
            entry["text"],
            entry.get("scope", GENERAL),
            entry.get("at", ""),
        )
        try:
            custom.compile_pattern(item.kind, item.text)
        except custom.Invalid:
            raise Unreadable(what) from None
        found.append(item)
    return tuple(found)


def _dump(terms: Terms) -> dict:
    # An older library refuses schema 2 (it would drop the newer lists on its next write), so the
    # newer schema is written only once the owner has actually used the newer lists.
    newer = bool(terms.always_hide or terms.custom_patterns)
    return {
        "schema": SCHEMA_WITH_HIDE if newer else SCHEMA,
        **{
            name: [{"text": w.text, "scope": w.scope} for w in getattr(terms, name)]
            for name in LISTS
            if name != "always_hide" or newer
        },
        **(
            {
                "custom_patterns": [
                    {"id": i.id, "kind": i.kind, "text": i.text, "scope": i.scope, "at": i.at}
                    for i in terms.custom_patterns
                ]
            }
            if newer
            else {}
        ),
        "sources": [{"id": s.id, "path": s.path, "fields": list(s.fields)} for s in terms.sources],
        "imports": list(terms.imports),
    }


def _load(path: Path) -> Terms:
    try:
        return _parse(_json(path, "store"))
    except FileNotFoundError:
        return Terms()


def read(path: Path | str | None = None) -> Terms:
    """The store. A missing store is Terms() (no words yet); a damaged one raises Unreadable."""
    path, legacy = _target(path)
    try:
        stamp = _stamp(path)
        if stamp is None and legacy is not None and (stamp := _stamp(legacy)) is not None:
            path = legacy  # not moved yet: the old store is still the store
    except OSError:
        raise Unreadable("store") from None
    if stamp is None:
        return Terms()
    cached = _cache.get(str(path))
    if cached and cached[0] == stamp:
        return cached[1]
    terms = _load(path)
    _cache[str(path)] = (stamp, terms)
    return terms


# --- writing ---------------------------------------------------------------------------


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a+b") as handle:
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415

            deadline = time.monotonic() + LOCK_SECONDS
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError("store busy") from None
                    time.sleep(0.02)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl  # noqa: PLC0415

            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _write(path: Path, terms: Terms) -> None:
    descriptor, temp = tempfile.mkstemp(dir=path.parent, prefix=".terms-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(_dump(terms), handle, ensure_ascii=False, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        for _attempt in range(100):  # Windows refuses the swap while a reader has it open
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                time.sleep(0.02)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def change(edit: Callable[[Terms], Terms], path: Path | str | None = None) -> Terms:
    """The one writer: lock, re-read, edit, swap in atomically. A damaged store raises
    Unreadable and is left as it is for the owner to repair."""
    path, legacy = _target(path)
    with _locked(path):
        if legacy is not None:
            _migrate(path, legacy)
        current = _load(path)
        updated = edit(current)
        if updated != current:
            _write(path, updated)
        _cache.pop(str(path), None)
        return updated


def _with_words(
    terms: Terms, name: str, scope: str, add: Iterable[str] = (), remove: Iterable[str] = ()
) -> tuple[Terms, int]:
    gone = {_key(text) for text in remove}
    kept = [w for w in getattr(terms, name) if not (w.scope == scope and _key(w.text) in gone)]
    have = {_key(w.text) for w in kept if w.scope == scope}
    never = {_key(w.text) for w in terms.never_send if w.scope == scope}
    hidden = {_key(w.text) for w in terms.always_hide if w.scope == scope}
    added = 0
    for text in add:
        if name == "always_ok" and _key(text) in never:
            raise Refused("that word is on the never-send list, which always wins")
        if name == "always_ok" and _key(text) in hidden:
            raise Refused("that word is on the always-hide list, which wins over always-OK")
        if _key(text) not in have:
            kept.append(Word(text, scope))
            have.add(_key(text))
            added += 1
    terms = replace(terms, **{name: tuple(kept)})
    if name in {"never_send", "always_hide"}:  # hiding wins: the same word leaves always-OK
        terms = replace(
            terms,
            always_ok=tuple(
                w for w in terms.always_ok if not (w.scope == scope and _key(w.text) in have)
            ),
        )
    return terms, added


def update(
    name: str,
    add: Iterable[str] = (),
    remove: Iterable[str] = (),
    scope: str = GENERAL,
    path: Path | str | None = None,
) -> Terms:
    """Add and remove words on one list. Send the owner's edits, not the whole list, so a word
    another writer added meanwhile is kept."""
    name = _list(name)
    adding = [_clean(text) for text in add]
    removing = [text for text in remove if type(text) is str]
    return change(lambda terms: _with_words(terms, name, scope, adding, removing)[0], path)


def add_pattern(
    text: str,
    kind: str = "shape",
    scope: str = GENERAL,
    path: Path | str | None = None,
) -> Pattern:
    """Store one of the owner's own patterns (ADR 0007): a shape such as "AA-999999" (see
    `custom.shape_of`) or a bounded regex. Checked before anything is written; the same
    pattern added twice is one pattern. Raises `custom.Invalid` or `Refused`, never the text."""
    text = text.strip() if type(text) is str else text
    custom.compile_pattern(kind, text)  # raises Invalid
    if type(scope) is not str or not scope or len(scope) > 40:
        raise Refused("a scope is 1 to 40 characters")
    identity = "p-" + hashlib.sha256(f"{kind}\0{scope}\0{text}".encode()).hexdigest()[:12]
    item = Pattern(identity, kind, text, scope, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    stored: list[Pattern] = []

    def edit(terms: Terms) -> Terms:
        known = next((i for i in terms.custom_patterns if i.id == identity), None)
        if known is not None:
            stored.append(known)
            return terms
        if len(terms.custom_patterns) >= MAX_PATTERNS:
            raise Refused(f"at most {MAX_PATTERNS} patterns")
        stored.append(item)
        return replace(terms, custom_patterns=(*terms.custom_patterns, item))

    change(edit, path)
    return stored[0]


def remove_pattern(pattern_id: str, path: Path | str | None = None) -> Terms:
    """Remove one pattern by its id. An unknown id changes nothing."""
    return change(
        lambda terms: replace(
            terms, custom_patterns=tuple(i for i in terms.custom_patterns if i.id != pattern_id)
        ),
        path,
    )


def register_source(
    source_id: str, file: Path | str, fields: Iterable[str] = (), path: Path | str | None = None
) -> Terms:
    """Register (or re-point) a read-only name source. The file is read live, never copied."""
    if type(source_id) is not str or not _ID.fullmatch(source_id):
        raise Refused("a source id is lower-case letters, digits and . _ : -")
    if not Path(file).is_absolute():
        raise Refused("a source path must be absolute")
    source = Source(source_id, str(file), tuple(str(field) for field in fields))
    return change(
        lambda terms: replace(
            terms, sources=(*(s for s in terms.sources if s.id != source_id), source)
        ),
        path,
    )


def unregister_source(source_id: str, path: Path | str | None = None) -> Terms:
    return change(
        lambda terms: replace(terms, sources=tuple(s for s in terms.sources if s.id != source_id)),
        path,
    )


def import_words(
    file: Path | str,
    import_id: str,
    name: str = "never_send",
    scope: str = GENERAL,
    path: Path | str | None = None,
) -> int:
    """A one-time import of a JSON list of words from an app's old file (read only). Returns
    how many were new. Running it again with the same id adds nothing, even after the owner
    removes an imported word. Everything is checked before the one write, so a failure leaves
    the store as it was."""
    name = _list(name)
    if type(import_id) is not str or not _ID.fullmatch(import_id):
        raise Refused("an import id is lower-case letters, digits and . _ : -")
    try:
        raw = _json(Path(file), "import")
    except FileNotFoundError:
        raise Unreadable("import") from None
    words = [_clean(text) for text in _strings(raw, "import") if text.strip()]
    added = 0

    def edit(terms: Terms) -> Terms:
        nonlocal added
        if import_id in terms.imports:
            return terms
        terms, added = _with_words(terms, name, scope, words)
        return replace(terms, imports=(*terms.imports, import_id))

    change(edit, path)
    return added


# --- name sources ----------------------------------------------------------------------


def _fullest_first(name: str) -> tuple[int, int, str]:
    return (-len(name.split()), -len(name), name)


def _source_names(source: Source) -> tuple[str, ...]:
    what, file = f"source:{source.id}", Path(source.path)
    try:
        stamp = _stamp(file)
    except OSError:
        raise Unreadable(what) from None
    if stamp is None:
        return ()  # a fresh app may not have this file yet; problems() reports a lost folder
    key = f"{source.path}|{','.join(source.fields)}"
    cached = _cache.get(key)
    if cached and cached[0] == stamp:
        return cached[1]
    try:
        items = _json(file, what)
    except FileNotFoundError:
        return ()
    if type(items) is not list:
        raise Unreadable(what)
    if source.fields:
        found = [
            str(item.get(field) or "")
            for item in items
            if isinstance(item, Mapping)
            for field in source.fields
        ]
    else:
        found = list(_strings(items, what))
    names = tuple(" ".join(name.split()) for name in found if name.strip())
    _cache[key] = (stamp, names)
    return names


def names(terms: Terms | None = None) -> tuple[str, ...]:
    """Every name from the registered sources, de-duplicated, fullest first, so a matcher
    takes "Alex Example" whole before a source holding just "Alex". Raises Unreadable."""
    terms = read() if terms is None else terms
    found: dict[str, str] = {}
    for source in terms.sources:
        for name in _source_names(source):
            found.setdefault(name.casefold(), name)
    return tuple(sorted(found.values(), key=_fullest_first))


def problems(path: Path | str | None = None) -> dict[str, str]:
    """What's wrong, for an app's privacy status: {"store" or source id: "unreadable" or
    "missing"}. Empty when all is well. A source whose folder has gone is "missing"."""
    try:
        terms = read(path)
    except Unreadable:
        return {"store": "unreadable"}
    found = {}
    for source in terms.sources:
        if not Path(source.path).parent.is_dir():
            found[source.id] = "missing"
            continue
        try:
            _source_names(source)
        except Unreadable:
            found[source.id] = "unreadable"
    if not path and _legacy_changed():
        found["legacy"] = "changed"  # an app still on the old library wrote to the old store
    return found


def _legacy_changed() -> bool:
    """True when the pre-rename store changed after it was moved: words added there by an app
    that has not moved yet are not in the store this library reads."""
    try:
        folder, real = _resolve()
        if not real:
            return False
        note = json.loads((folder / "migrated-from-tacitkit.json").read_text(encoding="utf-8"))
        stamp = (default_home(LEGACY_NAME) / "terms.json").stat()
    except (OSError, ValueError, NotProduction):
        return False
    return (stamp.st_mtime_ns, stamp.st_size) != (note["legacy_mtime_ns"], note["legacy_size"])


# --- command line ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """scrublet status | import-words <file> --id <id> [--list always_ok|always_hide]. Counts only.
    Running it is an operator action on the real store, so it declares production (a test run
    still can't)."""
    production()
    arguments = list(sys.argv[1:] if argv is None else argv)
    out = sys.stdout.write
    if arguments[:1] == ["status"]:
        try:
            issues = problems()
        except NotProduction as error:
            out(f"{error}\n")
            return 2
        if "store" in issues:
            out("Word store: unreadable. Private content is held until it's repaired.\n")
            return 1
        terms = read()
        known = 0 if "unreadable" in issues.values() else len(names(terms))
        out(
            f"Word store: {len(terms.never_send)} never-send, {len(terms.always_ok)} always-OK, "
            f"{len(terms.always_hide)} always-hide, {len(terms.custom_patterns)} patterns, "
            f"{len(terms.sources)} name sources ({known} names).\n"
        )
        for source_id, issue in sorted(issues.items()):
            out(f"Source {source_id}: {issue}.\n")
        return 1 if issues else 0
    if arguments[:1] == ["import-words"] and len(arguments) >= 4 and "--id" in arguments:
        name = arguments[arguments.index("--list") + 1] if "--list" in arguments else "never_send"
        try:
            added = import_words(arguments[1], arguments[arguments.index("--id") + 1], name)
        except (Unreadable, Refused) as error:
            out(f"Nothing imported: {error}.\n")
            return 1
        out(f"Imported {added} new words.\n")
        return 0
    out(
        "Use: scrublet_pii status | scrublet_pii import-words <file> --id <id> "
        "[--list always_ok|always_hide]\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
