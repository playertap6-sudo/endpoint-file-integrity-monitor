"""
gui/theme.py
Visual theme definitions and color constants for the FIM Console,
including canvas rendering, document view, and the spider crawler.
"""

# ── Canvas & Document View Colors ───────────────────────────────────────────
CANVAS_BG         = "#0d1117"     # Deep dark charcoal / navy
LINE_ROW_HOVER    = "#161b22"     # Subtle row tint
TEXT_FILENAME     = "#e2e8f0"     # Light grey readable font for filenames
TEXT_PATH         = "#64748b"     # Dimmer slate text for directory paths
TEXT_MUTED        = "#475569"     # Very dim text for row numbers
CANVAS_GUIDE_LINE = "#21262d"     # Separator guide line between rows

# ── Status Colors ───────────────────────────────────────────────────────────
STATUS_COLORS = {
    "Modified":  "#ef4444",       # Red highlight scribble
    "Created":   "#22c55e",       # Green highlight scribble
    "Deleted":   "#eab308",       # Yellow / amber highlight scribble
    "Unchanged": "#94a3b8",       # Neutral grey
}

# ── Spider Palette ──────────────────────────────────────────────────────────
SPIDER_BODY       = "#7c3aed"     # Cyber purple cephalothorax & abdomen
SPIDER_HEAD       = "#8b5cf6"     # Slightly lighter head
SPIDER_LEGS       = "#c4b5fd"     # Light lavender jointed legs
SPIDER_EYES       = "#ef4444"     # Glowing red ocular dots
SPIDER_PEDIPALP   = "#a78bfa"     # Front feelers / pedipalps
SPIDER_ACCENT     = "#a78bfa"     # Subtle outline accent for body

# ── Chrome & Buttons ────────────────────────────────────────────────────────
SIDEBAR_BG        = "#1e222d"
HEADER_BG         = "#1e222d"
HEADER_TEXT       = "#ffffff"
TOTALS_TEXT       = "#94a3b8"
BUTTON_BG         = "#2563eb"
BUTTON_FG         = "#ffffff"
BUTTON_ACTIVE_BG  = "#1d4ed8"
SECONDARY_BTN_BG  = "#334155"
SECONDARY_BTN_FG  = "#ffffff"
