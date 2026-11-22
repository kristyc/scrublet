# Bench results

Every `python -m tacitkit.bench bakeoff` run appends here (this table is rebuilt each time). Synthetic cases only. The winner is the highest names-caught model that passes the run's decision rule; "none" means no model passed, and the numbers are then for the model the report picked (or the best by names caught if it picked none).

| Date | Run | Report | Corpus | Winner | Names caught | Asian | Wrongly hidden | p95 ms | Peak RAM MB | Models |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-22 | bakeoff | [2026-11-22-bakeoff.md](2026-11-22-bakeoff.md) | f15659ceeaf0ffa1 | none | 80.5% | 100.0% | 1.8% | 259 | 2029 (after load) | 12 |
| 2026-11-22 | lean-parity | [2026-11-22-lean-parity.md](2026-11-22-lean-parity.md) | f15659ceeaf0ffa1 | GLiNER multi PII v1 (lean runner, embedding table int8) | 80.9% | 100.0% | 1.8% | 88 | 1028 | 2 |
| 2026-11-22 | lean-vs-current | [2026-11-22-lean-vs-current.md](2026-11-22-lean-vs-current.md) | f15659ceeaf0ffa1 | GLiNER multi PII v1 (lean runner, embedding table int8) | 80.9% | 100.0% | 1.8% | 76 | 1028 | 3 |
| 2026-11-22 | slim | [2026-11-22-slim.md](2026-11-22-slim.md) | f15659ceeaf0ffa1 | GLiNER multi PII v1 (ONNX, embedding table int8 (maths fp32)) | 80.9% | 100.0% | 1.8% | 75 | 1314 | 5 |
