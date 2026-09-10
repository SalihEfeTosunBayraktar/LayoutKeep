"""Background worker that fetches the model list from an OpenAI-compatible provider.

Ayrı iş parçacığında OpenAI-uyumlu bir sağlayıcıdan model listesi getiren yardımcı.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class ListModelsWorker(QThread):
    # Modelleri arka planda sorgulayan iş parçacığı / Worker fetching models in background
    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, base_url: str, api_key: str | None, parent=None) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._api_key = api_key

    def run(self) -> None:
        from layoutkeep.providers.openai_compat import OpenAICompatProvider

        provider = OpenAICompatProvider(base_url=self._base_url, model="", api_key=self._api_key)
        try:
            models = provider.list_models()
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(models)
