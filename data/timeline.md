# Timeline (stopwatch, IST). Hard stop 22:00.

| Step | Plan budget | Start | End | Actual | Notes |
|---|---|---|---|---|---|
| Planning + grilling | — | 18:35 | 18:52 | 17m | plan v2 written |
| S1 setup + smoke tests | 18:55–19:20 (25m) | 18:52 | 19:08 | 16m | 4 tools OK; catalog 1,842; Mistral Large first attempt needed top_p |
| S2 pipeline + 3-app test | 19:20–19:40 (20m) | 19:08 | 19:22 | 14m | 2 iterations (access taxonomy + prompt fix) |
| S3 full pass 1 | est. 100 apps × 13 s ÷ 5 ≈ 5 m | 19:22 | 19:28 | ~6m | 100/100, $0.20, 375 fetches |
| Checklist (blind, seed 42) | — | 19:28 | 19:31 | 3m | 15 apps × 6 claims |
| Verifier v1 run | est. 25 m | 19:33 | 19:39 | stopped | bugs: L1 narrowed auth; L4 quotes never mapped; L4 queue ~3 min/run; Large judge timeouts |
| Verifier v2 (L0–L3, all 100) | est. 100 ÷ ~5.5/min ≈ 18 m | 19:42 | | | browser L4 split out as its own step |
