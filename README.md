# scrublet

**Little scrubber, big privacy.**

scrublet keeps private words out of what your apps send to AI. It is a small Python library
that several apps can share, so one list of private names, one set of detectors and one
test corpus protect all of them. The Python package is `scrublet-pii`; you import
`scrublet_pii`.

## What it does

- **A shared word store** (`terms`): one JSON file in the user's config folder. Every app on
  the machine reads and writes the same never-send and always-OK lists, plus read-only *name
  sources* such as the cardholder field of another app's config file. Writes are locked and
  atomic; a damaged store is reported, never overwritten. See [ADR 0001](docs/adr/0001-global-word-store.md).
- **Hard detectors** (`patterns`, `fold`): keys and secrets, cards, ID numbers, passports, bank
  accounts, phones, emails and addresses, found in messy layouts. They return value-free names
  (`pattern.card`), never the value. A Malaysian pack ships first; more country packs are
  welcome ([ADR 0002](docs/adr/0002-patterns-and-fold.md)).
- **A matcher for printed names** (`printed`): finds known names as documents print them: split
  across lines, cut off at a field width, glued to other text, reordered, initialled, with
  markers such as A/P and BIN ([ADR 0003](docs/adr/0003-printed-matcher.md)).
- **A labelled synthetic corpus** (`corpus`): everyday requests and hard items, with no real
  person, account or number, and a runner each app calls with its own gate.
- **A model bake-off harness** (`bench`): compares local name-finding models on 1,430
  labelled synthetic cases and writes a plain-language report with the decision rule first
  ([ADR 0004](docs/adr/0004-bench-module.md)). Past runs are kept in [bench/results](bench/results/README.md).
- **A lean model runner** (`models.gliner_onnx`): GLiNER multi PII v1 as ONNX on onnxruntime,
  tokenizers and numpy only (no torch). Same predictions as the gliner package on all bench
  cases, about 1 GB at peak ([ADR 0005](docs/adr/0005-lean-gliner-runner.md)).

scrublet has no required dependencies. Models and their runtimes are optional extras, and no
model weights are in this repository.

## Install

```
pip install scrublet-pii
```

Until it is on PyPI, install from Git:

```
pip install "git+https://github.com/kristyc/scrublet.git@v0.7.0"
```

Optional extras (only the adapter you run imports them): `bench-onnx`, `bench-torch`,
`bench-gliner`, `bench-presidio`, for example `pip install "scrublet-pii[bench-onnx]"`.
Python 3.11 or newer.

## Quick start

**The word store.** An app declares production once, at its real start-up (see
[the production guard](#the-production-guard)), then reads and writes the shared store:

```python
from scrublet_pii import terms

terms.production()                              # once, at the app's real start-up
terms.update("never_send", add=["Alex Example"])
found = terms.read()                            # raises terms.Unreadable if the store is damaged
found.words("never_send")                       # ("Alex Example",)
terms.names(found)                              # names from registered sources, fullest first
terms.problems()                                # {} when all is well; counts and ids only
```

**Hard detectors.** Value-free names for what was found:

```python
from scrublet_pii import patterns

text = "Card 4111 1111 1111 1111 exp 12/29, IC 900101-14-5678"
patterns.kinds(text)        # ('pattern.phone', 'pattern.ic', 'pattern.card')
patterns.find(text)         # [(start, stop, 'pattern.card'), ...]
```

**Printed names.** Known names found as a document prints them:

```python
from scrublet_pii import printed

printed.matches("TRANSFER TO TAN AH KOW\n  MAYBANK 5140", ["Tan Ah Kow"])
# [(12, 22, 'Tan Ah Kow')]
```

**Models and the bake-off.** Compare name-finding models without writing code:

```
python -m scrublet_pii.bench models                 # adapters, licences, what each needs
python -m scrublet_pii.bench bakeoff --models current_ner,gliner_multi_pii_lean_emb8 \
    --cache ./models --rule replace --name my-run --max-cpu 80
python -m scrublet_pii.bench export-gliner --cache ./models    # make the ONNX variants
python -m scrublet_pii.bench results                # rebuild the index of past runs
```

Models download to `--cache` at pinned commits and are **removed afterwards** unless you pass
`--keep-models`. Each model runs alone in a fresh process, so peak memory is real; speed is
compared against the baseline at the same precision. Every run appends a report and a
machine-readable record to `bench/results/` (`--no-store` to skip).

**Command line.** Counts only, never a word:

```
scrublet status
scrublet import-words <path-to-a-json-list> --id <import-id>
```

## The production guard

The real profile store is shared by every app on the machine, so a test run or a stray script
must never touch it. scrublet enforces that in the library itself, so every app gets the same
rule:

- The real store resolves **only** for a process that declares production, by calling
  `scrublet_pii.terms.production()` at its real start-up, or by setting `SCRUBLET_PRODUCTION=1`
  for a service that starts without code.
- A **test run can never resolve it**, whatever else is set. A test run is detected from
  `sys.modules` (pytest is loaded) and from `PYTEST_CURRENT_TEST`, so a test that removes its own
  environment settings, or whose app boots and declares production, still cannot reach the real
  store. Child processes of a test run are guarded too.
- Anything else raises `terms.NotProduction` instead of guessing. Nothing is read, written or created.
- `SCRUBLET_HOME` names a scratch or custom store folder and works anywhere, including tests.
  Passing an explicit `path=` to a function uses that file as given.

Tests should set `SCRUBLET_HOME` to a temp folder (the guard is a backstop, not a replacement).

## Models and licences

No weights are bundled. Each model is an optional download you enable, at a pinned commit,
checked by hash. `python -m scrublet_pii.bench models` prints the details.

| Model | Licence | In plain words |
|---|---|---|
| bert-base-NER (int8 and fp32 ONNX) | MIT | Fine for personal and company use; can be bundled |
| Presidio with spaCy `en_core_web_lg` | MIT | Fine for personal and company use; can be bundled |
| GLiNER multi PII v1, GLiNER multi v2.1, knowledgator GLiNER PII | Apache-2.0 | Fine for personal and company use; can be bundled |
| XLM-R base NER-HRL | AFL-3.0 | Fine for personal and company use; can be bundled |
| h2oai DeBERTa PII | MIT (training data not stated) | Allows bundling, but the data source is unknown |
| NVIDIA GLiNER-PII | NVIDIA Open Model License | Fine for your own use; bundling needs the licence text and NVIDIA's notice |
| ai4privacy DeBERTa (Isotonic) | CC-BY-NC-4.0 | Non-commercial: an optional download for your own use, **never bundled** |
| Piiranha | CC-BY-NC-ND-4.0 | Non-commercial and no derivatives: an optional download, used unmodified, **never bundled** |

Licences are as stated on each model's card when the adapters were written; check the card
before you rely on one.

## Renamed from tacitkit

scrublet was called tacitkit before v0.7.0. For one more version (removed in v0.8.0):

- `import tacitkit` still works and gives the same modules, with a deprecation warning;
- `TACITKIT_HOME` is still read, with a deprecation warning (`SCRUBLET_HOME` wins);
- the store folder moves from `tacitkit` to `scrublet` in the user's config folder the first
  time a production app writes. The move is atomic, idempotent and lossless (the file is copied
  byte for byte; the old one is left in place). Until it moves, the old store is read.
  `terms.problems()` reports `legacy: changed` if an app still on the old library writes to the
  old store afterwards, so move all your apps together ([ADR 0006](docs/adr/0006-rename-and-production-guard.md)).

## Contributing

Issues and pull requests are welcome.

- Run `ruff check src tests` and `pytest` before you send a change. Tests must pass without any
  model installed; tests that need one are skipped unless its folder is named in an environment variable.
- **Synthetic data only.** The corpus, tests and bench results must hold no real person, account,
  number, employer or path. Use invented names and public test values.
- A bug in a detector comes with a failing case in the corpus or the tests.
- To add a model, add a `Spec` to `scrublet_pii/bench/adapters.py` with its pinned commit and its
  licence consequence in plain words, and a loader if its kind is new. Never add weights.
- To add a country pack, follow `patterns.pack`, with value-free detector names.
- Changes that alter behaviour come with a short ADR in `docs/adr/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
