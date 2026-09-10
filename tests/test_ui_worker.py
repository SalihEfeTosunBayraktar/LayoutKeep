"""Worker orchestration tests, run synchronously via `run()` (no thread) with the fake
provider so they need no network. Exercises the same read -> segment -> translate -> apply ->
write -> save_project path the CLI uses, just from `ui/worker.py`.
"""

from __future__ import annotations

import socket
import sys
import threading
from pathlib import Path

from layoutkeep.core.docir import load_project
from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.worker import TranslationWorker, _batch_timeout

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import build_epub_fixture
import build_pdf_fixture


def _job(tmp_path, **overrides) -> JobConfig:
    src = tmp_path / "sample.epub"
    build_epub_fixture.build_sample_epub(src)
    defaults = {
        "input_path": str(src),
        "output_path": str(tmp_path / "sample.out.epub"),
        "source_lang": "en",
        "target_lang": "tr",
        "provider": ProviderConfig(kind="fake"),
    }
    defaults.update(overrides)
    return JobConfig(**defaults)


def test_worker_pdf_input_runs_the_shared_fit_pass(qtbot, tmp_path, monkeypatch):
    """The GUI must fit PDF output exactly like the CLI does - both run fitting/pdf_pass.

    Regression for the two-directional engine landing: before this, ui/worker.py never called
    fitting at all, so a PDF translated from the desktop app could overflow its boxes while the
    CLI fitted the same job (the drift pdf_pass.py's docstring warns about).
    """
    from layoutkeep.ui.worker import TranslationWorker

    src = tmp_path / "sample.pdf"
    build_pdf_fixture.build_single_column(src)
    config = _job(
        tmp_path,
        input_path=str(src),
        output_path=str(tmp_path / "sample.out.pdf"),
    )

    fit_calls: list[tuple] = []

    def _spy(self, doc, segments, config, provider=None):
        fit_calls.append((len(segments), config.provider.kind))
        # do not actually retranslate against a network - the spy stands in for the pass

    monkeypatch.setattr(TranslationWorker, "_fit_pdf_pass", _spy)

    worker = TranslationWorker(config)
    finished: list[str] = []
    worker.finished_ok.connect(finished.append)
    failed: list[str] = []
    worker.failed.connect(failed.append)
    worker.run()

    assert not failed, failed
    assert finished
    assert fit_calls, "PDF girdi icin _fit_pdf_pass cagrilmadi"
    assert fit_calls[0][1] == "fake"


def test_worker_translates_and_writes_project(qtbot, tmp_path):
    config = _job(tmp_path)
    worker = TranslationWorker(config)

    progress_calls: list[tuple[int, int]] = []
    worker.progress.connect(lambda done, total: progress_calls.append((done, total)))
    finished: list[str] = []
    worker.finished_ok.connect(finished.append)
    failed: list[str] = []
    worker.failed.connect(failed.append)

    worker.run()  # synchronous - no QThread needed for orchestration correctness

    assert not failed
    assert finished
    assert progress_calls[-1][0] == progress_calls[-1][1]

    doc = load_project(finished[0])
    assert doc.target_lang == "tr"
    assert any("[tr]" in block.text for _, block in doc.iter_blocks())
    assert Path(config.output_path).exists()


def test_cancel_stops_before_writing_output(qtbot, tmp_path):
    config = _job(tmp_path)
    worker = TranslationWorker(config)
    worker.cancel()  # cancelled before it ever starts translating

    finished: list[str] = []
    worker.finished_ok.connect(finished.append)
    worker.run()

    assert not finished
    assert not Path(config.output_path).exists()


def test_failure_signal_on_bad_input_path(qtbot, tmp_path):
    config = _job(tmp_path, input_path=str(tmp_path / "does_not_exist.epub"))
    worker = TranslationWorker(config)

    failed: list[str] = []
    worker.failed.connect(failed.append)
    worker.run()

    # A1: mesaj kullanici dostu - traceback degil, dosyanin adini soyleyen tek cumle
    assert len(failed) == 1
    assert "bulunamadı" in failed[0] or "not found" in failed[0]
    assert "Traceback" not in failed[0]
    assert "does_not_exist.epub" in failed[0]


# -- connection failures must be legible, not a stack trace (mirrors cli.py cmd_translate) ------


def test_timeout_produces_readable_message_not_a_stack_trace(qtbot, tmp_path, monkeypatch):
    config = _job(tmp_path)
    worker = TranslationWorker(config)

    def _raise_timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        "layoutkeep.providers.fake.FakeProvider.translate", _raise_timeout
    )

    failed: list[str] = []
    worker.failed.connect(failed.append)
    worker.run()

    assert len(failed) == 1
    message = failed[0]
    assert "zaman aşımı" in message
    assert "Traceback" not in message


def test_connection_failure_produces_readable_message_not_a_stack_trace(qtbot, tmp_path, monkeypatch):
    config = _job(tmp_path)
    worker = TranslationWorker(config)

    def _raise_os_error(*args, **kwargs):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(
        "layoutkeep.providers.fake.FakeProvider.translate", _raise_os_error
    )

    failed: list[str] = []
    worker.failed.connect(failed.append)
    worker.run()

    assert len(failed) == 1
    message = failed[0]
    assert "ulaşılamıyor" in message
    assert "LM Studio" in message
    assert "Traceback" not in message


def _stalling_server() -> tuple[socket.socket, int, list[socket.socket]]:
    """A raw TCP server that accepts a connection and then never answers - simulates a model
    server that is up but still loading, the exact condition that timed out a real user's job.
    The accepted connection is kept open (not closed) so the client sees a stall, not a reset."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    accepted: list[socket.socket] = []

    def _accept_and_stall() -> None:
        try:
            conn, _ = srv.accept()
            accepted.append(conn)
        except OSError:
            pass  # server closed while waiting - fine, test is already done

    threading.Thread(target=_accept_and_stall, daemon=True).start()
    return srv, port, accepted


def test_real_timeout_against_a_stalling_server_fails_cleanly_without_crashing(qtbot, tmp_path):
    """Reproduces the user report ("timed out and closed") against a real socket instead of a
    monkeypatched exception. The worker must emit `failed` and return normally - no unhandled
    exception may escape `run()`, since that is what previously could tear down the whole app
    from a QThread (see docs/CONTRACT.md - the UI must never block/crash the main thread).

    `ProviderConfig.timeout=1.0` below is an explicit override, which `OpenAICompatProvider.
    translate()` now uses verbatim for every batch instead of recomputing an adaptive value - so
    the real socket read is bounded by it directly, no patching needed."""
    srv, port, accepted = _stalling_server()
    try:
        config = _job(
            tmp_path,
            provider=ProviderConfig(
                kind="openai",
                base_url=f"http://127.0.0.1:{port}/v1",
                model="test-model",
                timeout=1.0,  # explicit override so the test doesn't wait the 240s cold-load base
            ),
        )
        worker = TranslationWorker(config)

        failed: list[str] = []
        worker.failed.connect(failed.append)
        worker.run()  # must not raise

        assert len(failed) == 1
        assert "1 saniye" in failed[0]
        assert "Traceback" not in failed[0]
    finally:
        for conn in accepted:
            conn.close()
        srv.close()


# -- adaptive per-batch timeout ------------------------------------------------------------


def test_batch_timeout_uses_large_base_for_the_first_batch_to_cover_cold_model_load():
    first = _batch_timeout(100, is_first=True, chars_per_second=None)
    warm = _batch_timeout(100, is_first=False, chars_per_second=None)
    assert first > warm


def test_batch_timeout_grows_with_batch_size():
    small = _batch_timeout(100, is_first=False, chars_per_second=10.0)
    large = _batch_timeout(10_000, is_first=False, chars_per_second=10.0)
    assert large > small


def test_batch_timeout_uses_measured_rate_over_the_fallback_guess():
    slow_guess = _batch_timeout(1000, is_first=False, chars_per_second=None)
    fast_measured = _batch_timeout(1000, is_first=False, chars_per_second=1000.0)
    assert fast_measured < slow_guess


def test_batch_timeout_is_clamped_at_both_ends():
    from layoutkeep.ui.worker import _MAX_BATCH_TIMEOUT_S, _MIN_BATCH_TIMEOUT_S

    assert _batch_timeout(0, is_first=False, chars_per_second=1000.0) == _MIN_BATCH_TIMEOUT_S
    assert _batch_timeout(10**9, is_first=False, chars_per_second=1.0) == _MAX_BATCH_TIMEOUT_S


def test_worker_emits_batch_timeout_before_each_batch(qtbot, tmp_path):
    config = _job(tmp_path)
    worker = TranslationWorker(config)

    timeouts: list[float] = []
    worker.batch_timeout.connect(timeouts.append)
    worker.run()

    assert timeouts  # at least one batch was sent
    assert all(t > 0 for t in timeouts)


def test_explicit_timeout_override_is_used_verbatim(qtbot, tmp_path):
    config = _job(tmp_path, provider=ProviderConfig(kind="fake", timeout=42.0))
    worker = TranslationWorker(config)

    timeouts: list[float] = []
    worker.batch_timeout.connect(timeouts.append)
    worker.run()

    assert timeouts and all(t == 42.0 for t in timeouts)


def test_the_gui_stack_protects_literals_like_the_cli_does(tmp_path) -> None:
    """`_build_provider` says it mirrors cli.py's. It did not: it built no ProtectedProvider,
    so every torque figure and part number in a document translated from the desktop app - the
    product, per CONTRACT.md - went to the model unprotected while the CLI held it back.
    """
    from layoutkeep.providers.protected import ProtectedProvider
    from layoutkeep.ui.worker import _build_provider

    provider, _memory = _build_provider(_job(tmp_path))
    assert isinstance(provider, ProtectedProvider)

    provider, _memory = _build_provider(_job(tmp_path, memory_path=str(tmp_path / "m.sqlite")))
    assert isinstance(provider, ProtectedProvider)


def test_the_adaptive_timeout_reaches_through_every_wrapper(tmp_path) -> None:
    """With protection and a memory both in play the real provider is two decorators down.
    Unwrapping one layer sets the timeout on a CachedProvider, which has none, and every batch
    silently runs on the default instead.
    """
    from layoutkeep.ui.worker import _build_provider, _set_provider_timeout

    job = _job(tmp_path, memory_path=str(tmp_path / "m.sqlite"))
    job.provider = ProviderConfig(kind="openai", base_url="http://localhost:1234/v1", model="x")
    provider, _memory = _build_provider(job)

    _set_provider_timeout(provider, 42.0)

    innermost = provider
    while getattr(innermost, "inner", None) is not None:
        innermost = innermost.inner
    assert innermost.timeout == 42.0
