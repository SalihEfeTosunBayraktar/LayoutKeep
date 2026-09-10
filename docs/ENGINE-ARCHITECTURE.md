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
| **pdf →** | 100% · 10/10 styled | 101% · 10/10 styled | 100% · 10/10 | 101% · 10/10 | 91% · 0/10 |
| **epub →** | 100% · 1/1 img | 100% · 1/1 img · 3/3 | 100% · 1/1 img · 1/2 pages | 104% · 1/1 img | **63%** · 1/1 img |
| **docx →** | 100% · 4/2 styled | 119% · 2/2 styled · 5/4 pages | 100% · 2/2 | 110% · 2/2 · 1/4 pages | **73%** |
| **png →** | 100% · 1 img | 143% | 100% | 129% | 100% |

This table has been corrected twice since it was first published, both times because the
instrument was wrong rather than the thing it measured. What those corrections were is at the
end, under *What this measurement got wrong*, because a measurement that hides its own errata is
worth less than one that never claimed precision.

Two things to read out of it before anything else.

**Nothing fails.** Twenty pairs, no exceptions, no error dialogs. Several of them quietly hand
back a document missing its images or a third of its words. A conversion that throws is a bug
someone fixes; a conversion that succeeds and returns less than it was given is a bug nobody
reports.

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

## What this measurement got wrong

Twice, and both times the instrument rather than the subject. They are recorded here rather than
quietly amended, because the whole argument of this document rests on believing its numbers.

**The word counts.** The counter joined a document's blocks with nothing between them, so the
last word of one block and the first of the next counted as one word, while every output format
separates them with markup and counted two. That produced figures of 115%, 129%, 139% and 153%,
and an explanation of them — offered here — blaming chapter titles and navigation. It was not.
With the join fixed, those four read between 100% and 104%.

**The dropped images.** This document said `pdf_generator` drops images on the EPUB path: DocIR
held one, the PDF had none. It does not. The EPUB fixture's 1x1 PNG had `IHDD` where a PNG has
`IHDR`, so it was not a decodable image at all, and MuPDF was right to refuse to draw it. The
fixture had been that way for a long time without anyone noticing, because the reader tests only
ask whether the bytes survive the round trip, and bytes do not care whether they decode. With a
real PNG, epub→pdf carries its image: 1/1.

**The dropped images, again.** With the fixture repaired, epub→docx still read 0/1, and the
obvious conclusion - that the DOCX generator drops images where the PDF one does not - was also
wrong. The generator embeds the picture correctly; `readers/docx_reader.py` had no image
handling at all, so nothing read from a DOCX ever carried a figure regardless of target. That
part was real and is now fixed - epub→docx reads 1/1. Every number in the `img` column is only
ever as good as the reader used to check it, which is a limitation of this method and is now
stated rather than discovered again.

The moral is not that measurement is unreliable. It is that the instrument - the fixtures it
uses and the readers it counts with - is part of what is being measured, and an instrument that
has never been checked against something known-good is a source of confident numbers rather than
true ones. Three of the defects this document originally reported were the instrument, and a
fourth was real and has since been fixed. The ones that survive both are worth more for it.

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
document from DocIR alone. They are thinner, and where they are thin it is in ordinary ways:

* **`epub_generator` wrote no emphasis at all** — since fixed. DocIR held ten styled runs from
  `sample_report.pdf` (a bold title, an italic subtitle, bold headings) and the EPUB contained
  zero `<b>`, `<strong>`, `<i>` or `<em>` tags and zero `font-weight` declarations. It rendered
  the block's flattened text, which throws every span away. It renders spans now: pdf→epub went
  from 0/10 styled runs to 10/10, docx→epub from 0/2 to 2/2.
* **`docx_reader` read no images at all** — since fixed. This entry said "`docx_generator`
  drops images", measured as epub→docx 0/1. The generator was never dropping them: the DOCX it
  writes contains the media part, the drawing and the blip that references it. What could not
  see them was the reader used to count the output - `readers/docx_reader.py` had no image
  handling whatsoever, so every DOCX source lost every picture it had on the way back into
  DocIR, regardless of target. It reads them now: epub→docx went from 0/1 to 1/1.
* **An image with no geometry was embedded one EMU square** - since fixed. A reflowable source
  gives a picture a place in the flow and no box, and the DOCX generator sized the drawing from
  that empty box: present in the package, invisible on the page. It now falls back to the
  picture's own pixel size, read from its header.
* **Rendering to an image loses a third of the words** — epub→png 63%, docx→png 73%, against
  pdf→png at 91%. The words are drawn; what varies is whether OCR can read them back, which is
  the only way to check an output with no text layer. Worth understanding before that row opens.

None of this is evidence that the architecture is wrong.

## The three options that were on the table

**"Write a universal intermediate format and convert through it."** This already exists and is
called DocIR. `docs/CONTRACT.md` D1 has required it since the beginning: every reader produces
it, every writer consumes it, and readers and writers never know about each other. The
measurements confirm the intermediate is not the problem — DocIR *had* the bold runs the EPUB
generator dropped, and *has* the image the DOCX generator still drops. Building a second
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
