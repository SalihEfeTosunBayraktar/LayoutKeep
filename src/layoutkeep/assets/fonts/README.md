# Bundled fonts

These fonts are shipped with LayoutKeep because **a stock Windows install has none of them**,
and without them the metric-compatible substitution in `fitting/fontmatch.py` degrades to
whatever happens to be on the machine. That was measured, not assumed.

They matter because PDF embedded fonts are usually subsetted: the Turkish `ğ ş İ ı`, the German
`ß` and the Polish `ł` are frequently absent from the original font, so the original simply
cannot render the translation. Every font here was verified to carry full Turkish and European
Latin coverage before being added.

## What is here and why

| Font | Substitutes for | Licence |
|---|---|---|
| Tinos | Times New Roman, Georgia, generic serif | OFL 1.1 |
| Arimo | Arial, Helvetica, generic sans | OFL 1.1 |
| Cousine | Courier New, generic monospace | OFL 1.1 |
| Caladea | Cambria | OFL 1.1 |
| Carlito | Calibri | OFL 1.1 |
| Noto Sans / Noto Serif | Last-resort fallback for unknown families | OFL 1.1 |

Tinos, Arimo and Cousine are metrically compatible with the Microsoft fonts they replace: same
advance widths, so a line that fit before still fits after substitution. That is the whole reason
they were chosen over prettier alternatives.

Every static family ships all four faces - regular, bold, italic and bold italic. That is not
padding: `pdf_writer` verifies that an embedded font really carries the weight and slant it was
resolved for, and drops back to base-14 when it does not. Cousine, Caladea and Carlito originally
shipped no bold-italic face, so every bold-italic run in such a document lost its metrics without
any visible error. Arimo needs only two files because its variable axis is pinned at embed time.

## Licensing

All seven families are under the SIL Open Font License 1.1, which permits redistribution as part
of a larger work and is compatible with this project's AGPL-3.0.

Licence texts are in `licenses/`. The OFL requires them to be distributed with the fonts, so they
must be included in every build — see `packaging/layoutkeep.spec`.

One note for anyone auditing this: the `ofl/tinos` directory in the `google/fonts` repository
ships no licence file, which looks alarming. It is an upstream packaging omission, not a
licensing question — both `METADATA.pb` (`license: "OFL"`) and the font's own name table
(nameID 13) state OFL 1.1. The text in `licenses/tinos-OFL.txt` came from the upstream
`googlefonts/tinos` project.

## Size

About 12 MB for 20 files. Subsetting to Latin + Latin Extended-A would cut this further, but at
10 MB against a ~170 MB Qt application it is not worth the added build complexity.

## Updating

Sources are `github.com/google/fonts` (`ofl/<family>/`) and, for the Tinos licence,
`github.com/googlefonts/tinos`. If you replace any file, re-run the glyph coverage check before
committing — a font without `ğ ş İ ı` is worse than useless here, because the failure is silent.
