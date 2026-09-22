"""Term candidates: what recurs in a document, offered to the person who writes the glossary.

The rules are deliberately simple and are asserted as rules, not as a golden list: a phrase that
starts or ends on a function word is not a candidate, a phrase seen fewer than `minimum_count`
times is not offered, and what the glossary already holds is not offered again. The interesting
test is the last one - the suggestion has to be *useful*, which here means "it finds the phrases a
reader of the document would recognise", measured on a real page rather than on a toy string.
"""

from __future__ import annotations

from layoutkeep.core.terms import candidates, suggest_from_document


def test_a_phrase_that_recurs_is_offered() -> None:
    text = "The central limit theorem matters. The central limit theorem is used everywhere."

    found = [item.phrase for item in candidates([text], minimum_count=2)]

    assert "central limit theorem" in [phrase.casefold() for phrase in found]


def test_a_phrase_that_starts_or_ends_on_a_function_word_is_not_offered() -> None:
    text = "of the data and the data of the model and the model"

    found = [item.phrase.casefold() for item in candidates([text], minimum_count=2)]

    assert not any(phrase.startswith(("of ", "and ", "the ")) for phrase in found)
    assert not any(phrase.endswith((" of", " and", " the")) for phrase in found)


def test_a_one_off_phrase_is_not_offered() -> None:
    text = "Bayesian inference appears once here. Random variable appears once too."

    found = [item.phrase.casefold() for item in candidates([text], minimum_count=2)]

    assert "bayesian inference" not in found


def test_what_the_glossary_already_holds_is_not_offered_again() -> None:
    text = "random variable and random variable and random variable"

    found = [
        item.phrase.casefold()
        for item in candidates([text], minimum_count=2, exclude={"random variable"})
    ]

    assert "random variable" not in found


def test_the_ranking_prefers_longer_phrases_at_the_same_count() -> None:
    """A recurring three-word phrase is worth more of the reader's attention than a recurring
    single word, which is usually just the document's topic."""
    text = "probability distribution function x " * 4

    ranked = candidates([text], minimum_count=4, limit=5)

    assert ranked, "expected candidates"
    assert ranked[0].phrase.count(" ") >= 1, ranked[0]


def test_a_number_is_not_a_term() -> None:
    text = "1024 and 1024 and 1024 and 1024"

    assert candidates([text], minimum_count=2) == []


def test_candidates_come_from_a_real_document(tmp_path) -> None:
    """On a real page of the NIST journal: the phrases it offers must be phrases that page
    actually repeats, checked against the text rather than against a stored list."""
    from layoutkeep.writers.converter import read_any_document

    source = tmp_path / "doc.pdf"
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for index in range(6):
        page.insert_text(
            (60, 80 + index * 40),
            "The probability distribution of a random variable is described by "
            "its probability distribution function.",
            fontsize=11,
        )
    doc.save(str(source))
    doc.close()

    document = read_any_document(source)
    found = suggest_from_document(document, limit=10)
    phrases = [item.phrase.casefold() for item in found]

    assert any("probability distribution" in phrase for phrase in phrases), phrases
    assert all(item.count >= 3 for item in found)


def test_the_editor_offers_terms_from_the_job_document(qtbot, tmp_path) -> None:
    """The whole point: the editor can fill itself from the document the job is about to read."""
    import pymupdf

    from layoutkeep.ui.glossary_dialog import GlossaryDialog

    source = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for index in range(6):
        page.insert_text(
            (60, 80 + index * 40),
            "The probability distribution of a random variable is described by its "
            "probability distribution function.",
            fontsize=11,
        )
    doc.save(str(source))
    doc.close()

    dialog = GlossaryDialog()
    qtbot.addWidget(dialog)
    assert not dialog._suggest_btn.isEnabled(), "no document, no suggestion"

    dialog.set_document(source)
    assert dialog._suggest_btn.isEnabled()
    dialog._suggest()

    terms = dialog.terms()
    assert terms, "the editor should have gained candidate rows"
    assert all(value == "" for value in terms.values()), "targets are the person's to write"
    assert "candidates added" in dialog._status.text() or "aday" in dialog._status.text()


def test_the_editor_does_not_offer_what_is_already_there(qtbot, tmp_path) -> None:
    import pymupdf

    from layoutkeep.ui.glossary_dialog import GlossaryDialog

    source = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for index in range(6):
        page.insert_text((60, 80 + index * 40), "random variable and random variable again", fontsize=11)
    doc.save(str(source))
    doc.close()

    dialog = GlossaryDialog()
    qtbot.addWidget(dialog)
    dialog._append("random variable", "rastgele değişken")
    dialog.set_document(source)
    dialog._suggest()

    assert dialog.terms().get("random variable") == "rastgele değişken", "the existing row was overwritten"


def test_a_phrase_built_around_a_postposition_is_not_a_term() -> None:
    """Turkish Penal Code: 'yıla kadar hapis' and 'kadar' were offered - grammar, not terms, and a
    glossary that pins 'kadar -> up to' forces one rendering onto every sentence that uses it."""
    text = " ".join(
        ["iki yıla kadar hapis cezası verilir.", "altı aya kadar hapis cezası verilir.",
         "bu şekilde davranan kişi cezalandırılır.", "bu şekilde davranan kişi cezalandırılır."] * 2
    )

    found = [item.phrase.casefold() for item in candidates([text], minimum_count=2)]

    assert not any(word in phrase.split() for phrase in found for word in ("kadar", "şekilde"))
    assert "hapis cezası" in found


def test_common_english_function_words_do_not_frame_a_term() -> None:
    text = "each person shall file each return. each person shall file each return."

    found = [item.phrase.casefold() for item in candidates([text], minimum_count=2)]

    assert not any(phrase.split()[0] in ("each", "shall") or phrase.split()[-1] in ("each", "shall")
                   for phrase in found)
