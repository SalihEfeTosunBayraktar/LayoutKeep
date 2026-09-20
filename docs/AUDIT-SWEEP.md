# Denetim taraması: tüm koşular, üç araç

`tools/audit/sweep_runs.py` ile üretildi. Sıralama, en çok kayıp bildiren koşu üstte
olacak şekilde: listenin başı bir sonraki hatanın arandığı yerdir.

| Koşu | Kayıplar (audit.json) | type_drift | görsel üstü metin |
|---|---|---|---|
| `arxiv_19113` | L2=1, L6=7, L7=1 | 0 büyümüş, 44 küçülmüş, 4 hizası değişmiş, 7 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `arxiv_19145` | L1=1, L2=7, L6=2, L7=1, L8=2 | 21 büyümüş, 62 küçülmüş, 3 hizası değişmiş, 63 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `arxiv_19145_v2` | L2=7, L6=3, L7=6, L8=6 | 25 büyümüş, 114 küçülmüş, 2 hizası değişmiş, 98 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `cookbook_1907` | L2=1, L6=1 | 0 büyümüş, 84 küçülmüş, 0 hizası değişmiş, 12 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `cookbook_1907_rewritten` | L2=1, L6=1 | 0 büyümüş, 84 küçülmüş, 1 hizası değişmiş, 12 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `gutenberg_sherlock` | L2=1, L6=1 | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `irs_i1040gi` | L2=1, L6=6, L8=3 | 0 büyümüş, 78 küçülmüş, 2 hizası değişmiş, 50 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `irs_p505` | L2=2, L6=8, L8=2 | 0 büyümüş, 66 küçülmüş, 8 hizası değişmiş, 57 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `irs_p505_rewritten` | L2=2, L6=8, L8=2 | 1 büyümüş, 35 küçülmüş, 11 hizası değişmiş, 39 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `mushrooms_1895_sample` | L2=1 | 0 büyümüş, 28 küçülmüş, 0 hizası değişmiş, 10 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `nasa_ntrs_scan` | L2=1 | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `plos_animal_movement` | L2=3, L3=8 | 18 büyümüş, 24 küçülmüş, 0 hizası değişmiş, 10 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `wikipedia_photosynthesis` | L2=5, L6=1 | 0 büyümüş, 7 küçülmüş, 0 hizası değişmiş, 1 okunamaz boyutta | toplam 13 kelime gorselin ustunde |
| `wikipedia_printing_press` | L1=1, L2=4 | 4 büyümüş, 5 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 13 kelime gorselin ustunde |
| `arxiv_19113_r2` | L6=1 | 0 büyümüş, 38 küçülmüş, 4 hizası değişmiş, 7 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `arxiv_19145_r2` | L10=1, L2=3, L6=4, L7=1 | 16 büyümüş, 67 küçülmüş, 3 hizası değişmiş, 61 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `cookbook_1907_r2` | L6=2 | 0 büyümüş, 6 küçülmüş, 0 hizası değişmiş, 2 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `fresh_pdfmt_grant` | L2=2, L8=1, L9=1 | 0 büyümüş, 11 küçülmüş, 3 hizası değişmiş, 2 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `fresh_pdfmt_r4` | L2=2, L9=1 | 1 büyümüş, 11 küçülmüş, 3 hizası değişmiş, 1 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `fresh_pdfmt_r5` | L2=2, L9=1 | 1 büyümüş, 10 küçülmüş, 3 hizası değişmiş, 2 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `fresh_pdfmt_r6` | L2=2, L9=1 | 0 büyümüş, 10 küçülmüş, 3 hizası değişmiş, 1 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `fresh_pdfmt_shorten` | L2=2, L7=1, L9=1 | 0 büyümüş, 11 küçülmüş, 3 hizası değişmiş, 2 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `fresh_pdfmt_shorten_rewritten` | L2=2, L9=1 | 0 büyümüş, 11 küçülmüş, 3 hizası değişmiş, 2 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `fresh_pdfmt_strict` | L1=1 | 0 büyümüş, 9 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `irs_i1040gi_r2` | L2=1, L6=4, L8=2 | 0 büyümüş, 180 küçülmüş, 7 hizası değişmiş, 133 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `irs_p505_r2` | L2=5, L6=9, L7=11, L8=2 | 0 büyümüş, 49 küçülmüş, 7 hizası değişmiş, 48 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `irs_reflow` | L1=1, L7=1, L8=1 | 0 büyümüş, 2 küçülmüş, 1 hizası değişmiş, 2 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `mushrooms_1895_sample_r2` | L2=1, L6=1, L7=2 | 0 büyümüş, 16 küçülmüş, 0 hizası değişmiş, 3 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `nasa_grant` | L2=1 | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `nasa_ntrs_scan` | L2=1 | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `nasa_ntrs_scan_r2` | L2=3 | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `nist_ir6643_reflow` | L1=1 | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `nist_ir6643_vapor_pressure` | L1=1 | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `nist_jres_reflow` | L1=1, L6=1 | 1 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `nist_jres_v98n1` | L1=1, L2=1, L6=1 | 10 büyümüş, 6 küçülmüş, 1 hizası değişmiş, 1 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `plos_animal_movement_r2` | L2=1, L6=1 | 18 büyümüş, 20 küçülmüş, 0 hizası değişmiş, 7 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `ross_stats` | L1=1, L2=2, L6=4, L7=1, L8=1 | 0 büyümüş, 25 küçülmüş, 1 hizası değişmiş, 8 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `wikipedia_photosynthesis_r2` | L2=4, L7=2, L8=1 | 0 büyümüş, 6 küçülmüş, 0 hizası değişmiş, 1 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `wikipedia_printing_press_r2` | L2=1, L6=2 | 4 büyümüş, 4 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `wpa_poster` | temiz | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `arxiv_2510_03959` | temiz | 0 büyümüş, 0 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `arxiv_2605_18014` | temiz | 0 büyümüş, 3 küçülmüş, 0 hizası değişmiş, 0 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `fresh_p05_grant` | temiz | 0 büyümüş, 8 küçülmüş, 0 hizası değişmiş, 1 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
| `ross_stats_full` | temiz | 1 büyümüş, 32 küçülmüş, 3 hizası değişmiş, 15 okunamaz boyutta | toplam 0 kelime gorselin ustunde |
