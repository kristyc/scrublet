# ADR 0005: A lean runner for GLiNER multi PII v1

Status: accepted (22 Nov 2026)

## Context

The bench (ADR 0004) found that GLiNER multi PII v1 catches 81% of names against 45% for the
model apps use today, and that it fits in 1.5 GB once its embedding table is int8 in the ONNX
export. Running it through the `gliner` package costs a torch install (about 1.2 GB) and about
290 MB of extra memory. Apps that already ship onnxruntime and tokenizers should not need more.

## Decision

`scrublet_pii.models.gliner_onnx.GlinerOnnx(folder, onnx_file)` runs the exported model with
onnxruntime, tokenizers and numpy only. It follows the gliner package's convention: words by
`\w+(?:[-_]\w+)*|\S`; the prompt `<<ENT>> person <<SEP>>`; each word its own pre-token; the
word mask on each word's first sub-token; all spans up to `max_width`; sigmoid of the logits
against the threshold; greedy non-overlapping selection by score.

**Proof, not a promise.** On all 1,430 bench cases (and 14 awkward inputs: empty, symbols,
emoji, mixed scripts, non-breaking spaces) its predictions are identical to the package's.
`bench/results/2026-11-22-lean-parity.md` stores the run: identical scores (p = 1.0), peak memory
1,028 MB against 1,315 MB, no torch loaded.

**One deliberate difference.** The gliner package silently ignores every word after its first
384. For a tool whose job is hiding names that means an unseen tail. The lean runner reads long
texts in overlapping windows (12 words shared, each at most 500 tokens), so nothing goes unseen.

## Not here

How a model reaches an app's disk (download, hash pinning, building the slim file) is each app's
install step, not this library's.
