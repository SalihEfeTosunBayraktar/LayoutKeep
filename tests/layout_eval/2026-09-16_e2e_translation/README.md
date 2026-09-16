# End-to-end translation, 10 book pages - 2026-09-16

The judge is the translated page next to the source, not the reader metrics. Each `page_*.jpg`
shows four panels: **original | before** (the 524-page run made before this branch) **| no_model**
(this branch, XY-cut only) **| with_model** (this branch, `--layout-detector`).

Pages: 22, 28, 54, 61, 101, 121, 251, 301, 401, 451 of `computer-systems-Architecture.pdf`,
translated EN->TR with gemma-4-e4b on LM Studio.

    python tools/audit/translate_book.py sample10.pdf --out on.tr.pdf --model google/gemma-4-e4b \
        --workers 4 --pages-per-chunk 1 --layout-detector
    python tools/audit/side_by_side.py sample10.pdf before=... no_model=... with_model=... --out DIR

## Round 1 - what the images showed

`translation_completeness.py` on the same outputs:

| | prose still in English | words off the page |
|---|---|---|
| before | 6 of 82 (7%) | 0 |
| no_model | 4 of 82 (5%) | 0 |
| with_model | 1 of 82 (1%) | 0 |

Blocks reported still overflowing after fitting: no_model 60, with_model 48.

**Better with the model, seen on the page:**

- p54 (exercises): the running header stays one line at body size (before/no_model: two lines,
  oversized); every exercise its own translated block; no English left ("Ah at tr than the
  input..." remains in before and no_model).
- p301: every exercise item translated in place; before/no_model draw a translation over the
  untouched source line "8-2 when the following 14-bit control words are applied" and leave
  "to infix notation ..." in English.
- p22: the "small circle" paragraph is translated; before and no_model leave all of it in
  English.
- p61 and p28: figure labels stay as scanned instead of being re-typeset (`D{2`, `D_3`); p61's
  first paragraph is translated (no_model leaves it English).
- p121: the paragraph under table 4-5 is clean; before breaks it into garbage ("eat x l a o r ro").

**Defects found, and what was done:**

1. **Source line left visible under the translation** (p28 "ing term it represents is
   A'BC'D.", p451 "ferred to the operating system ...") - in no_model and with_model, not in
   before. Cause: `join_hyphenation` folded the whole line after a hyphen into the line above
   and deleted it, while the surviving line kept a one-line box; the block box stopped a line
   short and the writer never painted that line out. It also affects born-digital PDFs (shared
   helper). **Fixed**: only the word fragment moves; tests in `test_image_reader_hyphenation.py`.
2. **Table cells merged into one block** (p451 function table: "Veri yolu durumu Yuksek
   empedansli Yuksek empedansli ..."). Cause: lines the model put in a table or picture were
   grouped among themselves, where the table's column became the "body column". **Fixed**: one
   block per line inside picture/table regions; `test_table_cells_stay_separate_blocks`.
3. **Translated text visibly smaller than the source** (p22, p451, p61). Cause: the size ceiling
   was the median over every word box, and half of all word boxes are above their median by
   definition (p451 paragraphs 6.60pt -> 6.32pt). **Fixed**: ceiling is the median of each
   block's own median; `test_the_ceiling_does_not_shrink_ordinary_body_text`.
4. **Top half of a kept formula painted out** (p54 `b. AC' + B'D + ...`). Cause: the line above
   was translated, OCR boxes of adjacent lines overlap ~1pt and the cover adds 1.5pt. **Fixed**:
   the cover gives way to neighbouring lines that stay as scanned, but not to one inside its own
   box; `test_pdf_writer_scanned_neighbours.py`.

**Seen, not yet addressed:**

- p61: translated paragraph runs into the next block ("olusturulabilir." over "Sekil 2-3") -
  fitting lets a long translation overlap instead of shrinking further.
- p301: exercise 8-9's text came back in English in with_model; some list lines appear drawn
  over their scanned glyphs.
- p54: OCR garbage in exercises 1-14 and 1-19 ("Fuls nu a uo s sd--s ...") in every version -
  recognition, not layout.
- p121 table 4-6: column headers merged ("Boolean fonksiyonMikro Islem") in every version.

Round 2 (after the fixes) is in `round2/`.

## Rounds 3 and 4 (model path only from here)

`no_model_final` in `round3_milestone/` and `round4/` is the last no-model output (round 2's),
kept as the milestone; the no-model path is not developed further.

| | prose still English | blocks overflowing after fitting |
|---|---|---|
| round 1, model | 1 of 82 | 48 |
| round 3, model | 2 of 82 | 46 |
| round 4, model | **0 of 82** | **34** |

Round 3 found: labels inside a circuit diagram (p61) translated and re-typeset over its wires
("kod cozucu" between the lines, "D{2}"). Fixed: text inside a `picture` region keeps role
FIGURE and stays as scanned; table cells are still translated. Round 1 had looked right only by
accident (the labels happened to group into a wordless block).

Also found across rounds: a DIFFERENT paragraph left in English each run (p61, then p121) - the
model handing the source back intermittently. Fixed: `retry_untranslated` also resends echoed
replies once; an echo that echoes again keeps its first reply and stays flagged.

Round 4, still seen:

- p61 caption: the translation of "Figure 2-3 A 3 x 8 decoder ..." came back with sentences of
  the neighbouring paragraph appended (context bleeding into the reply), and was shrunk into the
  caption box. Round 3's caption was correct - model behaviour, intermittent.
- p61 heading "Decoder Expansion" left in English: two words, below the echo check's minimum,
  which exists because names and codes legitimately translate to themselves.
