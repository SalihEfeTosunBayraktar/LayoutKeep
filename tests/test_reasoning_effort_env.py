"""The bench can switch a model's thinking on without changing what the product sends.

The product sends reasoning_effort "none" (thinking measured at 30x the tokens for the same
translation). The thinking on/off comparison needs the other arm, so an environment variable - set
only by a measurement - overrides it for one run.
"""

from __future__ import annotations

from layoutkeep.providers._http_compat import DEFAULT_REASONING_EFFORT, OpenAIHTTPTransport


def test_the_product_default_is_no_thinking(monkeypatch):
    monkeypatch.delenv("LAYOUTKEEP_REASONING_EFFORT", raising=False)
    assert OpenAIHTTPTransport("http://x/v1", None).reasoning_effort == DEFAULT_REASONING_EFFORT == "none"


def test_a_measurement_can_ask_for_thinking(monkeypatch):
    monkeypatch.setenv("LAYOUTKEEP_REASONING_EFFORT", "medium")
    assert OpenAIHTTPTransport("http://x/v1", None).reasoning_effort == "medium"
