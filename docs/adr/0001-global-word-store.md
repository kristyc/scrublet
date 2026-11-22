# ADR 0001: One global word store, shared by every app

Status: accepted (22 Nov 2026)

## Context

The owner has built redaction three times, in three apps. Each app keeps its own list of
words that must never reach an AI. Adding a word in one app's Settings left the others unaware,
and a miss can't be undone once text has been sent. scrublet's first job is one list that every
app reads and writes.

## Decision

`scrublet_pii.terms` owns one JSON file in the user's config folder:

- Windows: `%APPDATA%\scrublet\terms.json`
- macOS: `~/Library/Application Support/scrublet/terms.json`
- other systems: `$XDG_CONFIG_HOME/scrublet/terms.json`, falling back to `~/.config`

`SCRUBLET_HOME` (`TACITKIT_HOME` before v0.7.0) overrides the folder, for tests and for an app that runs as another account.
The path rule is a few lines of standard library code, so scrublet has no runtime dependencies.

The store holds:

- `never_send`: words and phrases that must never be sent;
- `always_ok`: words a name finder must not hide, such as a company name it over-redacts;
- `sources`: registered read-only name sources. Each one is a JSON file holding a list, plus
  the fields to take from each item, or the items themselves when no field is named. Each
  source's file stays the one home of its facts: scrublet reads it live and never copies it;
- `imports`: the ids of one-time imports already done.

Each word carries a `scope`, `"general"` today, so that per-area lists can be added later
without changing the file's shape.

### Rules

1. **One writer path.** Every change goes through `terms.change()`: it takes a lock file,
   re-reads the store, applies the change, and writes a temp file that `os.replace` swaps in.
   Two writers in one app (a Settings editor and a "Redact it, always" answer on an upload) or
   in two apps can't lose each other's words. A reader never sees half a file.
2. **Empty is not unreadable.** `read()` returns a `Terms` value. A missing store is an
   explicit empty, because a fresh install has no words. A store that exists but won't parse,
   has the wrong shape, or has a newer schema raises `Unreadable`, and callers hold private
   content (fail closed). A source file that won't parse raises too. A source whose folder has
   gone is reported by `problems()` as `missing`, never silently treated as complete.
3. **Never-send wins.** A word can't be added to `always_ok` while the same word is on
   `never_send`. Words are compared ignoring case and spacing. A broader match check, such as
   a word inside a phrase, stays with each app's matcher until `printed` lands.
4. **Values are never logged.** scrublet doesn't log. Errors and command-line output carry
   counts and kinds only, never a word, a name or the error text of a parser that could quote
   the file.
5. **Schema-versioned.** The file carries `"schema": 1`. A reader refuses a schema it doesn't
   know, instead of guessing.
6. **Cached on mtime.** Reads cache on each file's (mtime_ns, size), so an app can ask on
   every send.
7. **One-time import.** `import_words(path, import_id)` adds a list of words from an app's old
   file, such as a `redaction_words.json` list. It reads that file and never
   writes it. It skips duplicates and records `import_id`, so running it again is a no-op even
   after the owner removes an imported word. Everything is checked before the one atomic
   write, so a failure leaves the store as it was. Each app retires its old file in its own
   change.

## Consequences

- Any process running as the user can read the store, as it can each app's own config today.
  The store holds the same words those apps held, in one place instead of three.
- An app running under another account (a service) must set `SCRUBLET_HOME`, or it reads a
  different, empty store. Each app should show where its store is in its privacy status.
- Matching (how a word is found in messy text) is not part of this step. It moves to
  `scrublet_pii.printed` later, once both apps' test corpora pass on it.
