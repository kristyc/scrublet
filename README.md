# tacitkit

Keep private words out of what your apps send to AI.

tacitkit is a small, dependency-free Python library that several apps can share:

- **terms**: one word store in the user's config folder. Every app reads and writes the same
  never-send and always-OK lists, plus read-only name sources such as a cardholder field in
  an app's own config file. See [ADR 0001](docs/adr/0001-global-word-store.md).
- **corpus**: a synthetic test corpus and a runner each app calls with its own gate.
- **patterns** and **fold**: value-free hard detectors (keys, cards, ID numbers, passports,
  accounts) in country packs, Malaysian first ([ADR 0002](docs/adr/0002-patterns-and-fold.md)).
- **printed**: one name matcher for messy printed text: split, cut off, glued, reordered,
  initials and markers ([ADR 0003](docs/adr/0003-printed-matcher.md)).

Coming next: tiers and policy helpers, and an interface for optional local name-finding models.

```python
from tacitkit import terms

terms.update("never_send", add=["Alex Example"])
found = terms.read()          # raises terms.Unreadable if the store is damaged
found.words("never_send")     # ("Alex Example",)
terms.names(found)            # names from registered sources, fullest first
```

Command line (prints counts only, never a word):

```
tacitkit status
tacitkit import-words <path-to-a-json-list> --id <import-id>
```

Licence: Apache-2.0.
