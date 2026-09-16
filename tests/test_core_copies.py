"""What counts as a reply that is still the source.

Every false alarm below is a real block from the campaign's digital pilot; the true copies are
real too. The distinction has to hold for any language pair, so it is judged on the texts, not on
a word list.
"""

from __future__ import annotations

from layoutkeep.core.copies import is_copy


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
