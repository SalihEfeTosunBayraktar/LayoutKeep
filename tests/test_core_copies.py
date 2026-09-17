"""What counts as a reply that is still the source.

Every false alarm below is a real block from the campaign's digital pilot; the true copies are
real too. The distinction has to hold for any language pair, so it is judged on the texts, not on
a word list.
"""

from __future__ import annotations

from layoutkeep.core.copies import is_copy, wrong_language


def test_names_that_stay_names_are_not_a_copy() -> None:
    names = "Michael Nieles Kelley Dempsey Victoria Yan Pillitteri"
    assert not is_copy(names, names)


def test_a_translated_footer_keeping_its_brand_is_not_a_copy() -> None:
    assert not is_copy("Free eBooks at Planet eBook.com", "Planet eBook.com'da Ucretsiz E-kitaplar")


def test_a_translation_keeping_a_url_is_not_a_copy() -> None:
    assert not is_copy(
        "Solution: https: // thinkpython. com/ code/ cartalk3. py .",
        "Cozum: https://thinkpython.com/code/cartalk3.py .",
    )


def test_a_translation_keeping_a_quoted_program_output_is_not_a_copy() -> None:
    assert not is_copy(
        "the program should print, \u201cHoly smokes, Fermat was wrong!\u201d Otherwise the program",
        "program \u201cHoly smokes, Fermat was wrong!\u201d yazdirir. Aksi takdirde program",
    )


def test_a_paragraph_left_in_english_is_a_copy() -> None:
    text = "There were others coming, and presently a little group of perhaps eight or ten of these"
    assert is_copy(text, text)


def test_english_with_recognition_noise_cleaned_is_a_copy() -> None:
    assert is_copy(
        "Simple CPU design examples are carried out in Chaps. 5 and 7. This chapter co s n thn memory stack.",
        "Simple CPU design examples are carried out in Chaps. 5 and 7. This chapter describes the memory stack.",
    )


def test_an_address_split_by_text_extraction_is_still_an_address() -> None:
    """Think Python page 110 in the pilot: extraction spaces a URL out ("https: // thinkpython.
    com/ code/ cartalk1. py"), its pieces looked like ordinary words, and a correct Turkish
    translation that kept the URL was called a copy."""
    source = ("Write a program to find it. Solution: https: // thinkpython. com/ code/ cartalk1. py . "
              "Here is another Car Talk Puzzler (http: // www. cartalk. com/ content/ puzzlers ):")
    reply = ("Bunu bulmak icin bir program yazin. Cozum: https: // thinkpython. com/ code/ cartalk1. py . "
             "Iste baska bir Car Talk Puzzler (http: // www. cartalk. com/ content/ puzzlers ):")
    assert not is_copy(source, reply)


def test_a_reply_that_lost_a_section_number_drops_numbers() -> None:
    from layoutkeep.core.copies import drops_numbers

    assert drops_numbers("5.2.1 Basic Components of Program Policy .... 27",
                         "Program Politikasinin Temel Bilesenleri .... 27")
    assert not drops_numbers("5.2.1 Basic Components .... 27", "5.2.1 Temel Bilesenler .... 27")
    # A decimal localised for the target language keeps its digits.
    assert not drops_numbers("pi is about 3.14 here", "pi burada yaklasik 3,14")


# Every book of the campaign had replies in the wrong language, including The Time Machine, which
# the audit had called lossless: a paragraph came back in German, a magazine headline too
# ("Sahne ist schockierend!"), and a heading half Turkish, half English. A copy check cannot see
# these - the words are not the source's.



def test_a_german_reply_to_a_turkish_request_is_wrong() -> None:
    reply = "Konkrete Krankheiten während meines gesamten Aufenthalts. Und ich muss sagen, dass die Luft"
    assert wrong_language(reply, "tr") == "de"


def test_a_half_translated_heading_is_wrong() -> None:
    reply = "the estimated power consumption of electrical appliances in the house and on the farm"
    assert wrong_language(reply, "tr") == "en"


def test_a_turkish_reply_is_right() -> None:
    reply = "Bu yayın, NIST tarafından 2014 Federal Bilgi Güvenliği Modernizasyon Yasası kapsamında ve bir çok"
    assert wrong_language(reply, "tr") is None


def test_a_turkish_reply_keeping_english_terms_is_right() -> None:
    reply = "Python'da math modülü bulunur ve bu modül ile log ve sin gibi fonksiyonlar kullanılabilir"
    assert wrong_language(reply, "tr") is None


def test_an_unknown_target_language_is_never_judged() -> None:
    assert wrong_language("the and of to is in that with for are", "ja") is None


def test_short_turkish_sentences_are_not_taken_for_other_languages() -> None:
    """Think Python, campaign run: correct Turkish replies called French ("ne" is also a French
    function word), Italian ("16.1'e" split at the apostrophe into "e") and Dutch ("Latince'de")."""
    assert wrong_language("5. Aralarında operatör olmayan iki değeriniz olursa ne olur?", "tr") is None
    assert wrong_language("Time nesnesinin durum diyagramı Şekil 16.1'e benziyor.", "tr") is None
    assert wrong_language("Peter Winstanley, Latince'deki uzun süredir devam eden bir hatayı Bölüm 3'te bize bildirdi.", "tr") is None
    assert wrong_language("İşte bir kare çizen for ifadesi ve bunun gibi daha fazlası:", "tr") is None
