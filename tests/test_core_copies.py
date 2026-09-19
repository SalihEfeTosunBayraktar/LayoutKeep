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


def test_a_function_word_the_target_shares_is_no_evidence_of_another_language() -> None:
    """Think Python: "in operatörü ayrıca listeler üzerinde de çalışır." was called Dutch - the
    Python keyword "in" plus Turkish "de", both Dutch function words. A word the target language
    also uses says nothing about which language the text is in."""
    assert wrong_language("in operatörü ayrıca listeler üzerinde de çalışır.", "tr") is None


def test_a_small_number_written_as_a_word_is_not_lost() -> None:
    """Think Python: "Since 3 is not 0, it takes the second branch" came back as "3 sıfır
    olmadığı için ikinci dalı alır" - 0 written "sıfır", nothing lost. Small numbers are written
    in words as often as in digits; the target language's words for 0-10 count as those digits."""
    from layoutkeep.core.copies import drops_numbers

    assert not drops_numbers("Since 3 is not 0, it takes the second branch", "3 sıfır olmadığı için ikinci dalı alır", "tr")
    assert drops_numbers("Since 3 is not 0, it takes the second branch", "3 olmadığı için ikinci dalı alır", "tr")


def test_a_letter_from_another_alphabet_inside_a_word_is_garbled() -> None:
    """Held-out WPA poster and Popular Science: "MÜHENДİSİ" - a Cyrillic letter inside a Turkish
    word, three times from the same model. Every other check passed it: the language is right,
    no number is lost, nothing was copied."""
    from layoutkeep.core.copies import garbled_words

    assert garbled_words("MECHANICAL ENGINEER", "MAKİNE MÜHENДİSİ") == ["MÜHENДİSİ"]
    assert garbled_words("the atmosphere", "〳atmosferinden") == ["〳atmosferinden"]


def test_scripts_the_source_has_and_symbols_that_are_not_letters_are_not_garbled() -> None:
    from layoutkeep.core.copies import garbled_words

    # Subscripts, superscripts and fractions are not letters (computer-systems-Architecture: "A₃").
    assert garbled_words("the output A3 and x squared", "A₃ çıkışı ve x² değeri, l½ inç") == []
    # A Greek letter the source already uses is carried, not invented.
    assert garbled_words("the α-helix and βcatenin", "α-heliks ve βkatenin") == []


def test_a_number_written_out_in_words_is_not_a_lost_number() -> None:
    """Every held-out document had at least one: the 1907 cookbook's "five medium onions", the
    IRS instructions' thresholds, an arXiv paper's "one hundred". Counting digits only reports a
    loss that never happened - and the retry it triggers re-asks a number-heavy block, which is
    what dropped NIST's "(1)" placeholder six times out of six."""
    from layoutkeep.core.copies import drops_numbers

    assert not drops_numbers("There are 20 pages of notes", "Notların yirmi sayfası var", "tr")
    assert not drops_numbers("12 chapters", "on iki bölüm", "tr")
    assert not drops_numbers("2500 items", "iki bin beş yüz öğe", "tr")
    assert not drops_numbers("20 pages", "twenty pages", "en")
    assert not drops_numbers("12 chapters", "twelve chapters", "en")
    assert not drops_numbers("100 samples", "one hundred samples", "en")


def test_a_number_that_is_really_missing_is_still_reported() -> None:
    from layoutkeep.core.copies import drops_numbers

    assert drops_numbers("Pages 20 to 24", "yirmi ve sonrası", "tr")
    assert drops_numbers("See 5.2.1 for the policy", "Politika için bkz.", "tr")


def test_a_run_of_number_words_is_folded_to_the_value_it_names() -> None:
    from layoutkeep.core.copies import spelled_numbers

    assert spelled_numbers("on iki bölüm", "tr")["12"] == 1
    assert spelled_numbers("iki bin beş yüz", "tr")["2500"] == 1
    assert spelled_numbers("two thousand five hundred", "en")["2500"] == 1
    assert spelled_numbers("nothing here", "tr") == {}
    # A language this has no words for contributes nothing rather than guessing.
    assert spelled_numbers("twenty pages", "xx") == {}
