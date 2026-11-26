# ADR 0008: Reversible redaction with a per-job token map

Status: accepted (27 Nov 2026)

## Context

Apps send everything to AI redacted, yet must act on the real values in the answer: a
transcript says "I'll email Phoebe", the AI sees a token, and the app must still draft the email
to Phoebe. Until now each app replaced values with its own stand-ins and could not reliably put
them back.

## Decision

- `reversible.redact(text, job, store=None, extra=())` returns the redacted text and the job's
  token map: token -> {"value", "kind"}, for example `"[PERSON_1_k3f9qz]": {"value":
  "Phoebe Example", "kind": "PERSON"}`. `job` is the map so far (`None` or `{}` to start). The
  caller's map is never changed in place; the returned map is the old one plus any new tokens.
- Every token of a job ends in the job's random six-character nonce, drawn once from `secrets`
  when the map is empty and read back from the map afterwards (all tokens share it). Text fed to
  the AI cannot name a token it was not shown, so injected text cannot ask for a value back.
- Token-shaped text already in the input (`[EMAIL_1]`, `[PERSON_1_abc123]`) has its bracket
  replaced by a fullwidth bracket before redaction, so it can never be restored.
- What is hidden comes from the existing rules only: names from the registered sources
  (`terms.names`), the `never_send` and `always_hide` words, the hard detectors
  (`patterns.find`), the owner's custom patterns, and `extra` names for this call. `always_ok`
  words are not hidden.
- Overlapping hits never merge into a new value: the longer one wins whole, and a shorter one
  that reaches past it keeps its own value and token for the part outside. One value keeps one
  token.
- Tokens are stable within a job. Values already in the map are matched in every later text and
  keep their token; numbering continues per kind. A known person printed in part ("Phoebe") is
  the same person as the full known name, so it shares the full name's token and restores as
  that name, which is what an app acting on the answer needs.
- `reversible.restore(text, job, only=None)` replaces exact tokens of this job only. `only`
  names the kinds a field may receive (for example `{"PERSON"}` for a greeting); a token of
  another kind stays a token. A token inside a link or address (`https://`, `www.`,
  `mailto:` and similar) is never restored, so the AI cannot carry a value into a URL. Unknown
  tokens stay as they are.
- Leak check: a redacted text that would still contain any mapped value (exactly, or as the
  printed matcher finds it) is refused with `Leaked`, which names no value.
- The map is plain data the app stores itself, encrypted. Scrublet never persists it.

### Folding lookalikes

`fold` (shared by the printed matcher and the corpus) NFKC-normalises each character and reads
Cyrillic and Greek letters drawn like Latin ones as the Latin letter, after case-folding. A
fullwidth or lookalike spelling of a known name now folds to the same text as the name, in every
app, not only in reversible redaction.

## Consequences

- Kinds come from detector names (`EMAIL`, `PHONE`, `CARD` and so on), `PERSON` for source and
  extra names and `PRIVATE` for listed words.
- An app that needs a value inside a link builds the link itself from the map, never from the
  AI's text.
- Where two values overlap, the restored text may repeat the shorter value's overlapping part.
- Names really written in Cyrillic or Greek fold to Latin letters on both sides, so matching
  stays consistent; a Latin word that happens to match such a folded name is hidden too.
