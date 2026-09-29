"""Building the provider chain a desktop run translates with, glossary included.

Masaüstü koşusunun çevireceği sağlayıcı zincirini (sözlük ve bellek dahil) kurar.
Builds the provider chain for a desktop run: provider, dedupe, memory, protection, glossary.
Callers reach `build_provider` through this module at call time, so a test that patches
`layoutkeep.ui.provider_factory.build_provider` is seen by every caller.
"""

from __future__ import annotations

from layoutkeep.providers.glossary import glossary_fingerprint, load_terms
from layoutkeep.ui.job import JobConfig


def load_glossary_terms(path: str | None) -> dict[str, str] | None:
    """Read a JSON glossary, or None when no file is configured.

    A broken file is not a reason to fail the job: it is reported by the caller and the run goes
    on without the glossary, which is the same document the user would have got before.

    The reading itself is `providers/glossary.load_terms`, the one the command line uses too; what
    this name adds is the window's own exception, which its callers report instead of stopping for.
    """
    try:
        return load_terms(path)
    except (OSError, ValueError) as exc:
        # A typo in a path or a hand-edited JSON file must not end a two-hour run before it
        # starts; the caller reports it and the document is translated as it would have been.
        raise GlossaryUnreadableError(path, str(exc)) from exc


class GlossaryUnreadableError(Exception):
    """The configured glossary file could not be read; the run continues without it."""


def build_provider(config: JobConfig):
    if config.provider.kind == "fake":
        from layoutkeep.providers.fake import FakeProvider

        provider, model_id = FakeProvider(), "fake"
    elif config.provider.kind == "deepl":
        from layoutkeep.providers.deepl import DeepLProvider

        provider = DeepLProvider(
            config.provider.api_key or "",
            base_url=config.provider.base_url or None,
            timeout=config.provider.timeout or 60.0,
        )
        # The key picks the host, so that is what identifies the model for the memory.
        model_id = f"deepl:{provider.host}"
    else:
        from layoutkeep.providers.openai_compat import OpenAICompatProvider

        provider = OpenAICompatProvider(
            base_url=config.provider.base_url,
            model=config.provider.model,
            api_key=config.provider.api_key,
        )
        model_id = f"{config.provider.base_url}:{config.provider.model}"

    from layoutkeep.providers.dedupe import DedupeProvider
    from layoutkeep.providers.protected import ProtectedProvider

    try:
        terms = load_glossary_terms(config.glossary_path)
    except GlossaryUnreadableError:
        terms = None  # the job runs without it; the settings dialog is where this is fixed
    if terms:
        model_id = f"{model_id}|gloss:{glossary_fingerprint(terms)}"

    if not config.memory_path:
        return ProtectedProvider(DedupeProvider(provider)), None, terms

    from layoutkeep.providers.cached import CachedProvider
    from layoutkeep.providers.memory import TranslationMemory

    memory = TranslationMemory(config.memory_path)
    return ProtectedProvider(CachedProvider(DedupeProvider(provider), memory, model_id)), memory, terms
