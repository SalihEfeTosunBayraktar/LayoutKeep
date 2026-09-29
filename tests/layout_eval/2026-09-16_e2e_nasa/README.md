# Universality check: NASA report, scanned pages, model path - 2026-09-16

A different document type from the textbook every fix was found on: a 1956 NACA report, tinted
scan, cover page and figure pages. Pages 1, 3, 11-16, 19, 20 (the ones that read as scanned; the
others carry a hidden OCR text layer and take the born-digital path, where the model is not used).
Each sheet: original | model output. EN->TR with gemma-4-e4b.

Found (page 1, the cover):

- **Visible patches on tinted paper.** The painted-out area is filled with each block's detected
  background, which on this yellowed scan comes out darker than the paper around it, so every
  translated block sits on a rectangle. Not seen on the textbook (white paper).
- **Centred title lines drawn left-aligned and small**; the cover's typographic design is lost.
- Translation quality ("RAPORTO", "ULUSLARAR ADILIYE KOMITESI") is the model's, not layout's.

Figure pages keep their drawings; their few text blocks translate in place.
