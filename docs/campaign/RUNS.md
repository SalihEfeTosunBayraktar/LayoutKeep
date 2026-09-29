# Translation runs on disk

Written by `tools/audit/run_registry.py`; regenerate it rather than editing it. Every run
under `_artifacts/{heldout/live, heldout/runs, campaign, bench}` and
`LayoutKeep_bench/_artifacts/bench` is listed with what can be established about it.

How each cell was established: plain = **recorded** (the run itself says so), `~` =
**inferred** (read off a directory or file name), `?` = **unknown** - nothing on disk
establishes it, and nothing has been filled in to look complete. The evidence behind every
field is in `RUNS.json`, which carries the same table as data.

A run that records no commit of its own is left unknown on purpose. The held-out
campaign's code versions were written down by hand, not per run -
`_artifacts/heldout/code_versions.log` (which document, and from which time on) and
`_artifacts/heldout/run_heldout.sh` (the worktree frozen at `bad981a`). Prose is not
parsed into this table: a sentence covering "every later document" is not a per-run
record, and reading it as one would put a commit next to a run that may not have used it.

Runs listed: **119**. Scanned 2026-09-23 01:07.

## How much of each field is known

| field | recorded | inferred | unknown |
|---|---|---|---|
| source | 116 | 0 | 3 |
| direction | 119 | 0 | 0 |
| date | 119 | 0 | 0 |
| commit | 66 | 1 | 52 |
| model | 119 | 0 | 0 |
| settings | 51 | 0 | 68 |
| audit | 104 | 0 | 15 |

## The runs

| run | source | direction | date | commit | model | settings | audit |
|---|---|---|---|---|---|---|---|
| bench-repo/arxiv_18014 | source.pdf | en->tr | 2026-09-23 00:58 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 109 blk, L=2, D=13 |
| bench-repo/arxiv_18014 | source.pdf | en->tr | 2026-09-23 00:58 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 108 blk, L=1, D=13 |
| bench-repo/tr_tck_5237 | source.pdf | tr->en | 2026-09-22 23:07 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 39 blk, L=2, D=14 |
| bench-repo/tr_kalkinma_12 | source.pdf | tr->en | 2026-09-22 23:06 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 33 blk, L=1, D=4 |
| bench-repo/nist_vapor_scan | source.pdf | en->tr | 2026-09-22 23:05 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 80 blk, L=1, D=8 |
| bench-repo/mushrooms_1895 | source.pdf | en->tr | 2026-09-22 23:04 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 62 blk, lossless, D=7 |
| bench-repo/sbb_plan_12_en | source.pdf | en->tr | 2026-09-22 23:03 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 38 blk, L=1, D=0 |
| bench-repo/cookbook_1907 | source.pdf | en->tr | 2026-09-22 23:01 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 87 blk, lossless, D=4 |
| bench-repo/history_of_math | source.pdf | en->tr | 2026-09-22 23:01 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 4 blk, lossless, D=0 |
| bench-repo/nasa_scan | source.pdf | en->tr | 2026-09-22 23:01 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 13 blk, L=3, D=6 |
| bench-repo/irs_p505 | source.pdf | en->tr | 2026-09-22 22:58 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 270 blk, L=2, D=79 |
| bench-repo/nist_jres | source.pdf | en->tr | 2026-09-22 22:57 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 71 blk, L=2, D=17 |
| bench-repo/irs_i1040gi | source.pdf | en->tr | 2026-09-22 22:50 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 82 blk, lossless, D=27 |
| bench-repo/arxiv_19145 | source.pdf | en->tr | 2026-09-22 22:43 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 64 blk, L=3, D=32 |
| bench-repo/wiki_printing_press | source.pdf | en->tr | 2026-09-22 22:39 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 44 blk, lossless, D=2 |
| bench-repo/wiki_photosynthesis | source.pdf | en->tr | 2026-09-22 22:38 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 32 blk, lossless, D=4 |
| bench-repo/plos | source.pdf | en->tr | 2026-09-22 22:32 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 58 blk, lossless, D=14 |
| bench-repo/arxiv_19113 | source.pdf | en->tr | 2026-09-22 22:24 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.auto_glossary=True... | 40 blk, lossless, D=5 |
| bench-repo/tr_tck_5237 | source.pdf | tr->en | 2026-09-22 22:16 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 39 blk, L=2, D=14 |
| bench-repo/nist_vapor_scan | source.pdf | en->tr | 2026-09-22 22:15 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 80 blk, L=2, D=8 |
| bench-repo/tr_kalkinma_12 | source.pdf | tr->en | 2026-09-22 22:15 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 33 blk, L=1, D=5 |
| bench-repo/sbb_plan_12_en | source.pdf | en->tr | 2026-09-22 22:14 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 38 blk, L=1, D=0 |
| bench-repo/mushrooms_1895 | source.pdf | en->tr | 2026-09-22 22:12 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 62 blk, lossless, D=7 |
| bench-repo/history_of_math | source.pdf | en->tr | 2026-09-22 22:11 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 4 blk, lossless, D=0 |
| bench-repo/cookbook_1907 | source.pdf | en->tr | 2026-09-22 22:09 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 87 blk, lossless, D=3 |
| bench-repo/nasa_scan | source.pdf | en->tr | 2026-09-22 22:09 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 13 blk, L=3, D=6 |
| bench-repo/nist_jres | source.pdf | en->tr | 2026-09-22 22:06 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 71 blk, L=1, D=16 |
| bench-repo/irs_p505 | source.pdf | en->tr | 2026-09-22 22:05 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 270 blk, L=2, D=77 |
| bench-repo/irs_i1040gi | source.pdf | en->tr | 2026-09-22 21:59 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 82 blk, lossless, D=28 |
| bench-repo/arxiv_19145 | source.pdf | en->tr | 2026-09-22 21:52 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 64 blk, L=1, D=33 |
| bench-repo/wiki_printing_press | source.pdf | en->tr | 2026-09-22 21:51 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 44 blk, lossless, D=3 |
| bench-repo/tr_tck_5237 | source.pdf | tr->en | 2026-09-22 21:49 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 39 blk, L=4, D=14 |
| bench-repo/wiki_photosynthesis | source.pdf | en->tr | 2026-09-22 21:49 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 32 blk, L=1, D=3 |
| bench-repo/wiki_printing_press | source.pdf | en->tr | 2026-09-22 21:48 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 44 blk, lossless, D=2 |
| bench-repo/tr_kalkinma_12 | source.pdf | tr->en | 2026-09-22 21:47 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 33 blk, L=1, D=4 |
| bench-repo/sbb_plan_12_en | source.pdf | en->tr | 2026-09-22 21:46 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 38 blk, L=1, D=0 |
| bench-repo/plos | source.pdf | en->tr | 2026-09-22 21:45 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 58 blk, L=1, D=14 |
| bench-repo/wiki_photosynthesis | source.pdf | en->tr | 2026-09-22 21:45 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 32 blk, lossless, D=4 |
| bench-repo/nist_jres | source.pdf | en->tr | 2026-09-22 21:44 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 71 blk, L=1, D=16 |
| bench-repo/nist_vapor_scan | source.pdf | en->tr | 2026-09-22 21:44 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 80 blk, L=2, D=21 |
| bench-repo/mushrooms_1895 | source.pdf | en->tr | 2026-09-22 21:43 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 62 blk, lossless, D=4 |
| bench-repo/nasa_scan | source.pdf | en->tr | 2026-09-22 21:43 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 13 blk, L=2, D=7 |
| bench-repo/irs_p505 | source.pdf | en->tr | 2026-09-22 21:42 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 270 blk, L=3, D=81 |
| bench-repo/irs_i1040gi | source.pdf | en->tr | 2026-09-22 21:41 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 82 blk, lossless, D=29 |
| bench-repo/cookbook_1907 | source.pdf | en->tr | 2026-09-22 21:40 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 87 blk, lossless, D=4 |
| bench-repo/history_of_math | source.pdf | en->tr | 2026-09-22 21:40 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 4 blk, lossless, D=0 |
| bench-repo/arxiv_19145 | source.pdf | en->tr | 2026-09-22 21:39 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 64 blk, L=3, D=38 |
| bench-repo/plos | source.pdf | en->tr | 2026-09-22 21:39 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 58 blk, lossless, D=13 |
| bench-repo/arxiv_19113 | source.pdf | en->tr | 2026-09-22 21:38 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 40 blk, lossless, D=7 |
| bench-repo/arxiv_18014 | source.pdf | en->tr | 2026-09-22 21:37 | d9f2129 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 106 blk, L=2, D=10 |
| bench-repo/arxiv_19113 | source.pdf | en->tr | 2026-09-22 21:33 | 34495d6 | google/gemma-4-e4b | output.timing_report=True, translation.workers=8 | 40 blk, lossless, D=7 |
| bench/tck_rewrite | 3 chunk files | tr->en | 2026-09-22 21:28 | ? | google/gemma-4-e4b | ? | ? |
| bench/nasa_scan | source.pdf | en->tr | 2026-09-22 20:35 | ~e911715 | google/gemma-4-e4b | ? | 13 blk, L=3, D=7 |
| heldout/live/tr_plan_11 | 50 chunk files | tr->en | 2026-09-21 16:57 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/tr_tck_5237 | 22 chunk files | tr->en | 2026-09-21 16:57 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/arxiv_2601_00135_run | 6 chunk files | en->tr | 2026-09-21 07:06 | ? | google/gemma-4-e4b | ? | 212 blk, L=32, D=109 |
| heldout/live/tr_tck_5237_r3 | 22 chunk files | tr->en | 2026-09-21 05:25 | ? | google/gemma-4-e4b | ? | 1594 blk, L=105, D=370 |
| heldout/live/gutenberg_56464 | ? | en->tr | 2026-09-21 03:39 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/tr_tck_smoke | 22 chunk files | tr->en | 2026-09-21 02:08 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/tr_tck_5237_r2 | 22 chunk files | tr->en | 2026-09-21 02:07 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/tr_plan_12 | 64 chunk files | tr->en | 2026-09-20 22:44 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/en_sbb_plan_12 | 66 chunk files | en->tr | 2026-09-20 21:51 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/tr_tmk_4721 | 41 chunk files | tr->en | 2026-09-20 20:49 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/tr_cmk_5271 | 23 chunk files | tr->en | 2026-09-20 20:06 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/gutenberg_math | 139 chunk files | en->tr | 2026-09-20 17:53 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/ross_stats_full | 106 chunk files | en->tr | 2026-09-20 17:51 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/arxiv_2605_18014 | 24 chunk files | en->tr | 2026-09-20 11:28 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/arxiv_2510_03959 | 81 chunk files | en->tr | 2026-09-20 08:46 | ? | google/gemma-4-e4b | ? | ? |
| heldout/live/cookbook_1907_r2 | 35 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 510 blk, L=2, D=147 |
| heldout/live/fresh_p05_grant | 1 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 33 blk, lossless, D=22 |
| heldout/live/fresh_pdfmt_grant | 8 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 148 blk, L=4, D=70 |
| heldout/live/fresh_pdfmt_r4 | 8 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 149 blk, L=3, D=73 |
| heldout/live/fresh_pdfmt_r5 | 8 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 149 blk, L=3, D=72 |
| heldout/live/fresh_pdfmt_r6 | 8 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 149 blk, L=3, D=72 |
| heldout/live/fresh_pdfmt_shorten | 8 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 148 blk, L=4, D=70 |
| heldout/live/fresh_pdfmt_shorten_rewritten | 8 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 148 blk, L=3, D=71 |
| heldout/live/fresh_pdfmt_strict | 8 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 36 blk, L=1, D=28 |
| heldout/live/irs_i1040gi_r2 | 32 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 1166 blk, L=7, D=341 |
| heldout/live/irs_p505_r2 | 48 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 2145 blk, L=27, D=465 |
| heldout/live/irs_reflow | 32 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 101 blk, L=3, D=1 |
| heldout/live/mushrooms_1895_sample_r2 | 41 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 267 blk, L=4, D=34 |
| heldout/live/nasa_grant | 1 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 13 blk, L=1, D=5 |
| heldout/live/nasa_ntrs_scan | 1 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 13 blk, L=1, D=5 |
| heldout/live/nasa_ntrs_scan_r2 | 1 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 13 blk, L=3, D=7 |
| heldout/live/nist_ir6643_reflow | 61 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 29 blk, L=1, D=4 |
| heldout/live/nist_ir6643_vapor_pressure | 61 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 29 blk, L=1, D=4 |
| heldout/live/nist_jres_reflow | 157 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 114 blk, L=2, D=7 |
| heldout/live/nist_jres_v98n1 | 157 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 158 blk, L=3, D=63 |
| heldout/live/plos_animal_movement_r2 | 30 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 468 blk, L=2, D=176 |
| heldout/live/ross_stats | 211 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 4491 blk, L=9, D=964 |
| heldout/live/wikipedia_photosynthesis_r2 | 33 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 354 blk, L=7, D=27 |
| heldout/live/wikipedia_printing_press_r2 | 19 chunk files | en->tr | 2026-09-20 07:11 | ? | google/gemma-4-e4b | ? | 260 blk, L=3, D=16 |
| heldout/live/arxiv_19113_r2 | 29 chunk files | en->tr | 2026-09-20 07:10 | ? | google/gemma-4-e4b | ? | 506 blk, L=1, D=91 |
| heldout/live/arxiv_19145_r2 | 20 chunk files | en->tr | 2026-09-20 07:10 | ? | google/gemma-4-e4b | ? | 489 blk, L=9, D=299 |
| heldout/runs/irs_p505_rewritten | 48 chunk files | en->tr | 2026-09-20 06:24 | dd52021 | google/gemma-4-e4b | ? | 2144 blk, L=12, D=514 |
| heldout/runs/cookbook_1907_rewritten | 35 chunk files | en->tr | 2026-09-20 06:10 | a0f1a21 | google/gemma-4-e4b | ? | 444 blk, L=2, D=130 |
| heldout/runs/irs_i1040gi | 32 chunk files | en->tr | 2026-09-19 06:14 | 2f0f94e | google/gemma-4-e4b | ? | 737 blk, L=10, D=212 |
| heldout/runs/mushrooms_1895_sample | 41 chunk files | en->tr | 2026-09-19 05:39 | 360fad5 | google/gemma-4-e4b | ? | 264 blk, L=1, D=45 |
| heldout/runs/cookbook_1907 | 35 chunk files | en->tr | 2026-09-19 05:30 | a0f1a21 | google/gemma-4-e4b | ? | 444 blk, L=2, D=130 |
| heldout/runs/gutenberg_sherlock | ? | en->tr | 2026-09-19 05:14 | e839938 | google/gemma-4-e4b | ? | 2624 blk, L=2, D=0 |
| heldout/runs/arxiv_19145_v2 | 20 chunk files | en->tr | 2026-09-19 04:07 | aff28d6 | google/gemma-4-e4b | ? | 489 blk, L=22, D=323 |
| heldout/runs/irs_p505 | 48 chunk files | en->tr | 2026-09-17 18:54 | dd52021 | google/gemma-4-e4b | ? | 2144 blk, L=12, D=514 |
| heldout/runs/nasa_ntrs_scan | 1 chunk files | en->tr | 2026-09-17 17:42 | e45ddb8 | google/gemma-4-e4b | ? | 13 blk, L=1, D=6 |
| heldout/runs/arxiv_19145 | 20 chunk files | en->tr | 2026-09-17 17:36 | bad981a | google/gemma-4-e4b | ? | 478 blk, L=13, D=305 |
| heldout/runs/wikipedia_photosynthesis | 33 chunk files | en->tr | 2026-09-17 17:35 | ccf5348 | google/gemma-4-e4b | ? | 359 blk, L=6, D=36 |
| heldout/runs/plos_animal_movement | 30 chunk files | en->tr | 2026-09-17 17:10 | 6390410 | google/gemma-4-e4b | ? | 468 blk, L=11, D=186 |
| heldout/runs/arxiv_19113 | 29 chunk files | en->tr | 2026-09-17 16:41 | 6390410 | google/gemma-4-e4b | ? | 511 blk, L=9, D=124 |
| heldout/runs/wikipedia_printing_press | 19 chunk files | en->tr | 2026-09-17 16:14 | 583027d | google/gemma-4-e4b | ? | 250 blk, L=5, D=28 |
| heldout/runs/wpa_poster | ? | en->tr | 2026-09-17 15:57 | bad981a | google/gemma-4-e4b | ? | ? |
| campaign/architecture | 524 chunk files | en->tr | 2026-09-17 14:38 | ? | google/gemma-4-e4b | ? | 7417 blk, L=80, D=666 |
| campaign/think_python | 244 chunk files | en->tr | 2026-09-17 14:23 | ? | google/gemma-4-e4b | ? | 3506 blk, lossless, D=402 |
| campaign/electricity_1922 | 148 chunk files | en->tr | 2026-09-17 13:49 | ? | google/gemma-4-e4b | ? | 956 blk, L=27, D=51 |
| campaign/nist | 101 chunk files | en->tr | 2026-09-17 13:49 | ? | google/gemma-4-e4b | ? | 1585 blk, lossless, D=395 |
| campaign/popular_science_1920 | 144 chunk files | en->tr | 2026-09-17 13:49 | ? | google/gemma-4-e4b | ? | 4222 blk, L=127, D=1023 |
| campaign/time_machine | 120 chunk files | en->tr | 2026-09-17 12:41 | ? | google/gemma-4-e4b | ? | 532 blk, lossless, D=92 |
| campaign/digital_pilot2 | 30 chunk files | en->tr | 2026-09-17 01:58 | ? | google/gemma-4-e4b | ? | 418 blk, L=2, D=62 |
| campaign/digital_pilot | 30 chunk files | en->tr | 2026-09-17 01:33 | ? | google/gemma-4-e4b | ? | 406 blk, L=4, D=52 |
| campaign/pilot10b | 10 chunk files | en->tr | 2026-09-16 23:45 | ? | google/gemma-4-e4b | ? | 149 blk, L=1, D=12 |
| campaign/pilot10 | 10 chunk files | en->tr | 2026-09-16 23:11 | ? | google/gemma-4-e4b | ? | 149 blk, L=5, D=16 |

## Directories that are not runs

| directory | why |
|---|---|
| campaign/books | no audit.json, no log and no translated output at its top; holds: electricity_agriculture_1922.pdf, nist_sp800_12r1.pdf, popular_science_1920_01.pdf, think_python_2e.pdf, time_machine.pdf |
| campaign/echo_experiment | no audit.json, no log and no translated output at its top; holds: result.txt, result_batch.txt, result_context.txt, result_markers.txt, result_numbers.txt, result_parallel.txt ... |
| campaign/nist_layout_probe | no audit.json, no log and no translated output at its top; holds: pure_nist_sp800_12r1_p20.png, pure_nist_sp800_12r1_p35.png, pure_nist_sp800_12r1_p6.png, pure_nist_sp800_12r1_p60.png, pure_nist_sp800_12r1_p7.png |

## Loose files beside the runs (not runs, listed so they are not missed)

- `campaign`: `nist_p20.pdf`, `nist_p7.pdf`, `runs_stdout.log`
- `bench`: `consA.log`, `early_arxiv_19145_r2.json`, `early_tr_plan_12.json`, `early_tr_tck_5237_r3.json`, `early_wikipedia_photosynthesis_r2.json`, `judgeA.log`
