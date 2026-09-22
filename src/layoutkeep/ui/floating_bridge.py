"""Pencere ile yüzen çubuk sırayla görünür / The window and the floating bar take turns.

Yüzen çubuk, pencere yoldan çekildiğinde bir koşuyu izleyen sahipsiz bir üst düzey penceredir.
İkisinden tam olarak biri ekranda olur; aralarındaki her yol (koşuyu devretme, geri dönme,
yeni iş başlatma, çıktıyı açma, duraklatma) burada durur, böylece ikisi çelişemez.

Kendi Qt durumunu tutmaz: pencereyi, çubuğu döndüren bir çağrıyı (`closeEvent` onu aldıktan
sonra None) ve sahiplenmemesi gereken geri çağırmaları alır.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget

from layoutkeep.core import tunables
from layoutkeep.ui.floating_progress import FloatingProgress


class FloatingBarBridge:
    """Hands a run between the window and the summary bar; exactly one of the two is visible."""

    def __init__(
        self,
        window: QWidget,
        bar: Callable[[], FloatingProgress | None],
        *,
        on_new_job: Callable[[], None],
        on_pause: Callable[[], None],
        on_resume: Callable[[], None],
        output_path: Callable[[], str],
    ) -> None:
        self._window = window
        self._bar = bar
        self._on_new_job = on_new_job
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._output_path = output_path

    def _shown_bar(self) -> FloatingProgress:
        """The bar, or the same error the window's own `_bar` property raises once it is gone."""
        bar = self._bar()
        if bar is None:
            raise RuntimeError("the floating bar was already destroyed")
        return bar

    def switch_to_bar(self, worker: object | None) -> None:
        """Hand the run to the floating bar: the window steps aside and the bar takes over.

        The bar used to be a one-way door. It appeared when a job started and when the window was
        minimised, and once it was folded or closed there was nothing left to bring it back - the
        reader had a running job and no compact view of it. This is the way in; the bar's own
        "back to window" button is the way out again.
        """
        if worker is None:
            return
        tunables.set_value("ui.floating_progress", True)
        self._window.hide()  # hideEvent hands the run to the bar (see `sync`)

    def sync(self) -> None:
        """The window and the bar take turns, so a run never shows two progress displays at once.

        This is the bug the first screenshot of the bar came with: the run started and the reader
        had the in-window progress screen *and* the bar on top of it. The bar is for when the
        window is out of the way - minimised, or hidden behind other work - and it is the only
        thing left on screen then, which is also the only way it stays reachable.
        """
        bar = self._bar()
        if bar is None:
            return
        if self._window.isMinimized() or not self._window.isVisible():
            bar.show()
            bar.raise_()
        else:
            bar.hide()

    def restore_window(self) -> None:
        # Yüzen çubuktan ana pencereye döner / Comes back to the full window from the summary bar
        self._shown_bar().hide()
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def start_new_job(self) -> None:
        # "Yeni çeviri": kurulum ekranına döner / Starts over from the setup screen
        self._shown_bar().hide()
        self._on_new_job()
        self.restore_window()

    def open_output(self) -> None:
        # Çıktı dosyasını sistem varsayılanıyla açar / Opens the output with the system default app
        path = self._output_path() or self._shown_bar().output_path()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def toggle_pause(self) -> None:
        # Yüzen çubuktaki duraklat/devam düğmesi / The bar's pause-resume toggle
        if self._shown_bar().is_paused():
            self._on_pause()
        else:
            self._on_resume()
