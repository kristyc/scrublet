# ADR 0002: Hard detectors and folding, moved unchanged

Status: accepted (22 Nov 2026)

## Decision

`scrublet_pii.patterns` holds the hard detectors, and `scrublet_pii.fold` holds the folding with an
index map. Both are moved byte for byte from the owner's assistant app's gate, which had the
stronger card, IC, passport, account and key detection of the apps reviewed. Comments that cite
that app's ADRs and review items keep those references for history.

- A pack is an ordered tuple of `Detector(name, group, finder)`. The Malaysian pack `"my"` is the
  only pack so far. Its local parts are the IC birth-date groups, the road words, the postcode
  and town, the bank names, RM, and the passport letter shapes.
- `name` is value-free (`pattern.card`). `group` is `identity`, `financial` or `credential`.
  Each app maps the group to its own categories, and the name to its own tier (hide, liftable or
  hard). The tiers themselves move to `scrublet_pii.policy` later.
- `find()` returns `(start, stop, name)` and `kinds()` returns the names, never a value.
- A finder is a compiled regex or a regex-like object (`search` and `finditer` yielding spans).
  Cards are found by network prefix plus Luhn, read across printed groups (spaces, non-breaking
  spaces, dashes and line breaks) and at either end of a glued run.

## Verification

- On every corpus text, each detector found exactly the spans the source app's detector found
  (a parity run before the move).
- Every hard corpus item is found, and its hits cover the whole secret.
- No everyday search trips a hard detector.

## Not yet

- The name and word matcher (`printed`), which merges both apps' matchers, is the next step.
- A masked-card shape (`XXXX XXXX XXXX 1234`) and other country packs come later.
