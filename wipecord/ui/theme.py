"""Discord's dark palette.

Colour values are taken from Discord's dark theme so the window sits next to
the real client without clashing. Discord's own typeface (gg sans) is not
redistributable, so the stack falls back to the system UI font, which is what
the Discord client itself falls back to on Windows.
"""

from __future__ import annotations

# Surfaces, darkest to lightest.
BG_DARKEST = "#1e1f22"  # inputs, log console
BG_SIDEBAR = "#2b2d31"  # settings column
BG_MAIN = "#313338"     # content column
BG_CARD = "#383a40"     # raised elements, hover

# Brand and intent.
BLURPLE = "#5865f2"
BLURPLE_HOVER = "#4752c4"
DANGER = "#da373c"
DANGER_HOVER = "#a12d2f"
SUCCESS = "#23a559"
WARNING = "#f0b132"

# Text.
TEXT = "#dbdee1"
TEXT_MUTED = "#949ba4"
TEXT_HEADING = "#f2f3f5"
TEXT_LINK = "#00a8fc"

BORDER = "#3f4147"

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"

# Log line colours, keyed by the Level values in events.py.
LEVEL_COLOURS = {
    "info": TEXT_MUTED,
    "success": SUCCESS,
    "warn": WARNING,
    "error": DANGER,
    "wait": TEXT_LINK,
    "delete": TEXT,
}
