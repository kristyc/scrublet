# Lean GLiNER runner: parity with the gliner package

2026-11-22. Local only; synthetic cases only; 2 CPU threads; each model ran alone in a fresh process at below-normal priority.

## Decision rule (set before the numbers)

A challenger replaces the baseline only if it:

1. catches **at least 77.5%** of names
2. catches **at least 95%** of Malay, Chinese and Indian names
3. wrongly hides **at most 2.5%** of facts
4. uses **at most 1500 MB** of memory at peak (fresh process)
5. takes **at most 300 ms** per message at p95

Licence never blocks an owner's own use. It only decides whether a model can be bundled in a public library or must be an optional download.

## Recommendation

**Adopt GLiNER multi PII v1 (lean runner, embedding table int8).** It passes every rule: 80.9% of names caught, 100.0% of Asian names, 1.8% of facts wrongly hidden, 1028 MB at peak, p95 88 ms. Licence: OK for personal and company use; can be bundled.

**What this run proves.** The lean runner (`scrublet_pii.models.gliner_onnx`: onnxruntime, tokenizers and numpy only) gives the same predictions as the gliner package on the same ONNX file. The headline numbers match to the case (a separate check found 0 different predictions on all 1,430 cases and on 14 awkward inputs: empty, symbols, emoji, mixed scripts, non-breaking spaces). The extra rows show what dropping torch and the gliner package saves in memory. For text longer than about 380 words the lean runner is *better* than the gliner package, which silently ignores everything after its first 384 words; the lean runner reads it all in overlapping windows (on a 714-word test text it found all three names, the package found two).

## Headline

1430 cases in 13 categories (corpus f15659ceeaf0ffa1). **Speed is like-for-like only against a baseline row of the same precision**: read the "same precision" column, not raw milliseconds across precisions. "Within noise" means p ≥ 0.05 on a paired McNemar test.

| Model | Precision | Names caught (95% CI) | vs baseline | Asian names | Wrongly hidden (95% CI) | vs baseline | ms median (p95) | vs baseline, same precision | Peak RAM | Licence | What that means |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32)) | fp32+emb8 | **80.9%** (78-83) | baseline | 100.0% | **1.8%** (1-3) | baseline | 57 (81) | - | 1315 MB | Apache-2.0 | OK for personal and company use; can be bundled |
| GLiNER multi PII v1 (lean runner, embedding table int8) | fp32+emb8 | **80.9%** (78-83) | +0.0 pts (**within noise**) | 100.0% | **1.8%** (1-3) | +0.0 pts (**within noise**) | 59 (88) | - | 1028 MB | Apache-2.0 | OK for personal and company use; can be bundled |

## Rules, model by model

| Model | names caught | Asian names | wrong hides | peak RAM | p95 speed | Adopt? |
|---|---|---|---|---|---|---|
| GLiNER multi PII v1 (lean runner, embedding table int8) | pass | pass | pass | pass | pass | **yes** |

## Who wins where: names caught, % per category (bold is best)

| Model | english | malay | chinese | indian | allcaps | split_lines | cut_off | glued | statement_rows |
|---|---|---|---|---|---|---|---|---|---|
| GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32)) | **100** | **100** | **100** | **100** | **74** | **93** | **44** | **40** | **75** |
| GLiNER multi PII v1 (lean runner, embedding table int8) | **100** | **100** | **100** | **100** | **74** | **93** | **44** | **40** | **75** |

Facts wrongly hidden, % per category (lower is better; the shops category is shown on its own because hiding a shop named after a person is defensible):

| Model | organisations | places | facts_survive | statement_rows | allcaps | cut_off | shops_named_after_people |
|---|---|---|---|---|---|---|---|
| GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32)) | 0 | 3 | 2 | 4 | 0 | 0 | 24 |
| GLiNER multi PII v1 (lean runner, embedding table int8) | 0 | 3 | 2 | 4 | 0 | 0 | 24 |

## Example misses (synthetic)


**GLiNER multi PII v1 (lean runner, embedding table int8)**: 178 names missed, 22 facts wrongly hidden.
- missed (allcaps, 29 in this category): `PAYEE IVAN TEO  14.88`
- missed (split_lines, 8 in this category): `Transfer to Mohan / Raj for the deposit`
- missed (cut_off, 62 in this category): `22 Aug 2026 DUITNOW TRF TEO MEI Y RM89.15`
- missed (glued, 66 in this category): `PAYMENTTOKAVITHA A/P NAIR MYR 576.83`
- missed (statement_rows, 13 in this category): `12/01/2026 IBG CR FOO CHEE KEONG REF 0031882 RM 533.87`
- wrongly hid `Taman Tun Dr Ismail` in `Is there a post office in Taman Tun Dr Ismail?`
- wrongly hid `VILLAGE GROCER` in `03/04/2026 VILLAGE GROCER  RM95.76 DR`
- wrongly hid `MYDIN` in `2026-09-11 CARD TXN MYDIN KUALA LUMPUR RM 315.79`
