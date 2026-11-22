# ADR 0004: A bench module for comparing local name-finding models

Status: accepted (22 Nov 2026)

## Context

On 22 Nov 2026 a bake-off of 11 name-finding models ran for the first app, with throwaway
scripts. It needed to be repeatable: models change, the corpus grows, and a later model must be
judged on the same cases, by the same rule, with history kept. The bank-statement and chat
layouts it measured are the shared gate's world (ADR 0002 and 0003), so the harness belongs
here, not in one app.

## Decision

`tacitkit.bench` (the `python -m tacitkit.bench` command) is a harness, not a detector.

- **Corpus (`cases`).** 1,430 labelled synthetic cases, 13 categories of 110: names in English,
  Malay, Chinese (Latin letters and characters) and Indian forms; ALL-CAPS statement names; names
  split across lines, cut off and glued; organisations; places; statement rows; facts that must
  survive; shops named after people. Seeded; `corpus_hash` is stored with every result so runs
  on different corpora are never compared. No real person, account or number. It is separate
  from `tacitkit.corpus`, which tests gates; this one measures detectors.
- **Adapters (`adapters`).** A `Spec` per model: where it comes from (repo and pinned commit),
  precision, licence, and what the licence means in plain words (bundle it, or an optional
  download only). A loader per kind turns it into `detect(text) -> spans`. Third-party packages
  (torch, gliner, onnxruntime, Presidio, spaCy) are optional extras imported only by the adapter
  that needs them. **No weights live in the repo.** They download to a folder the user names,
  and are removed afterwards unless `--keep-models`; only what the run added is removed.
- **Fresh process per model (`worker`).** Peak memory is its own. Below-normal priority, 2
  threads by default, one model at a time, an optional wait while the PC's CPU is above a limit.
- **Statistics (`stats`).** A name is caught when every word is hidden (markers excepted); a fact
  is wrongly hidden when any word is. Wilson 95% intervals; exact paired McNemar p-values against
  the baseline, so "within noise" is a number.
- **Speed is like-for-like only against a baseline of the same precision.** The baseline has an
  int8 and an fp32 adapter; a challenger's speed is also shown as a multiple of the baseline at
  its own precision.
- **Report (`report`).** The decision rule first (`replace` and `slim` presets, or any limit by
  flag), then the recommendation, headline table with licence consequences, rule pass table,
  per-category tables and example misses.
- **Results (`results`).** Each run appends `bench/results/<date>-<name>.md` and `.json`
  (model, commit, precision, per-category scores, RAM, speed, licence, decision) and the
  `bench/results/README.md` index is rebuilt. Synthetic-case results only; no raw text.

## Not decided here

The detector the apps use. The harness only reports; adoption stays each app's decision.

## Lessons recorded from the first runs

- Whole-model int8 (gliner's own export, torch dynamic int8) breaks DeBERTa-family models: they
  find almost nothing. Quantise the embedding table only, or check quality before trusting speed.
- Memory after loading understates the peak (fp32 GLiNER: 2.1 GB after load, 3.1 GB peak). Report peak.
