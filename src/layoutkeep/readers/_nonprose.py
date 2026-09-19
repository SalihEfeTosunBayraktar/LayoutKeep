"""Is this text code, rather than prose that happens to contain a symbol?

WHY THIS EXISTS. A born-digital PDF says which runs are monospaced (see
`readers/pdf_reader._all_monospace`), and Think Python's code blocks were caught by that. A
LaTeX paper's verbatim fragments are not set in a monospaced face at all, so nothing caught them
and they were sent for translation as prose. Held-out arXiv 2609.19145 came back with these among
its seven untranslated blocks - a model that sees a line of options echoes it:

    trim_offsets=True, use_regex=True)
    trim_offsets=False, use_regex=True)

The consequence is not a garbled translation but a claim: the line stays in the source language,
the audit counts it as text left untranslated (L2), the retry ladder spends three lone requests
and then a request per piece on it, and every one of them is answered with the same line. Code is
carried through untouched by policy (`BlockRole.CODE`); these never reached it.

WHAT THIS JUDGES. Only the shape of the text, and only when that shape cannot be prose: an
identifier written `like_this`, a call with its parenthesis attached, or a keyword argument, each
alongside enough brackets and operators to be set as code rather than quoted in a sentence. A
sentence that ends like a sentence is never code, however many parentheses it holds - which is what
keeps a form's "Form 1099-B (or 1099-DA)" and a manual's "the bolts (3)" out of this, both of which
are text a reader wants translated.

Deliberately narrow. A missed line costs one wasted retry; a false positive silently leaves a
reader's paragraph in the source language, which is the failure this project spends its effort
avoiding.
"""

from __future__ import annotations

import re

#: `like_this` - an identifier no prose uses.
_SNAKE_CASE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")

#: `save(` - a call, the parenthesis attached, in a name long enough to be a function. Not
#: `f(a)`: a single letter in parentheses is how a paper writes a function of x, not code, and
#: treating it as code left a paragraph of arXiv's own prose untranslated in a probe over the
#: held-out sources ("Now, define f(a) = a log a, which implies ...").
_ATTACHED_CALL = re.compile(r"\b[a-z_][a-z0-9_]{2,}\(")

#: `use_regex=True` - a keyword argument, which only code and configuration files write.
_KEYWORD_ARGUMENT = re.compile(r"\b[a-z_][a-z0-9_]*(?:_[a-z0-9]+)+\s*=[^=\s]")

#: Punctuation that carries code and is rare in running prose.
_CODE_SYMBOLS = frozenset("(){}[]<>_=/*&|;\\`@#$^~\",:")

#: Operators that carry mathematics.
_MATH_OPERATORS = frozenset("=\u2248\u2264\u2265\u00b1\u2211\u2192\u221e\u221a^\u2212\\<>[]")

#: Nothing claiming to be code or a formula carries this many real words: a sentence does. The
#: guard that keeps a paragraph of prose with an equation in it translating as prose.
_PROSE_WORD = re.compile(r"[^\W\d_]{3,}")
_PROSE_WORDS = 10

#: A fragment this short is an equation rather than a sentence about one.
_FORMULA_WORDS = 8

#: Share of a text's characters that must be code punctuation. Measured: the arXiv lines above sit
#: at 0.24, and the most symbol-dense prose in the same document ("(ii) the new token s1 ◦s2
#: changes from frequency 0 to ...") at 0.04.
_MIN_SYMBOL_SHARE = 0.08

#: Text that ends in sentence punctuation ends like a sentence. A code line does not.
_SENTENCE_END = re.compile(r"""[.!?…]["'”’)\]]*\s*$""")

#: Longer than this and it is a paragraph: paragraphs are prose whatever they quote.
_MAX_CHARS = 300


def _reads_as_prose(stripped: str) -> bool:
    return len(_PROSE_WORD.findall(stripped)) >= _PROSE_WORDS


def _symbol_share(stripped: str) -> float:
    symbols = sum(character in _CODE_SYMBOLS for character in stripped)
    return symbols / len(stripped)


def is_code_like(text: str) -> bool:
    """True when `text` is a line of code or a verbatim fragment, not a sentence to translate."""
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_CHARS:
        return False
    if _SENTENCE_END.search(stripped) or _reads_as_prose(stripped):
        return False
    if not (
        _SNAKE_CASE.search(stripped)
        or _ATTACHED_CALL.search(stripped)
        or _KEYWORD_ARGUMENT.search(stripped)
    ):
        return False
    return _symbol_share(stripped) >= _MIN_SYMBOL_SHARE


def is_formula_like(text: str) -> bool:
    """True when `text` is a fragment of mathematics rather than a sentence about one.

    The reader already recognises a displayed equation by its faces (`_looks_like_math`); this
    catches the ones set in an ordinary face, which are otherwise sent for translation as prose -
    held-out arXiv 2609.19145's "f(a) ≈f(x) + (a −x)f′(x)". Nothing that reads as a sentence
    qualifies: an equation is short, carries an operator, and does not end where a sentence does.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_CHARS:
        return False
    if _SENTENCE_END.search(stripped) or _reads_as_prose(stripped):
        return False
    if len(stripped.split()) > _FORMULA_WORDS:
        return False
    return any(character in _MATH_OPERATORS for character in stripped)
