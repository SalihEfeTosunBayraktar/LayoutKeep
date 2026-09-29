"""Language codes and what to call them, in a place both the interface and the providers can use.

WHY THIS EXISTS. The translation prompt said "from en to tr" - a code the model has to guess a
language and a script for. Measured on arXiv 2507.03009's appendix, whose table lists 56 language
names: asked for `tr`, gemma-4-e4b came back with `Urdu, Ukraynaca, Việt語, Galce` - the Vietnamese
name carrying Chinese characters, because nothing in the prompt said which script the answer was
in. The audit flags that as L9 (garbled letters) and it is the one loss the held-out campaign has
not been able to close.

Naming the language and asking for its own script is the cheap half of the fix; the other half is
that the same names are needed by the interface (`ui/languages.py`) and by the prompt, and a list
kept in two places drifts.

The names are English on purpose: that is the language a translation model is most reliably told
things in, whatever the interface language is.
"""

from __future__ import annotations

#: Language code -> English name. Codes are ISO 639-1 (or the common two-letter form) - the same
#: ones `--from`/`--to` and the interface's language selector carry.
ENGLISH_NAMES: dict[str, str] = {
    "ar": "Arabic",
    "az": "Azerbaijani",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sv": "Swedish",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh": "Chinese",
}

#: Languages whose script is not Latin, and what to call that script. The model is told to write
#: in it, because "translate to Vietnamese" alone produced Chinese characters inside Vietnamese
#: words (`Việt語`). Languages written in Latin need no such note.
SCRIPTS: dict[str, str] = {
    "ar": "Arabic script",
    "el": "Greek script",
    "fa": "Persian (Arabic) script",
    "he": "Hebrew script",
    "hi": "Devanagari script",
    "ja": "Japanese script (kanji, hiragana and katakana)",
    "ko": "Hangul",
    "ru": "Cyrillic script",
    "uk": "Cyrillic script",
    "zh": "Chinese characters (simplified or traditional, whichever the document uses)",
}


def english_name(code: str) -> str:
    """What to call `code` in a prompt. Unknown codes are returned as they came."""
    return ENGLISH_NAMES.get(code.strip().lower(), code)


def script_note(code: str) -> str:
    """The sentence telling the model which script to write in, empty for Latin-script targets."""
    script = SCRIPTS.get(code.strip().lower())
    if not script:
        return ""
    return f" Write it in {script}, never mixing in characters from another writing system."
