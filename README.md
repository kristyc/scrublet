# tacitkit

Keep private words out of what your apps send to AI.

tacitkit is a small, dependency-free Python library that several apps can share:

- **terms**: one word store in the user's config folder. Every app reads and writes the same
  never-send and always-OK lists, plus read-only name sources such as a cardholder field in
  an app's own config file. See [ADR 0001](docs/adr/0001-global-word-store.md).

Coming next: pattern detectors (keys, cards, ID numbers), messy-text matching, a synthetic test
corpus and benchmark, and an interface for optional local name-finding models.

```python
from tacitkit import terms

terms.add("never_send", "Alex Example")
found = terms.read()          # raises terms.Unreadable if the store is damaged
found.never_send              # ("Alex Example",)
terms.names(found)            # names from registered sources, fullest first
```

Command line (prints counts only, never a word):

```
tacitkit status
tacitkit import-words <path-to-a-json-list> --id <import-id>
```

Licence: Apache-2.0.
