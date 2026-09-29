"""The system prompt is editable where it is instruction, frozen where it is protocol.

WHY THIS EXISTS: users asked to adapt the prompt to their subject matter and to give the model a
document preamble, because a measured half of all segments carry under 200 characters of neighbouring
context and none of them knows what the document is about. What must not happen is a user edits the
prompt and the replies stop being parseable - every lost marker is a page that cannot be put back -
so the contract lines are appended no matter what, and these tests hold that line.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core import tunables
from layoutkeep.core.docir import Segment
from layoutkeep.providers.openai_compat import _build_messages

_KEYS = ("provider.system_prompt_file", "provider.system_prompt_extra", "translation.document_preamble")
_PROTOCOL = "Reply with ONLY a JSON array"


def _prompt() -> str:
    seg = Segment(block_id="b1", source="Hello world", context_before="", context_after="")
    messages = _build_messages([seg], "en", "tr", None)
    return messages[0]["content"]


def _clean() -> None:
    for key in _KEYS:
        tunables.set_value(key, "")


def test_the_defaults_leave_the_prompt_exactly_as_it_was() -> None:
    _clean()
    try:
        prompt = _prompt()
    finally:
        _clean()

    assert _PROTOCOL in prompt
    assert "About this document" not in prompt


def test_a_document_preamble_and_extra_lines_reach_the_model() -> None:
    _clean()
    tunables.set_value("translation.document_preamble", "A 19th century Turkish story collection.")
    tunables.set_value("provider.system_prompt_extra", "Keep proper nouns in the original.")
    try:
        prompt = _prompt()
    finally:
        _clean()

    assert "About this document" in prompt
    assert "19th century Turkish story collection" in prompt
    assert "Keep proper nouns in the original." in prompt
    assert _PROTOCOL in prompt, "the protocol lines must survive whatever the user adds"


def test_a_file_replaces_the_role_line_and_nothing_else(tmp_path: Path) -> None:
    role_file = tmp_path / "role.txt"
    role_file.write_text("You are a literary translator working into Turkish.", encoding="utf-8")
    _clean()
    tunables.set_value("provider.system_prompt_file", str(role_file))
    try:
        prompt = _prompt()
    finally:
        _clean()

    assert prompt.startswith("You are a literary translator working into Turkish.")
    assert "You are a professional translator" not in prompt
    assert _PROTOCOL in prompt, "a user file must not be able to drop the reply contract"


def test_a_missing_file_keeps_the_built_in_role_line() -> None:
    _clean()
    tunables.set_value("provider.system_prompt_file", "C:/no/such/prompt.txt")
    try:
        prompt = _prompt()
    finally:
        _clean()

    assert "You are a professional translator" in prompt
    assert _PROTOCOL in prompt
