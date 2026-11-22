# ADR 0006: The name scrublet, the production guard, and the move of the store

Status: accepted (22 Nov 2026)

## Context

The library was called tacitkit. It becomes **scrublet**: the project and repository are
`scrublet`, the PyPI distribution is `scrublet-pii` (the name `scrublet` on PyPI is an unrelated
science package), and the import name is `scrublet_pii` (so it never clashes with that package).

Separately, a test run once reached the real profile store. A test removed the setting that
pointed it at a scratch store (`monkeypatch.undo()`), then booted an app, whose start-up
registered name sources in the real store. Per-app test fixtures are not enough: any one of them
can be undone or forgotten. The rule belongs in the library, once.

## Decision

### The rename

- Package `scrublet_pii`; distribution `scrublet-pii`; commands `scrublet` and
  `python -m scrublet_pii.bench` / `python -m scrublet_pii.terms`.
- `SCRUBLET_HOME` replaces `TACITKIT_HOME`. The old name is still read for one version with a
  `DeprecationWarning`; if both are set, `SCRUBLET_HOME` wins silently.
- For one version, `import tacitkit` and `from tacitkit import terms` work and give the **same
  module objects** (an alias in `sys.modules`), with a deprecation warning, so an app can bump
  its pin first and rename its imports after. The alias, the `tacitkit` command and
  `TACITKIT_HOME` are removed in v0.8.0.

### The production guard

- The **real profile store resolves only when the caller declares production**:
  `scrublet_pii.terms.production()` at the app's real start-up, or `SCRUBLET_PRODUCTION=1` for a
  service that starts without code.
- **A test run can never resolve it.** A test run is detected without depending on anything a test
  can remove: pytest in `sys.modules`, or `PYTEST_CURRENT_TEST` (inherited by child processes). In a
  test run a production declaration has no effect.
- Anything that has not declared production, and is not given a store, **raises
  `NotProduction`**. It does not fall back to a scratch store: guessing a store is how data
  lands in the wrong one. Nothing is read, written or created.
- `SCRUBLET_HOME` (an explicit scratch or custom folder) and an explicit `path=` argument work
  anywhere, including tests. The CLI declares production itself (it is an operator action), and
  is still refused under a test run.
- `tests/test_guard.py` proves it, including the exact leak: the scratch setting undone, then the
  app boots and declares production; and again with the pytest variable removed too.

### Moving the store

The default folder changes from `tacitkit` to `scrublet` in the user's config folder. The move is
**one-time, atomic, idempotent and lossless**, and only for the real profile store (never for an
explicit `SCRUBLET_HOME`):

- It happens inside the first write by a production app, under the new store's lock, so two apps
  starting together move it once.
- The old file's bytes are copied as they are (damaged or not) to a temp file that `os.replace`
  swaps in. If the new store exists, or there is no old one, nothing happens.
- Until it moves, reads fall back to the old store, so nothing is lost in between.
- The old file is **left in place**, with a note beside it (`MOVED-TO-SCRUBLET.txt`).

## Consequences

- **Apps must move together.** An app still on the old library keeps using the old store, which
  stops receiving the new library's changes. `terms.problems()` reports `legacy: changed` when the
  old store changes after the move, so the divergence is visible (counts and ids only).
- An app that upgrades without declaring production is refused, not guessed for. That is a held
  send for apps that fail closed, by design: the fix is one line at start-up.
- A production process that happens to import pytest is treated as a test run. That is the
  conservative failure.
