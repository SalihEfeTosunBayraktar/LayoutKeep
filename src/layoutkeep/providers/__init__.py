"""Translation provider layer (see docs/CONTRACT.md, D2). Layout-blind: list[Segment] in, list[Segment] out."""

from __future__ import annotations

from layoutkeep.providers.base import TranslationProvider
from layoutkeep.providers.cached import CachedProvider
from layoutkeep.providers.fake import FakeProvider
from layoutkeep.providers.glossary import Glossary
from layoutkeep.providers.memory import TranslationMemory
from layoutkeep.providers.openai_compat import OpenAICompatProvider

__all__ = [
    "CachedProvider",
    "FakeProvider",
    "Glossary",
    "OpenAICompatProvider",
    "TranslationMemory",
    "TranslationProvider",
]
