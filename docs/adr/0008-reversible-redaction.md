# ADR 0008: Reversible redaction with a per-job token map

Status: accepted (27 Nov 2026)

## Context

Apps send everything to AI redacted, yet must act on the real values in the answer: a
transcript says "I'll email Phoebe", the AI sees a token, and the app must still draft the email
to Phoebe. Until now each app replaced values with its own stand-ins and could not reliably put
them back.

## Decision

- `reversible.redact(text, job, store=None, extra=())` returns the redacted text and the job's
  token map: token -> {"value", "kind"}, for example `"[PERSON_1]": {"value": "Phoebe Example",
  "kind": "PERSON"}`. `job` is the map so far (`None` or `{}` to start). The caller's map is
  never changed in place; the returned map is the old one plus any new tokens.
- What is hidden comes from the existing rules only: names from the registered sources
  (`terms.names`), the `never_send` and `always_hide` words, the hard detectors
  (`patterns.find`), the owner's custom patterns, and `extra` names for this call. `always_ok`
  words are not hidden. Overlapping hits become one token covering both.
- Tokens are stable within a job. Values already in the map are matched in every later text and
  keep their token; numbering continues per kind. A known person printed in part ("Phoebe") is
  the same person as the full known name, so it shares the full name's token and restores as
  that name, which is what an app acting on the answer needs.
- `reversible.restore(text, job)` replaces exact tokens only. A token not in the map is left
  as it is, so output that reorders, repeats or invents tokens is safe.
- Leak check: a redacted text that would still contain any mapped value (exactly, or as the
  printed matcher finds it) is refused with `Leaked`, which names no value. Nothing that leaks
  is returned.
- The map is plain data the app stores itself, encrypted. Scrublet never persists it.

## Consequences

- Kinds come from detector names (`EMAIL`, `PHONE`, `CARD` and so on), `PERSON` for source and
  extra names and `PRIVATE` for listed words.
- A literal token already present in the original text (for example `[PERSON_1]`) would be
  replaced on restore. Apps that may see such text should not restore it.
