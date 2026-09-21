"""A collapsible section: a clickable header that shows and hides its body.

The settings dialog groups its entries by the `group` field of the tunable registry, and a flat list
of a hundred rows is a wall. Hiding a group also takes its rows out of the layout's size hint, which
is what makes the dialog open at a readable size instead of as wide as its longest warning text.

One class, one job: the header toggle and the body's visibility. It knows nothing about settings.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLayout, QToolButton, QVBoxLayout, QWidget

from layoutkeep.ui.theme import ThemeManager


class CollapsibleSection(QWidget):
    """A titled section whose body the user can fold away."""

    def __init__(self, title: str, *, expanded: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._body = QWidget(self)
        self._body_layout: QLayout | None = None

        self._toggle = QToolButton(self)
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setSizePolicy(self._toggle.sizePolicy().horizontalPolicy(), self._toggle.sizePolicy().verticalPolicy())
        self._toggle.clicked.connect(self._on_toggled)
        palette = ThemeManager.current_palette()
        self._toggle.setStyleSheet(
            "QToolButton {"
            f"  color: {palette.text_primary};"
            "  font-weight: 700;"
            "  border: none;"
            "  padding: 6px 0;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)
        layout.addWidget(self._toggle)
        layout.addWidget(self._body)

        self._body.setVisible(expanded)

    def set_body_layout(self, body_layout: QLayout) -> None:
        """Install the layout that holds the section's rows."""
        self._body_layout = body_layout
        self._body.setLayout(body_layout)

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(expanded)
        self._body.setVisible(expanded)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def _on_toggled(self, checked: bool) -> None:
        """Fold or unfold the body. One method, one job: keep the arrow, the body and the state in step."""
        self.set_expanded(checked)
