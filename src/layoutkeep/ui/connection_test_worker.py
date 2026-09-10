"""Background connection test for one endpoint.

The dialog's "Test" button has to answer a single question - does this endpoint work with
these credentials - for providers that answer it in different ways. An OpenAI-compatible
server is asked for its model list; DeepL is asked for its usage, which costs no characters
and reports the quota left; the test provider needs no network at all.

It runs on a thread because a wrong host takes as long as the timeout to fail, and a frozen
dialog looks like a crashed application.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class ConnectionTestWorker(QThread):
    # Uç noktayı arka planda sınayan iş parçacığı / Worker testing one endpoint in background
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        kind: str,
        base_url: str,
        api_key: str | None,
        timeout: float | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout

    def run(self) -> None:
        try:
            self.succeeded.emit(self._check())
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))

    def _check(self) -> str:
        if self._kind == "fake":
            return "Test sağlayıcısı - ağ bağlantısı gerekmez"
        if self._kind == "deepl":
            from layoutkeep.providers.deepl import DeepLProvider

            provider = DeepLProvider(
                self._api_key or "",
                base_url=self._base_url or None,
                timeout=self._timeout or 30.0,
            )
            return provider.check_connection()

        from layoutkeep.providers.openai_compat import OpenAICompatProvider

        models = OpenAICompatProvider(
            base_url=self._base_url, model="", api_key=self._api_key
        ).list_models()
        if not models:
            return "Sunucuya ulaşıldı ama model listesi boş"
        return f"Bağlantı çalışıyor - {len(models)} model bulundu"
