"""Is a reply a translation, or the source handed back?

One definition, used wherever a reply is accepted: the retry pass (`providers/retry.py`), the
passthrough report (`providers/passthrough.py`), the fitting pass (`fitting/fit.py`) and the
lossless audit. It lived in two places with two meanings, and the gap between them is how a
paragraph on book page 61 stayed English through every safeguard: fitting compared a reply with
the source *including* its inline style markers, the English reply had none, so "not equal" -
and the English was accepted.

Pure text, no DocIR, so both the provider and the fitting layer can use it.
"""

from __future__ import annotations

import re
from collections import Counter

_MARKER = re.compile(r"</?\d+>")
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

#: Share of a reply's words that also appear in its source, at or above which the reply is the
#: source rather than a translation of it. A translation keeps names, acronyms and technical
#: terms and changes the rest; a majority of shared words means the rest did not change either.
#: Language-independent: it compares the two texts, not a word list.
COPY_SHARE = 0.5

#: Fewer distinct words than this and the share is too coarse to mean anything.
COPY_MIN_WORDS = 4


def normalised(text: str) -> str:
    """Markers removed, whitespace collapsed, case folded."""
    return " ".join(_MARKER.sub("", text).split()).casefold()


def content_words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(_MARKER.sub("", text))}


#: Text a translation keeps as it is, whatever the language: anything in quotation marks (a
#: program's output, a title) and addresses (URLs, domains, paths, e-mail).
_QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"|‘[^’]*’")
_SPACED_SLASH = re.compile(r"\s*/\s*")
_SPACED_COLON = re.compile(r"\s*:/+")
_SPACED_DOT = re.compile(r"(?<=\w)\.\s+(?=[a-z0-9])")
_ADDRESS_HINTS = ("/", "@", "www.", ".com", ".org", ".net", ".gov", ".edu", ".py", ".htm")


def ordinary_words(text: str) -> set[str]:
    """Words a translation is expected to change: lower-case, outside quotes and addresses.

    Names, brands and acronyms are capitalised and legitimately survive translation - an author
    list or "Planet eBook.com" came back unchanged and correct, and was taken for untranslated
    text by a check that counted every word.
    """
    text = _QUOTED.sub(" ", _MARKER.sub("", text))
    # Text extraction spaces addresses out ("https: // thinkpython. com/ code/"); put them back
    # together so they are recognised as one address rather than as ordinary words. A dot
    # followed by a lower-case letter is not the end of a sentence.
    text = _SPACED_SLASH.sub("/", text)
    text = _SPACED_COLON.sub("://", text)
    text = _SPACED_DOT.sub(".", text)
    kept = [
        token for token in text.split()
        if not any(hint in token.casefold() for hint in _ADDRESS_HINTS)
    ]
    return {w for w in _WORD.findall(" ".join(kept)) if w.islower()}


def is_identical(source: str, reply: str) -> bool:
    return bool(reply) and normalised(reply) == normalised(source)


def is_copy(source: str, reply: str) -> bool:
    """The reply is the source, verbatim or lightly edited - still in the source language.

    Judged on ordinary words (see `ordinary_words`): when most of the reply's ordinary words are
    also the source's, the words a translation must change did not change. Beyond identity this
    catches book page 251, which came back in English with its recognition noise corrected
    ("co s n thn" -> "communicate with"). A reply with too few ordinary words to judge - a name,
    a label, a code - is not called a copy here; `is_identical` still reports that it came back
    unchanged, for a caller that wants to ask again.
    """
    if not reply:
        return False
    words = ordinary_words(reply)
    if len(words) < COPY_MIN_WORDS:
        return False
    if is_identical(source, reply):
        return True
    return len(words & ordinary_words(source)) / len(words) > COPY_SHARE


_DIGITS = re.compile(r"\d+")


#: Number words, per language, so a reply that writes a value out is not read as having lost it.
#: Every held-out document had at least one: the 1907 cookbook's "five medium onions", the IRS
#: instructions' thresholds, an arXiv paper's "one hundred". A checker that only counts digits
#: reports a loss that never happened, and the report costs more than a wrong count: the retry it
#: triggers re-asks a number-heavy block, and on NIST's glossary the retry is what dropped the
#: placeholder for "(1)" six times out of six.
#:
#: The words are the language's own units, teens, tens, hundred and thousand; a run of them is
#: folded to the value it names ("on iki" -> 12, "two thousand five hundred" -> 2500). Words
#: outside a run are no evidence of anything and end it, which is what keeps "bir" as an article
#: from looking like a "1" the reply never claimed to have.
#:
#: Zero counts as a number word: "0" came back as "sifir" on Think Python, and that is not a loss.
_NUMBER_WORDS: dict[str, dict[str, int]] = {
    "tr": {
        "sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7,
        "sekiz": 8, "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50,
        "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90, "yüz": 100, "bin": 1000,
    },
    "en": {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
    },
    "de": {
        "null": 0, "eins": 1, "ein": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
        "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12,
        "zwanzig": 20, "dreißig": 30, "vierzig": 40, "fünfzig": 50, "sechzig": 60,
        "siebzig": 70, "achtzig": 80, "neunzig": 90, "hundert": 100, "tausend": 1000,
        # German fuses the multiplier into the word ("zweitausend" for 2000) where English and
        # French keep it separate ("two thousand", "deux mille"): without these, a page count or a
        # year written the fused way was invisible to the checker and a lost number went unreported.
        "einhundert": 100, "eintausend": 1000, "zweihundert": 200, "dreihundert": 300,
        "vierhundert": 400, "fünfhundert": 500, "sechshundert": 600, "siebenhundert": 700,
        "achthundert": 800, "neunhundert": 900, "zweitausend": 2000, "dreitausend": 3000,
        "viertausend": 4000, "fünftausend": 5000, "zehntausend": 10000, "hunderttausend": 100000,
    },
    "fr": {
        "zéro": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
        "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13,
        "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40,
        "cinquante": 50, "soixante": 60, "cent": 100, "mille": 1000,
    },
    "es": {
        "cero": 0, "uno": 1, "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
        "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
        "trece": 13, "catorce": 14, "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40,
        "cincuenta": 50, "sesenta": 60, "cien": 100, "ciento": 100, "mil": 1000,
    },
}

#: Ordinals the target language writes as words instead of a digit with a suffix. IRS Publication
#: 505's "by the 1st day of the 3rd month" comes back as "ayın ... günü" or "üçüncü ayın", and the
#: "1st" no longer reads as a digit - reported as a lost number, three times over, on a document
#: whose numbers are the content.
#:
#: Only the target's own ordinal for the same value counts, and only for values where the word is
#: unambiguous. Turkish "ilk" is left out on purpose: it means "first" and it also means "initial",
#: and counting it would hide a digit that really went missing.
_ORDINAL_WORDS: dict[str, dict[str, int]] = {
    "tr": {
        "birinci": 1, "ikinci": 2, "üçüncü": 3, "dördüncü": 4, "beşinci": 5, "altıncı": 6,
        "yedinci": 7, "sekizinci": 8, "dokuzuncu": 9, "onuncu": 10,
    },
    "en": {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
        "eighth": 8, "ninth": 9, "tenth": 10,
    },
    "de": {
        "erste": 1, "erstes": 1, "ersten": 1, "zweite": 2, "dritte": 3, "vierte": 4, "fünfte": 5,
        "sechste": 6, "siebte": 7, "achte": 8, "neunte": 9, "zehnte": 10,
    },
    "fr": {
        "premier": 1, "première": 1, "deuxième": 2, "troisième": 3, "quatrième": 4, "cinquième": 5,
        "sixième": 6, "septième": 7, "huitième": 8, "neuvième": 9, "dixième": 10,
    },
    "es": {
        "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercero": 3, "tercera": 3,
        "cuarto": 4, "quinto": 5, "sexto": 6, "séptimo": 7, "octavo": 8, "noveno": 9, "décimo": 10,
    },
}

#: A fraction the target writes as one glyph. "1/2" comes back as "½", and the checker that counts
#: digits then reports the 1 and the 2 as lost on a translation that is exact. Both sides are
#: expanded, so a source that uses the glyph and a reply that spells it out also match.
_VULGAR_FRACTIONS: dict[str, str] = {
    "½": "12", "⅓": "13", "⅔": "23", "¼": "14", "¾": "34", "⅕": "15", "⅖": "25", "⅗": "35",
    "⅘": "45", "⅙": "16", "⅚": "56", "⅛": "18", "⅜": "38", "⅝": "58", "⅞": "78",
}


def _digit_groups(text: str) -> Counter[str]:
    """Every number a piece of text states, as the digit groups it would be written with."""
    stripped = _MARKER.sub("", text)
    found = Counter(_DIGITS.findall(stripped))
    for glyph, digits in _VULGAR_FRACTIONS.items():
        count = stripped.count(glyph)
        if count:
            for digit in digits:
                found[digit] += count
    return found

_LETTER_RUN = re.compile(r"[^\W\d_]+", re.UNICODE)


def spelled_numbers(text: str, target_lang: str) -> Counter[str]:
    """The values a reply writes out in words, counted as the digit groups the source would use.

    "on iki" -> {"12": 1}, so a source "12" is found present, and "üçüncü" -> {"3": 1} for a source
    "3rd". A language with no number words here contributes nothing rather than guessing.
    """
    language = target_lang.split("-")[0].casefold() if target_lang else ""
    words = {**_NUMBER_WORDS.get(language, {}), **_ORDINAL_WORDS.get(language, {})}
    if not words:
        return Counter()
    found: Counter[str] = Counter()
    total = 0
    current = 0
    seen = False

    def flush() -> None:
        nonlocal total, current, seen
        if seen:
            found[str(total + current)] += 1
        total = current = 0
        seen = False

    for token in _LETTER_RUN.findall(_MARKER.sub("", text).casefold()):
        value = words.get(token)
        if value is None:
            flush()
            continue
        seen = True
        if value == 100:
            current = (current or 1) * 100
        elif value == 1000:
            total += (current or 1) * 1000
            current = 0
        else:
            current += value
    flush()
    return found


#: A number grouped in thousands, with either separator: 3.657, 12,500, 1.234.567. A decimal ("3.14")
#: or a section number ("5.2.1") has no three-digit group and is left alone.
_THOUSANDS = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,]\d{3})+(?![.,]?\d)")


def _joined_thousands(text: str) -> str:
    """The text with thousands separators dropped: the languages disagree on the separator, and
    Turkish writes a law's number as 3.657 where English writes 3657 or 3,657."""
    return _THOUSANDS.sub(lambda match: re.sub(r"[.,]", "", match.group(0)), text)


def drops_numbers(source: str, reply: str, target_lang: str = "") -> bool:
    """True when a number in the source is missing from the reply.

    A section number, a page reference or a value is content, and the model can lose one without
    anything else looking wrong - NIST's contents came back as "Program Politikasinin Temel
    Bilesenleri .... 27" for "5.2.1 Basic Components of Program Policy .... 27". Compared as digit
    groups, so a decimal the target language writes with a comma ("3,14" for "3.14") still matches,
    a fraction it writes as one glyph ("½" for "1/2") still matches, and a value it spells out
    ("yirmi" for "20", "üçüncü" for "3rd") counts as present.

    A limit worth stating: a target language whose number word doubles as an article ("bir", one)
    is counted as the number it also is, so that value can hide a genuinely lost digit. The check
    is a report, not a gate - the fitting pass keeps the source when a segment's numbers came back
    wrong, and a human reads what is flagged.
    """
    have = _digit_groups(_joined_thousands(reply)) + spelled_numbers(reply, target_lang)
    need = _digit_groups(_joined_thousands(source))
    return any(have[digits] < count for digits, count in need.items())


#: The most frequent function words of each language this can judge. They carry no subject matter,
#: so any running text in a language is dense with its own and nearly free of another's - which is
#: what makes a reply in the wrong language visible whatever it is about.
_FUNCTION_WORDS: dict[str, frozenset[str]] = {
    "tr": frozenset(["ve", "bir", "bu", "için", "ile", "da", "de", "olan", "olarak", "gibi", "daha", "çok", "en", "ancak", "ya", "veya", "ki", "ama", "her", "şu", "o"]),
    "en": frozenset(["the", "and", "of", "to", "is", "in", "that", "with", "for", "are", "this", "which", "by", "be", "as", "on", "an", "or", "from", "it", "was", "were"]),
    "de": frozenset(["der", "die", "das", "und", "ist", "sind", "nicht", "mit", "von", "zu", "den", "ein", "eine", "im", "auf", "für", "sich", "dem", "des", "ich"]),
    "fr": frozenset(["le", "la", "les", "et", "est", "des", "une", "un", "du", "que", "pour", "dans", "pas", "sur", "au", "qui", "ne", "se"]),
    "es": frozenset(["el", "la", "los", "las", "y", "es", "que", "en", "un", "una", "por", "con", "para", "del", "se", "no", "lo"]),
    "it": frozenset(["il", "la", "le", "e", "è", "che", "di", "un", "una", "per", "con", "del", "della", "non", "si", "gli"]),
    "pt": frozenset(["o", "a", "os", "as", "e", "é", "que", "de", "um", "uma", "para", "com", "do", "da", "não", "se", "em"]),
    "nl": frozenset(["de", "het", "en", "is", "een", "van", "dat", "die", "in", "op", "met", "voor", "niet", "zijn", "te"]),
}

#: A reply needs this many words before its function words say anything.
_LANGUAGE_MIN_WORDS = 6

#: Share of a reply's words that must be another language's function words, and outnumber the
#: target's, before the reply is called that language.
_LANGUAGE_SHARE = 0.12


def wrong_language(reply: str, target_lang: str) -> str | None:
    """The language a reply is actually in, when it is clearly not `target_lang`; else None.

    Only languages with a profile are judged, and an unknown target is never judged. Quoted text
    and addresses are left out first, so a translation that keeps an English program output or a
    URL is not taken for English.
    """
    target = _FUNCTION_WORDS.get(target_lang.split("-")[0].casefold())
    if target is None:
        return None
    text = _QUOTED.sub(" ", _MARKER.sub("", reply))
    # A suffix joined by an apostrophe ("Latince'deki", "16.1'e") is part of its word: split off,
    # "de" and "e" read as Dutch and Italian function words.
    words = [
        w.casefold() for token in text.split()
        if not any(hint in token.casefold() for hint in _ADDRESS_HINTS)
        for w in re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*", token)
    ]
    if len(words) < _LANGUAGE_MIN_WORDS:
        return None
    own = sum(w in target for w in words) / len(words)
    best, best_share = None, own
    for lang, profile in _FUNCTION_WORDS.items():
        if profile is target:
            continue
        # A word the target language also uses ("de" is Turkish and Dutch) is no evidence either way.
        hits = [w for w in words if w in profile and w not in target]
        share = len(hits) / len(words)
        # At least two different function words: one alone ("ne", which French also has) is a
        # coincidence, not a language.
        if len(set(hits)) >= 2 and share >= _LANGUAGE_SHARE and share > best_share:
            best, best_share = lang, share
    return best


def _script(letter: str) -> str:
    """The writing system a letter belongs to, as Unicode names it ("LATIN", "CYRILLIC", ...)."""
    import unicodedata

    try:
        return unicodedata.name(letter).split()[0]
    except ValueError:
        return "UNKNOWN"


def garbled_words(source: str, reply: str) -> list[str]:
    """Words of the reply that mix letters of two writing systems, one of them not in the source.

    Held-out WPA poster and Popular Science Monthly: "MÜHENДİSİ" - a Cyrillic letter inside a
    Turkish word, three times from the same model, and every other check passed it. Only letters
    count: subscripts, superscripts and fractions ("A₃", "x²", "l½") are not a script, and a Greek
    letter the source already uses ("α-helix") is carried rather than invented. Measured on the
    campaign's 21,600 translated blocks: the three glitches above and nothing else.
    """
    known = {_script(c) for c in source if c.isalpha()}
    found = []
    for word in _LETTER_RUN.findall(reply):
        scripts = {_script(c) for c in word if c.isalpha()}
        if len(scripts) > 1 and scripts - known:
            found.append(word)
    return found
