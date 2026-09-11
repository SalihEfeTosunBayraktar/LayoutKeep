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
| **epub →** | 100% · 1/1 img | 100% · 1/1 img · 3/3 | 100% · 1/1 img · 1/2 pages | 104% · 1/1 img · 2/2 pages | 101% · 1/1 img |
| **docx →** | 100% · 4/2 styled | 119% · 2/2 styled · 5/4 pages | 100% · 2/2 | 110% · 2/2 · 4/4 pages | 100% |
| **png →** | 100% · 1 img | 143% | 100% | 129% | 100% |

This table has been corrected five times since it was first published - three times because the
instrument was wrong, twice because a real defect it correctly found got fixed. What those
corrections were is at the end, under *What this measurement got wrong* and *Why the diagonal is
clean*, because a measurement that hides its own errata is worth less than one that never claimed
precision.

Two things to read out of it before anything else, and a third that only became true after five
rounds of checking the instrument.

**Nothing fails.** Twenty pairs, no exceptions, no error dialogs. A conversion that throws is a
bug someone fixes; a conversion that succeeds and returns less than it was given is a bug nobody
reports, which is the entire reason this table exists.

**The diagonal is clean.** Every same-format pair keeps everything it was given: pdf→pdf 100%
with all ten styled runs, epub→epub with its image and all three styled runs, docx→docx, png→png.
Nothing surprising there - see *Why the diagonal is clean* for the reason.

**Almost everything else now reads at or near 100% too.** That was not true of the first version
of this table, which is the whole reason the errata sections below exist. Of the sixteen
cross-format pairs, one is genuinely short - pdf→png at 91%, and even that is not lost content
(see below) - and the rest sit at 100% or a little over, the over explained in the next section.
This document's original thesis was that cross-format conversions lose real content; four of the
five defects it reported turned out to be its own measuring tool. What is left is thin enough
that locking every cross-format pair on fidelity grounds alone is no longer the finding it once
was - see *What is being done now*.

**pdf→png's 91% is not missing content.** Its character count matches the source exactly (1091
of 1091); only the word count is short, because RapidOCR occasionally reads two adjacent short
spans as one recognized run without the space between them that was there in the source. Every
character survives; some of the whitespace that separates them into words does not. Left as a
known texture of OCR word-counting rather than investigated further, since the character count
already answers the question this table exists to ask.

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

Four times, and every time the instrument rather than the subject. They are recorded here rather
than quietly amended, because the whole argument of this document rests on believing its numbers.

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

**The collapsed pages.** This document said a paged document collapses to one HTML flow - docx→html
measured 1 page out of 4. `html_writer.py` never did that: it wraps every DocIR page in its own
`<section class="page-container">`, and all four were there in the file. The counter reading the
output hardcoded `pages=1` regardless of what it found, a leftover from before this measurement
checked pages at all. Counting the actual `<section>` tags gives docx→html 4/4, epub→html 2/2.

The moral is not that measurement is unreliable. It is that the instrument - the fixtures it
builds and the readers it counts with - is part of what is being measured, and an instrument that
has never been checked against something known-good is a source of confident numbers rather than
true ones. Four of the defects this document originally reported were the instrument, and one -
the OCR detector losing sparse pages (see *Why the diagonal is clean*) - was real and has since
been fixed. What survives both is worth more for it: essentially nothing does. Every number in
this table now reads at or near 100%, or is explained.

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
* **Rendering to an image lost a third of the words** - since fixed, and not where it looked, and
  the fix itself cost a second round when a real document found what the fixture had not.
  epub→png read 63%, docx→png 73%, against pdf→png at 91%; the shape of it (single-page pdf→png
  fine, multi-page epub/docx→png badly wrong) pointed at the writer, but the words were on every
  page, drawn correctly. A DOCX's header, footer and footnotes become their own DocIR pages with
  no geometry, and `pdf_generator.py`'s flowing layout gives every page the same A4 sheet to keep
  a document looking like one - reasonable for a PDF, but rasterized to PNG it puts one 20px line
  of text alone on a 1240x1755 canvas, and RapidOCR's small/fast detector found nothing on a page
  that sparse. `RapidOcrEngine.recognize` was given a fix that crops to the page's own content,
  padded, before handing it to the detector - the same model then reads the same line at 98%
  confidence. Measured on the format matrix's small fixture, that fix looked complete: epub→png
  and docx→png both read 100%+.

  It was not complete. Asked to build a realistic multi-page document and check the same
  conversion by hand rather than trust the fixture, a 450-word DOCX report turned up a second
  bug the crop had introduced: on a page whose body text filled 82% of it, cropping to that
  content - still the exact bounds of the content, padded, not touching a glyph - made the
  detector drop a whole paragraph it read correctly at native, uncropped size. The crop was safe
  by the letter of what it removed and still cost real recall on a page it was never meant to
  touch. `_content_crop` now declines to crop once the content already covers roughly half the
  page or more - the actual sparse pages this exists for measured 2-6%, comfortably clear of the
  50% gate, so the fix for the original bug is untouched and the page shape that regressed it is
  now left at native resolution. The 450-word document reads at 100.2% now (one harmless "+/-"
  tokenisation split accounts for the rounding), verified by hand, not by re-running the fixture -
  the fixture's own pages are too small to have shown either bug at realistic scale.

None of this is evidence that the architecture is wrong.

## The three options that were on the table

**"Write a universal intermediate format and convert through it."** This already exists and is
called DocIR. `docs/CONTRACT.md` D1 has required it since the beginning: every reader produces
it, every writer consumes it, and readers and writers never know about each other. The
measurements confirm the intermediate is not the problem — DocIR *had* the bold runs the EPUB
generator dropped and *had* the image the DOCX reader could not see, both now carried through.
Building a second intermediate would not have carried them any better than the first one already
did; the gap was always downstream of it.

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
offering them misrepresents their quality.

**Most of that lock was earned by this document's own mistakes, not by the code.** It went into
its first draft claiming widespread content loss across cross-format conversions; four of five
defects it reported were the measuring tool - a broken test fixture, two missing readers, a
hardcoded page count - and the fifth, a real OCR detector limitation, is fixed. What remains
below 100% is pdf→png's 91%, which is a whitespace-counting quirk with the character count intact,
not lost content. Whether that is enough evidence to open any of these pairs is a product
decision, not a measurement one, and is left to whoever owns that call rather than decided here.
What this document still stands behind is the *architecture* finding: the generators were thinner
than the writers, two of them have since been made as serious, and the format matrix is what to
run before trusting the next one.

The matrix is a tool, not a document: rerun it after any change to a reader or a writer.

    .venv/Scripts/python.exe tools/audit/format_matrix.py docs/samples/format_matrix.json
