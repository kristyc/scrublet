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

- **bench**: a harness that compares local name-finding models on a labelled synthetic corpus,
  with a stated decision rule and a product-owner report. Results are kept under
  [bench/results](bench/results/README.md) ([ADR 0004](docs/adr/0004-bench-module.md)).

- **models.gliner_onnx**: a lean runner for GLiNER multi PII v1 as ONNX (onnxruntime, tokenizers
  and numpy only; no torch, no gliner package). Same answers as the gliner package on all 1,430
  bench cases, about 1 GB at peak, and it reads texts past the package's 384-word limit in windows
  ([ADR 0005](docs/adr/0005-lean-gliner-runner.md)).

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

## Bench

Compare name-finding models (optional extras; no weights in the repo):

```
python -m tacitkit.bench models                    # adapters, licences, what each needs
python -m tacitkit.bench bakeoff --models current_ner,gliner_multi_pii --cache D:/models     --rule replace --name my-run --max-cpu 80
python -m tacitkit.bench export-gliner --cache D:/models   # ONNX variants of GLiNER multi PII v1
python -m tacitkit.bench results                   # rebuild the index of past runs
```

- Models download to `--cache` at pinned commits and are **removed afterwards** unless
  `--keep-models`. Only what the run added is removed.
- Each model runs alone in a fresh process, so peak memory is real. Speed is compared with the
  baseline at the same precision (`current_ner` is int8, `current_ner_fp32` is fp32).
- `--rule replace` (a clear gain, nothing lost) or `--rule slim` (stay near a full-size model's
  numbers in less memory), or set any limit: `--min-caught`, `--min-asian`, `--max-hidden`,
  `--max-ram-mb`, `--max-p95-ms` and the others.
- Every run appends a report and a `.json` record to `bench/results/` and rebuilds its index
  (`--no-store` to skip). The corpus and results are synthetic: no personal data.
- Licence notes are per adapter. Non-commercial models can be tested for your own use; they
  can't be bundled in a public library.
- Add a model: add a `Spec` to `tacitkit/bench/adapters.py` with its pinned commit and licence
  consequence, and a loader if its kind is new.

Licence: Apache-2.0.
