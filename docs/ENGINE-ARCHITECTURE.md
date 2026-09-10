# What the conversion engine is, what it is not, and what to build next

The user interface offers twenty source-to-target pairs. This is a measurement of all twenty,
followed by what the numbers say about the three ways forward that were on the table.

Everything here comes from [`tools/audit/format_matrix.py`](../tools/audit/format_matrix.py),
which runs each pair on a document built to carry text, an image and bold/italic runs, translates
it with the identity function — every segment comes back as itself, so a word count that moves is
a word that was lost or invented rather than a longer language — and counts what came out against
what the reader put in. The raw output is `docs/samples/format_matrix.json`.

## The measurement

`text` is words out over words in. `img`, `pages` and `styled` are out/in counts; `styled` is
runs marked bold or italic.

| | → pdf | → epub | → docx | → html | → png |
|---|---|---|---|---|---|
| **pdf →** | 100% · 10/10 styled | 101% · **0/10 styled** | 100% · 10/10 | 101% · 10/10 | 91% · 0/10 |
| **epub →** | 101% · **0/1 img** | 100% · 1/1 img · 3/3 | 100% · **0/1 img** · 1/2 pages | 104% · 1/1 img | **66%** · 1/1 img |
| **docx →** | 100% · 4/2 styled | 119% · **0/2 styled** | 100% · 2/2 | 110% · 2/2 · 1/4 pages | **73%** |
| **png →** | 100% · 1 img | 143% | 100% | 129% | 100% |

Two things to read out of it before anything else.

**Nothing fails.** Twenty pairs, no exceptions, no error dialogs. Five of them quietly hand back
a document missing its images, its emphasis, or a third of its words. A conversion that throws is
a bug someone fixes; a conversion that succeeds and returns less than it was given is a bug
nobody reports.

**The diagonal is clean and everything off it is not.** Every same-format pair keeps what it was
given: pdf→pdf 100% with all ten styled runs, epub→epub with its image and all three styled runs,
docx→docx, png→png. Every cross-format pair loses something. That is not a coincidence, and it is
the whole finding.

### Where the percentages above 100 come from

An earlier version of this table showed 115%, 129%, 139% and 153% in the HTML and EPUB columns,
and the explanation offered for them here was wrong. It was not chapter titles and navigation. It
was this measurement's own counter: it joined block text with nothing between blocks, so the last
word of one block and the first word of the next were counted as a single word, while the output
formats separate them with markup and count two. Fixing the join moved those four numbers to
between 100% and 104%.

What is left is small and honest: `png→epub` at 143% is ten words against seven, on a fixture too
small for a ratio to mean anything, and `docx→epub` at 119% is of the same kind. They are left in
rather than tidied away — a table that shows only the numbers supporting its argument is not a
measurement. The lesson is the one this project keeps relearning: check the instrument before
believing what it says about the thing.

## Why the diagonal is clean

There are two families of writers in `writers/`, and `converter.py` picks between them by asking
one question: is the target the same format as the source?

    source .pdf  → target .pdf   → pdf_writer.py      edits the original file
    source .epub → target .pdf   → pdf_generator.py   builds a new file from DocIR

The first family — `pdf_writer`, `epub_writer`, `docx_writer` — opens the **source file** and
edits it in place: the original's own fonts, its vector art, its stylesheet, its page geometry
all stay because they are never rebuilt. Only the text is replaced. Years of the work in this
project have gone into that path, and the diagonal shows it.

The second family — `pdf_generator`, `epub_generator`, `docx_generator`, `html_writer` — builds a
document from DocIR alone. They are thin. Measured, verified, reproducible:

* **`epub_generator` writes no emphasis at all.** DocIR holds ten styled runs from
  `sample_report.pdf` — a bold title, an italic subtitle, bold headings. The EPUB it produces
  contains zero `<b>`, `<strong>`, `<i>` or `<em>` tags and zero `font-weight` or `font-style`
  declarations. The information reached the writer and the writer dropped it.
* **`pdf_generator` drops images on the EPUB path.** DocIR holds one image with `order=5`. The
  PDF it produces contains zero images and zero drawings. Same for the DOCX path.

Both are ordinary defects in ordinary code. Neither is evidence that the architecture is wrong.

## The three options that were on the table

**"Write a universal intermediate format and convert through it."** This already exists and is
called DocIR. `docs/CONTRACT.md` D1 has required it since the beginning: every reader produces
it, every writer consumes it, and readers and writers never know about each other. The
measurements confirm the intermediate is not the problem — DocIR *had* the image the PDF
generator dropped, and *had* the bold runs the EPUB generator dropped. Building a second
intermediate would not have carried them any better; the writers would still be thin.

**"Separate conversion engines for every combination."** Sixteen cross-format pairs, each its own
engine. Every fix to table detection or literal protection would then need doing sixteen times,
and the diagonal — the part that works — would gain nothing. This is the option the current
design already rejected, and the measurement gives no reason to revisit it.

**"Segment the engine in detail."** This is the real answer, and the segmentation the measurement
points at is not by format pair. It is the one already half-built: *editing* an existing file and
*generating* a new one are different jobs with different fidelity ceilings, and the second one is
where the work is.

## What is actually missing

DocIR is shaped for a page: `Document → pages → blocks → lines → spans`, with a bounding box on
everything. That fits a PDF exactly, an image well enough, and a reflowable book badly. It has
been stretched twice already — `ImageRef.order` exists because an EPUB image has no geometry to
be placed by, only a position in the flow. The stretch marks are the honest signal of what to
build:

1. **The generators need to be as serious as the writers.** Not a new architecture: styling,
   images, headings, lists and tables carried through to each output format, with the format
   matrix above as the regression test. This is most of the work and all of the value.
2. **Reflow is a first-class output mode, not a fallback.** A PDF made from an EPUB cannot
   preserve a geometry the source never had. It should be laid out well rather than laid out
   apologetically, and it should say so.
3. **An image target has no text layer, and that is a property, not a defect.** `png→pdf`
   measured 100% only because the check renders the page and reads it with OCR. The words are
   there and legible; they cannot be searched or selected. The interface should say that before
   the conversion, not leave the user to discover it.

## What is being done now

Only **PDF → PDF** is enabled. The other targets stay visible, with a lock and a plain sentence
saying what is not ready, because hiding them would misrepresent the project's scope while
offering them misrepresents their quality. They come back one at a time, each when the row of
this table that covers it reads the way the diagonal does.

The matrix is a tool, not a document: rerun it after any change to a reader or a writer.

    .venv/Scripts/python.exe tools/audit/format_matrix.py docs/samples/format_matrix.json
