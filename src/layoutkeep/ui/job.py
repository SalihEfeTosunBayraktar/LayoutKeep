"""Job description passed from the setup screen to the translation worker.

Plain data only - no Qt, no core logic. Keeping it Qt-free makes it easy to unit test the
worker's orchestration without a QApplication.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProviderConfig:
    """What the provider settings screen produces."""

    #: "openai" - any OpenAI-compatible chat endpoint (LM Studio, Ollama, cloud).
    #: "deepl"  - DeepL's translation API. No model to choose; the key decides the host.
    #: "fake"   - the test provider, which does not translate.
    kind: str
    base_url: str = "http://localhost:1234/v1"
    model: str = ""
    api_key: str | None = None
    #: Per-request timeout override, in seconds. None (the default) means the worker computes
    #: an adaptive timeout per batch instead - see worker.py's `_batch_timeout`. This is an
    #: advanced escape hatch for unusual hardware, not something a user should have to set to
    #: get a working default.
    timeout: float | None = None


@dataclass(slots=True)
class JobConfig:
    """What the job setup screen produces."""

    input_path: str
    output_path: str
    source_lang: str
    target_lang: str
    provider: ProviderConfig
    memory_path: str | None = None
    project_path: str | None = None
    page_range: str = ""
