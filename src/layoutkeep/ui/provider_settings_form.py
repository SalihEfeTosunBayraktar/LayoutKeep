"""Form widgets and layout for the provider settings dialog.

Sağlayıcı ayar diyaloğunun form alanlarını ve düzenini yöneten yardımcı sınıf.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui.api_key_helpers import load_api_key_for
from layoutkeep.ui.endpoint_tree import EndpointTree
from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.job import ProviderConfig
from layoutkeep.ui.model_catalog import ModelSelectorWidget

KIND_OPENAI = "openai"
KIND_DEEPL = "deepl"
KIND_FAKE = "fake"

#: Buttons here are small; the accent reads as a control rather than as decoration.
_ICON_COLOR = "#2563eb"


class ProviderSettingsForm:
    """Builds and owns the input widgets used by ProviderSettingsDialog.

    Sağlayıcı ayar diyaloğunun kullandığı girdi bileşenlerini kuran ve
    barındıran yardımcı. Düzen ve OK/Cancel düğmelerini de içerir.
    """

    def __init__(self, parent: QWidget, config: ProviderConfig) -> None:
        self._parent = parent
        self._config = config
        self._build_controls()
        self._build_layout()
        self._apply_initial_kind(config.kind)

    # -- public widgets exposed to the dialog ----------------------------
    @property
    def endpoint_list(self) -> EndpointTree:
        return self._endpoint_list

    @property
    def profile_name(self) -> QLineEdit:
        return self._profile_name

    @property
    def group(self) -> QComboBox:
        return self._group

    @property
    def new_profile_btn(self) -> QPushButton:
        return self._new_profile_btn

    @property
    def test_btn(self) -> QPushButton:
        return self._test_btn

    @property
    def save_btn(self) -> QPushButton:
        return self._save_btn

    @property
    def kind_combo(self) -> QComboBox:
        return self._kind_combo

    @property
    def base_url(self) -> QLineEdit:
        return self._base_url

    @property
    def model(self) -> ModelSelectorWidget:
        return self._model

    @property
    def refresh_btn(self) -> QPushButton:
        return self._refresh_btn

    @property
    def api_key(self) -> QLineEdit:
        return self._api_key

    @property
    def timeout(self) -> QLineEdit:
        return self._timeout

    @property
    def status(self) -> QLabel:
        return self._status

    @property
    def buttons(self) -> QDialogButtonBox:
        return self._buttons

    # -- construction ----------------------------------------------------
    def _build_controls(self) -> None:
        cfg = self._config
        self._endpoint_list = EndpointTree(self._parent)
        self._profile_name = QLineEdit("Varsayılan", self._parent)

        # Editable: a group is just a heading the user invents, so typing a new one has to be
        # the same gesture as picking an existing one.
        self._group = QComboBox(self._parent)
        self._group.setEditable(True)
        self._group.lineEdit().setPlaceholderText("opsiyonel - örn. Yerel, Bulut")

        self._new_profile_btn = QPushButton("+ Yeni Uç Nokta", self._parent)
        # One line: the same three sentences wrapped to three and took as much room as two
        # endpoints in the list above them.
        self._hint = QLabel("Sürükleyerek sırala ve grupla · sağ tık: sil, yeniden adlandır", self._parent)
        self._hint.setProperty("class", "muted")
        self._hint.setWordWrap(True)
        self._hint.setProperty("class", "muted")
        self._test_btn = QPushButton("Test Et", self._parent)
        self._test_btn.setIcon(get_svg_icon("zap", color=_ICON_COLOR, size=16))
        self._test_btn.setToolTip("Uc noktayi kaydetmeden dener")
        self._save_btn = QPushButton("Kaydet", self._parent)
        self._save_btn.setIcon(get_svg_icon("check", color=_ICON_COLOR, size=16))

        self._kind_combo = QComboBox(self._parent)
        self._kind_combo.addItem(
            "OpenAI-uyumlu sunucu (LM Studio, Ollama, ...)",
            KIND_OPENAI,
        )
        self._kind_combo.addItem(
            "DeepL (çeviri servisi - model seçimi yok)",
            KIND_DEEPL,
        )
        self._kind_combo.addItem(
            "Test / Sahte Çevirici ([dil] İşareti Ekle)",
            KIND_FAKE,
        )

        self._base_url = QLineEdit(cfg.base_url, self._parent)
        self._model = ModelSelectorWidget(self._parent)
        if cfg.model:
            self._model.addItem(cfg.model)

        self._refresh_btn = QPushButton("Modelleri Getir", self._parent)
        self._api_key = QLineEdit(load_api_key_for(cfg.base_url), self._parent)
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("opsiyonel - LM Studio/Ollama gerektirmez")

        self._timeout = QLineEdit(
            str(cfg.timeout) if cfg.timeout else "", self._parent
        )
        self._timeout.setPlaceholderText("boş = otomatik (öneriliyor)")
        self._status = QLabel("", self._parent)
        self._status.setWordWrap(True)

    def _build_layout(self) -> None:
        # Saved endpoints, in the order they were arranged, above the form that edits them -
        # the arrangement is only meaningful if it is visible while you change it.
        saved_box = QGroupBox("Kayıtlı Uç Noktalar", self._parent)
        saved_layout = QVBoxLayout(saved_box)
        saved_layout.addWidget(self._endpoint_list)
        saved_layout.addWidget(self._hint)
        saved_layout.addWidget(self._new_profile_btn)
        self._saved_box = saved_box

        form = QFormLayout()
        # Kept so rows can be hidden per provider kind: a DeepL profile has no base URL and no
        # model, and showing empty boxes for them invites the user to fill in values that are
        # then ignored.
        self._form_layout = form
        form.addRow("Uç Nokta Adı", self._profile_name)
        form.addRow("Grup", self._group)
        form.addRow("Sağlayıcı Türü", self._kind_combo)
        form.addRow("Base URL", self._base_url)
        form.addRow("Model", self._model)
        form.addRow("", self._refresh_btn)
        form.addRow("API Anahtarı", self._api_key)
        form.addRow("Zaman Aşımı (sn)", self._timeout)
        form.addRow("", self._status)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self._parent,
        )

        action_row = QHBoxLayout()
        action_row.addWidget(self._test_btn)
        action_row.addWidget(self._save_btn)
        action_row.addStretch()
        action_row.addWidget(self._buttons)

        edit_box = QGroupBox("Uç Nokta Ayarları", self._parent)
        edit_layout = QVBoxLayout(edit_box)
        edit_layout.addLayout(form)

        # The fields scroll rather than growing the dialog past the bottom of the screen: at
        # 854 pixels tall on an 816-pixel screen, Save and OK were simply not on it.
        scroller = QScrollArea(self._parent)
        scroller.setWidgetResizable(True)
        scroller.setWidget(edit_box)
        scroller.setFrameShape(QScrollArea.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        outer = QVBoxLayout(self._parent)
        outer.addWidget(self._saved_box)
        outer.addWidget(scroller, 1)
        outer.addLayout(action_row)

    def set_row_visible(self, field: QWidget, visible: bool) -> None:
        """Show or hide a form row, label included."""
        self._form_layout.setRowVisible(field, visible)

    def _apply_initial_kind(self, kind: str) -> None:
        idx_kind = self._kind_combo.findData(kind)
        if idx_kind >= 0:
            self._kind_combo.setCurrentIndex(idx_kind)
