# ADR 0007: An always-hide list and the owner's own patterns

Status: accepted (23 Nov 2026)

## Context

An app that shows the owner exactly what an AI will read lets them hide something the detectors
missed: a name in an unusual script, a policy or member number in a format no pack knows. That
is the strongest signal the library has that a word or a shape should be hidden next time. The
store had two lists, and neither fits:

- `never_send` means the word must not leave at all. A final check refuses a send that still
  holds it, and a web search containing it is blocked. That is too strong for "hide this in
  what you send, but don't stop the task".
- `always_ok` is the opposite: words that are fine to send.

## Decision

### A third list: `always_hide`

- `always_hide` holds words that are **hidden** (replaced by a stand-in) on private paths. It
  never blocks a send and is not a reason to refuse a search. `never_send` keeps its meaning,
  "block in searches too".
- It has the same shape as the other lists: words with a scope, edited with
  `terms.update("always_hide", add=..., remove=...)`, imported with
  `import-words --list always_hide`, under the same lock, atomic write and production guard.
- **Hiding wins over OK.** Adding a word to `always_hide` removes it from `always_ok`, and adding
  a word that is on `always_hide` to `always_ok` is refused, as for `never_send`. A word may be
  on both `never_send` and `always_hide`; they answer different questions.

### Custom patterns: `Terms.custom_patterns`

- A pattern is `Pattern(id, kind, text, scope, at)`. `kind` is `"shape"` or `"regex"`. The id is
  derived from kind, scope and text, so adding the same pattern twice is one pattern and removal
  is by a stable id. `add_pattern`, `remove_pattern` and `Terms.patterns(scope)` are the API.
- A **shape** is made from one example (`custom.shape_of("ab-123456")` is `"AA-999999"`): letters
  become `A`, digits `9`, other characters stay. It matches that format as a whole, not inside
  longer runs of letters or digits. A shape needs at least six letters or digits, so it can't
  match every pair of digits.
- A **regex** is accepted only in a small grammar. Quantifiers apply to one character or class,
  never a group, so nested quantifiers cannot exist. Backreferences, lookaround, flags and
  conditionals are refused. At most four quantifiers, at most ONE unbounded (two can overlap and
  make matching quadratic; v0.8.0 allowed two), repeat counts up to 64, at most 200 characters, and a pattern that can match nothing is refused. Matching is
  therefore polynomial of small degree, not exponential; a test pins a long hostile input.
- Patterns are checked when added **and again on every read**. A hand-edited or damaged entry
  makes the store unreadable (private content is held), never an unvetted pattern.
- At most 50 patterns. Errors name the rule, never the pattern or a sample.
- Patterns live only in the local store. Nothing here sends or logs them.

### Schema and older libraries

- The store's schema is **1** until it holds an always-hide word or a pattern, then **2**; it
  goes back to 1 when those are removed. An older library refuses schema 2 as unreadable, which
  holds private content, instead of silently dropping the newer lists on its next write. This
  library reads both.
- The CLI `status` counts the new lists; it never prints a word or a pattern.

### What does not change

- The production guard (ADR 0006) covers the new writers, because they go through `change`.
- The `tacitkit` alias, command and `TACITKIT_HOME`, announced for removal in v0.8.0 by
  ADR 0006, stay for one more version. Other apps may still import the alias, and removing
  it in the same release as new store content would couple two risky changes. They are removed
  in v0.9.0.

## Consequences

- An app can offer "always hide this" and "hide numbers like this from now on" without owning
  a second store.
- Applying the lists is the app's job: it treats `always_hide` as hide-only and compiles
  `custom.compile_pattern(p.kind, p.text)` for each pattern in its own detector.
- Version 0.8.0.
