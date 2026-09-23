"""A list or paragraph number the source starts with survives the model dropping it.

Bench arm d-tr (Turkish statutes to English): '4.Kapsama dahil diğer personel için' came back as
'For other personnel included in the scope,' and paragraphs opening '(1)' lost their number - the
label rule only knew '3.' followed by a space.
"""

from __future__ import annotations

import pytest

from layoutkeep.providers.openai_compat import _with_leading_label


@pytest.mark.parametrize(
    ("source", "reply", "expected"),
    [
        ("3. Write a function", "Bir fonksiyon yazın", "3. Bir fonksiyon yazın"),
        ("4.Kapsama dahil diğer personel için", "For other personnel included", "4. For other personnel included"),
        ("(1) Herkesin gelip geçtiği yerlerde", "In places frequented by all", "(1) In places frequented by all"),
        ("(b) ikinci durum", "the second case", "(b) the second case"),
    ],
)
def test_a_dropped_leading_label_is_put_back(source, reply, expected):
    assert _with_leading_label(source, reply) == expected


def test_a_label_the_reply_kept_is_not_doubled():
    assert _with_leading_label("(1) Metin", "(1) Text") == "(1) Text"


def test_a_number_that_is_not_a_label_is_left_alone():
    assert _with_leading_label("2012 yılında", "In 2012") == "In 2012"
