# 7. Honest limits, open work, and lessons

The most valuable part of an engineering document is the part that writes down what does not work.
This chapter is not polished.

## 7.1 Today's limits (measured)

**Bibliographies and numbered headings.** On the book run L2 = 2: bibliography rows and some numbered
headings stay in the source language. They are *flagged* (not silent) but not translated — because
those rows are treated as "not translatable": most consist of an author name, a journal name, a year
and a page range, and translating them goes against academic citation convention. The decision is
deliberate, but the user sometimes reads it as "missing translation"; it needs explaining better in
the interface.

**Blocks below the readability floor (D1).** Long translations get shrunk; on the book 801 blocks sit
below the floor. `--fit-mode reflow` removes much of that class (D1 52 → 0 on the NIST journal) but
can draw text over text in fixed layouts (L7 0 → 1 on the IRS form). So it is **off** by default: a
proven loss outranks a measured gain.

**Scanned pages depend on OCR quality.** Low-confidence blocks are flagged, not corrected. Clean
300 dpi scans are reliable; skewed, stained or low-resolution ones are not. The NASA scan and NIST's
scanned vapour-pressure report test that path.

**Number strips.** Runs of bare numbers spread across a table heading (for example
`11 34 56 79 101 124`) can collapse into one flush-left block: the numbers survive but their
**arrangement** is lost. This happens where the table structure reduces to plain text; the fix goes
through widening table detection.

**Right-to-left scripts are not implemented.** The schema carries a `direction` field (D4); the
writer does not use it. An Arabic or Hebrew document is not translated correctly today — and the
interface does not say so, because those languages do not appear in the supported list.

**Quality is the model's ability.** The pipeline prevents loss; it does not produce fluency. Text
from a small local model is weaker than a cloud model's; the glossary and the memory narrow that gap
but do not remove it.

**The review queue can be read, not edited.** Flags carry their reason, but the user cannot correct a
translation inside the application and write it out again. This is the highest-effort item on the
roadmap.

## 7.2 The roadmap (in order of impact / effort)

Items 1, 3 and 7 of the earlier roadmap have since **shipped** — the bilingual PDF, term candidates
from the document, and the setting presets. What is left, with today's state:

1. **The overlap ladder** (shrink → tighten the leading → push down). The leading step alone was
   built, measured and **reverted** on 2026-09-20: with the pass's own substituted font it rescued no
   block, and the written-page A/B was identical in both arms. The measurement also showed where the
   real work is: most flagged blocks are short of **box**, not of lines (`room_below` can crush a
   measured box to six points). Effort: medium-high. Measure: D1 and the "unreadable size" count,
   read together with L7.
2. **A small editor** — correcting flagged blocks inside the application and writing the document
   out again. Effort: high.
3. **Cross-page context** — adding the previous chunk's last blocks to the request at a chunk
   boundary; expected to bring L2 and D2 down.
4. **A visual page picker for the range** — choosing a range from small previews.
5. **Reading the current limits into the interface** — the D1/box distinction is now on the
   completion screen (0.9.7); the bibliography note is not.

## 7.3 Lessons

**1. Measurement comes before the feature.** The claim of "lossless" is only meaningful if it can be
counted. In this project every feature arrived with a *number*: the L/D table, `type_drift`, the
four-panel visual comparison.

**2. A wrong measurement is worse than no measurement.** Half of L10, all of "obviously bigger type",
and part of the alignment flags were **measurement bugs** (section 3.3). All three were found only by
auditing the measuring tool itself. The rule: when a number looks doubtful, look at the tool first.

**3. An unproven fix is not kept — and neither is an unproven rewrite.** The block-widening attempt
was refuted by measurement (12 → 12) and reverted. The V2 rewrite plan would have thrown away 1,000+
tests for one gap; instead the gap was added to the existing engine.

**4. The same capability needs two doors: the command line and the interface.** We made the same
mistake twice: the glossary and the memory existed in the CLI and not in the interface (4.6);
parallelism existed in the CLI and not in the application (4.8). The lesson: when a capability is
added, **both doors** must be wired, or for the user it does not exist.

**5. A setting you cannot see is a setting that does not work.** `timeout.first_batch_s` sat in the
settings screen and changed nothing (4.11). There is now a test that says "every declared setting
must be read".

**6. Defaults must be conservative.** Parallelism came down from 7 to 2: an aggressive default spoils
the user's first experience (and quality on small models). The user can raise it; they should not have
to think of lowering it.

**7. User feedback is the best test set.** Most cases in this document start with a user's sentence:
*"even with 7 slots it sends 1"*, *"why did it give the whole book"*, *"obviously bigger type"*,
*"when I close the pill I cannot get it back."* None of them were the kind the 1,256 tests catch —
they all came out in *use*. The test suite holds regressions down; use finds the new bug.

**8. Copyright and privacy are part of the architecture.** Which content gets published
(`NOT_PUBLISHABLE`), the document not leaving the machine (local-first), and the repository being
cleaned up (36 MB → 12 MB) were not features added later; they should have been part of the design
from the start, and now are.
