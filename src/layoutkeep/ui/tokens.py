"""Design tokens for LayoutKeep UI: color palettes, typography, and spacing constants.

LayoutKeep arayüzü için tasarım token'ları (renk paletleri, tipografi ve boşluk sabitleri).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColorPalette:
    # Arayüz renk paleti tanımları / UI color palette definitions
    background: str
    surface: str
    surface_hover: str
    surface_active: str
    border: str
    border_focus: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    error: str
    dropzone_bg: str
    dropzone_border: str


# Açık tema renk paleti / Light theme color palette
LIGHT_PALETTE = ColorPalette(
    background="#f8fafc",
    surface="#ffffff",
    surface_hover="#f1f5f9",
    surface_active="#e2e8f0",
    border="#cbd5e1",
    border_focus="#3b82f6",
    text_primary="#0f172a",
    text_secondary="#334155",
    text_muted="#64748b",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_text="#ffffff",
    success="#16a34a",
    warning="#ea580c",
    error="#dc2626",
    dropzone_bg="#f1f5f9",
    dropzone_border="#94a3b8",
)

# Koyu tema renk paleti / Dark theme color palette
DARK_PALETTE = ColorPalette(
    background="#0f172a",
    surface="#1e293b",
    surface_hover="#334155",
    surface_active="#475569",
    border="#334155",
    border_focus="#60a5fa",
    text_primary="#f8fafc",
    text_secondary="#cbd5e1",
    text_muted="#94a3b8",
    accent="#3b82f6",
    accent_hover="#60a5fa",
    accent_text="#ffffff",
    success="#22c55e",
    warning="#f97316",
    error="#ef4444",
    dropzone_bg="#1e293b",
    dropzone_border="#475569",
)

FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
FONT_FAMILY_MONO = 'Consolas, Monaco, "Courier New", monospace'
RADIUS_SM = "4px"
RADIUS_MD = "8px"
RADIUS_LG = "12px"
