"""Function words per language: what may not frame a term candidate.

Terim adayını başlatamayan/bitiremeyen işlev sözcükleri, dil başına tek yerde.

WHY THIS EXISTS: `core/terms.py` kept one short list mixing English, Turkish and German, kept short
on purpose because a long English list would have been wrong for the other languages. Measured on
the bench's 21 sources (three pages each), that list still let grammar through as "terms": `your`,
`using`, `through`, `between`, `could` on the English sources; `tarafından`, `yönelik`,
`doğrultusunda`, `içinde` on the Turkish ones; and citation debris (`https doi org`, `ncbi nlm nih
gov`) on every paper with a reference list. Lists kept per language can be as long as the grammar
needs without blocking a real word of another language (English `sea`, `era`, `men` are function
words in Spanish, Italian and Dutch).

The language is the document's when it is known; otherwise it is guessed from the text with these
same lists (the language whose function words the text uses most), and when nothing matches every
list applies.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Dil başına işlev sözcükleri / Function words per language (casefolded).
FUNCTION_WORDS: dict[str, frozenset[str]] = {
    "en": _words(
        "the a an and or nor of to in on for with by as at is are was were be been being that this"
        " these those it its from but not no if then than so such which who whom whose what when"
        " where why how each every other others also only more most any all some per shall will may"
        " must can should would could has have had having do does did doing done you your yours we"
        " our ours they them their theirs he him his she her hers i me my us itself themselves"
        " there here into onto upon over under about above below between among across through"
        " during before after since until while within without against toward towards via"
        " however thus therefore although though because whether either neither both same own"
        " very just too again further once rather used using made make makes one two three four"
        " five first second third don doesn didn isn aren wasn weren won wouldn shouldn couldn"
        " haven hasn hadn"
    ),
    "tr": _words(
        "ve bir ile için olarak bu şu o bunlar şunlar da de ki mi mı mu mü veya ya ya da her tüm"
        " bütün daha çok az en olan olup ise ancak sonra önce ayrıca hem ne diğer bazı hiç gibi"
        " kadar göre üzere dolayı karşı rağmen dair ilişkin itibaren birlikte arasında üzerinde"
        " altında içinde dışında sonucunda nedeniyle tarafından yönelik doğrultusunda ilgili"
        " kendi sayılı şekilde halinde hâlinde iki üç dört beş altı yedi sekiz dokuz on"
    ),
    "de": _words(
        "der die das den dem des ein eine einer eines einem einen und oder aber für mit von zu"
        " ist sind war waren wird werden wurde kann können muss soll auch nur nicht kein keine"
        " im in am an auf aus bei nach über unter vor zwischen durch gegen ohne um als wie wenn"
        " dass ob sich es er sie wir ihr ihre sein seine jede jeder jedes alle diese dieser dieses"
        " einem zum zur beim vom"
    ),
    "fr": _words(
        "le la les un une des du de d l et ou mais pour par avec sans sur sous dans en au aux ce"
        " ces cet cette qui que quoi dont où est sont était être avoir a ont il elle ils elles on"
        " nous vous leur leurs son sa ses se ne pas plus comme entre chaque tout tous toute toutes"
    ),
    "es": _words(
        "el la los las un una unos unas y o u pero para por con sin sobre en de del al que quien"
        " cual cuyo donde es son era fue ser estar ha han se su sus lo le les como entre cada todo"
        " todos toda todas este esta estos estas ese esa no más muy también sea sean"
    ),
    "it": _words(
        "il lo la i gli le un uno una e o ma per con senza su in di del della dei degli delle al"
        " alla ai agli alle da dal dalla che chi cui dove è sono era essere ha hanno si suo sua"
        " suoi sue come tra fra ogni tutto tutti tutta tutte questo questa non più anche"
    ),
    "pt": _words(
        "o a os as um uma uns umas e ou mas para por com sem sobre em de do da dos das no na nos"
        " nas ao aos que quem qual cujo onde é são era ser estar tem têm se seu sua seus suas"
        " como entre cada todo todos toda todas este esta não mais muito também"
    ),
    "nl": _words(
        "de het een en of maar voor met zonder op in van aan bij uit door over onder tussen naar"
        " dat die dit deze wie wat waar is zijn was waren wordt worden kan moet zal ook niet geen"
        " hij zij wij ze hun haar zijn elk elke alle als dan"
    ),
}

#: Words that make the phrase around them a clause, not a name, wherever they stand in it.
#: Çevresindeki öbeği ad değil yan cümle yapan sözcükler; öbeğin neresinde olursa olsun.
#: Measured: the Turkish Penal Code offered "yıla kadar hapis" and "kadar" itself.
NEVER_INSIDE: dict[str, frozenset[str]] = {
    "tr": _words(
        "kadar gibi göre ile için şekilde halinde hâlinde üzere dolayı tarafından içinde yönelik"
        " doğrultusunda ilişkin dair rağmen nedeniyle sonucunda arasında"
    ),
}

#: Pieces of URLs and citation identifiers, never a term in any language: a reference list offered
#: `https doi org` and `ncbi nlm nih gov` as the most frequent phrases of three bench papers.
#: URL ve künye parçaları; hiçbir dilde terim değil.
CITATION_NOISE: frozenset[str] = _words(
    "http https www doi org com gov edu net html htm isbn issn pmid pmc ncbi nlm nih pubmed arxiv"
)


def guess(words: Iterable[str]) -> str | None:
    """The language whose function words `words` (casefolded) use most, or None if none match.

    Metindeki işlev sözcüklerinden en çok eşleşen dili tahmin eder.
    """
    hits: Counter[str] = Counter()
    for word in words:
        for code, listed in FUNCTION_WORDS.items():
            if word in listed:
                hits[code] += 1
    if not hits:
        return None
    return hits.most_common(1)[0][0]


def lists_for(codes: Iterable[str]) -> tuple[frozenset[str], frozenset[str]]:
    """(edge words, never-inside words) for `codes`; every language when none of them is known.

    Verilen dillerin listeleri; hiçbiri bilinmiyorsa tüm dillerinki.
    """
    known = [code for code in (c.strip().lower() for c in codes if c) if code in FUNCTION_WORDS]
    chosen = known or list(FUNCTION_WORDS)
    edges = frozenset().union(*(FUNCTION_WORDS[code] for code in chosen))
    inside = frozenset().union(*(NEVER_INSIDE.get(code, frozenset()) for code in chosen))
    return edges | CITATION_NOISE, inside | CITATION_NOISE
