# Lean GLiNER runner against the current name model

2026-11-22. Local only; synthetic cases only; 2 CPU threads; each model ran alone in a fresh process at below-normal priority.

## Decision rule (set before the numbers)

A challenger replaces the baseline only if it:

1. catches at least **10 points more names** than the baseline, and the gain is not noise (paired McNemar p < 0.05)
2. catches Malay, Chinese and Indian names **no worse than** the baseline
3. wrongly hides **at most 3 points more** facts (dates, amounts, merchants, organisations, places) than the baseline
4. uses **at most 1500 MB** of memory at peak (fresh process)
5. takes **at most 200 ms** per message (median)
6. takes **at most 500 ms** per message at p95

Licence never blocks an owner's own use. It only decides whether a model can be bundled in a public library or must be an optional download.

## Recommendation

**Adopt GLiNER multi PII v1 (lean runner, embedding table int8).** It passes every rule: 80.9% of names caught, 100.0% of Asian names, 1.8% of facts wrongly hidden, 1028 MB at peak, p95 76 ms. Licence: OK for personal and company use; can be bundled.

**What this run shows.** The lean GLiNER runner against today's name model on the same 1,430 cases, each in a fresh process, 2 threads. The gliner-package row is shown only so the saving from the lean runner is visible: identical answers, about 290 MB less peak memory and no torch. The decision rule is the "replace" preset (a clear gain, nothing lost, usable speed and memory).

## Headline

1430 cases in 13 categories (corpus f15659ceeaf0ffa1). **Speed is like-for-like only against a baseline row of the same precision**: read the "same precision" column, not raw milliseconds across precisions. "Within noise" means p ≥ 0.05 on a paired McNemar test.

| Model | Precision | Names caught (95% CI) | vs baseline | Asian names | Wrongly hidden (95% CI) | vs baseline | ms median (p95) | vs baseline, same precision | Peak RAM | Licence | What that means |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bert-base-NER (int8 ONNX) | int8 | **45.0%** (42-48) | baseline | 78.2% | **0.9%** (1-2) | baseline | 14 (21) | - | 205 MB | MIT | OK for personal and company use; can be bundled (the default name model today) |
| GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32)) | fp32+emb8 | **80.9%** (78-83) | +35.9 pts (p<0.001) | 100.0% | **1.8%** (1-3) | +0.9 pts (**within noise**) | 55 (76) | - | 1314 MB | Apache-2.0 | OK for personal and company use; can be bundled |
| GLiNER multi PII v1 (lean runner, embedding table int8) | fp32+emb8 | **80.9%** (78-83) | +35.9 pts (p<0.001) | 100.0% | **1.8%** (1-3) | +0.9 pts (**within noise**) | 54 (76) | - | 1028 MB | Apache-2.0 | OK for personal and company use; can be bundled |

## Rules, model by model

| Model | names gain | Asian vs baseline | wrong hides vs baseline | peak RAM | median speed | p95 speed | Adopt? |
|---|---|---|---|---|---|---|---|
| GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32)) | pass | pass | pass | pass | pass | pass | **yes** |
| GLiNER multi PII v1 (lean runner, embedding table int8) | pass | pass | pass | pass | pass | pass | **yes** |

## Who wins where: names caught, % per category (bold is best)

| Model | english | malay | chinese | indian | allcaps | split_lines | cut_off | glued | statement_rows |
|---|---|---|---|---|---|---|---|---|---|
| bert-base-NER (int8 ONNX) | 99 | 95 | 60 | 79 | 0 | 37 | 0 | 11 | 0 |
| GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32)) | **100** | **100** | **100** | **100** | **74** | **93** | **44** | **40** | **75** |
| GLiNER multi PII v1 (lean runner, embedding table int8) | **100** | **100** | **100** | **100** | **74** | **93** | **44** | **40** | **75** |

Facts wrongly hidden, % per category (lower is better; the shops category is shown on its own because hiding a shop named after a person is defensible):

| Model | organisations | places | facts_survive | statement_rows | allcaps | cut_off | shops_named_after_people |
|---|---|---|---|---|---|---|---|
| bert-base-NER (int8 ONNX) | 4 | 4 | 1 | 0 | 0 | 0 | 33 |
| GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32)) | 0 | 3 | 2 | 4 | 0 | 0 | 24 |
| GLiNER multi PII v1 (lean runner, embedding table int8) | 0 | 3 | 2 | 4 | 0 | 0 | 24 |

## Example misses (synthetic)


**GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32))**: 178 names missed, 22 facts wrongly hidden.
- missed (allcaps, 29 in this category): `PAYEE IVAN TEO  14.88`
- missed (split_lines, 8 in this category): `Transfer to Mohan / Raj for the deposit`
- missed (cut_off, 62 in this category): `22 Aug 2026 DUITNOW TRF TEO MEI Y RM89.15`
- missed (glued, 66 in this category): `PAYMENTTOKAVITHA A/P NAIR MYR 576.83`
- missed (statement_rows, 13 in this category): `12/01/2026 IBG CR FOO CHEE KEONG REF 0031882 RM 533.87`
- wrongly hid `Taman Tun Dr Ismail` in `Is there a post office in Taman Tun Dr Ismail?`
- wrongly hid `VILLAGE GROCER` in `03/04/2026 VILLAGE GROCER  RM95.76 DR`
- wrongly hid `MYDIN` in `2026-09-11 CARD TXN MYDIN KUALA LUMPUR RM 315.79`

**GLiNER multi PII v1 (lean runner, embedding table int8)**: 178 names missed, 22 facts wrongly hidden.
- missed (allcaps, 29 in this category): `PAYEE IVAN TEO  14.88`
- missed (split_lines, 8 in this category): `Transfer to Mohan / Raj for the deposit`
- missed (cut_off, 62 in this category): `22 Aug 2026 DUITNOW TRF TEO MEI Y RM89.15`
- missed (glued, 66 in this category): `PAYMENTTOKAVITHA A/P NAIR MYR 576.83`
- missed (statement_rows, 13 in this category): `12/01/2026 IBG CR FOO CHEE KEONG REF 0031882 RM 533.87`
- wrongly hid `Taman Tun Dr Ismail` in `Is there a post office in Taman Tun Dr Ismail?`
- wrongly hid `VILLAGE GROCER` in `03/04/2026 VILLAGE GROCER  RM95.76 DR`
- wrongly hid `MYDIN` in `2026-09-11 CARD TXN MYDIN KUALA LUMPUR RM 315.79`
