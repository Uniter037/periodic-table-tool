"""Dependency-free light ttk theme. Scale is a user-selected multiplier (1 = 10 pt)."""
from __future__ import annotations

import math
import tkinter.font as tkfont
from tkinter import ttk

PALETTE = {
    "background": "#f3f4f6", "surface": "#ffffff", "text": "#1f2937",
    "muted": "#6b7280", "border": "#d1d5db", "hover": "#e5e7eb",
    "accent": "#2563eb", "accent_hover": "#1d4ed8", "disabled": "#9ca3af",
    "preview": "#e5e7eb",
}


def apply_theme(root):
    """Install the light palette; return the root's ttk Style. Safe to reapply."""
    style = ttk.Style(root)
    style.theme_use("clam")
    p = PALETTE
    root.configure(background=p["background"])
    style.configure(".", background=p["background"], foreground=p["text"],
                    bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"],
                    troughcolor=p["hover"], selectbackground=p["accent"],
                    selectforeground=p["surface"])
    for name in ("Card.TFrame", "Toolbar.TFrame", "Card.TLabel", "Toolbar.TLabel"):
        style.configure(name, background=p["surface"])
    for name in ("Muted.TLabel", "Status.TLabel"):
        style.configure(name, foreground=p["muted"])
    style.configure("Header.TLabel", foreground=p["text"])
    style.configure("Status.TLabel", padding=(10, 6))
    style.configure("TButton", background=p["surface"], padding=(10, 6), relief="flat")
    style.map("TButton", background=[("disabled", p["background"]), ("pressed", p["border"]),
                                    ("active", p["hover"])],
              foreground=[("disabled", p["disabled"])])
    for name in ("Accent.TButton", "Export.TButton"):
        style.configure(name, background=p["accent"], foreground=p["surface"])
        style.map(name, background=[("disabled", p["border"]),
                                   ("pressed", p["accent_hover"]), ("active", p["accent_hover"])],
                  foreground=[("disabled", p["muted"]), ("!disabled", p["surface"])])
    style.configure("Section.TButton", anchor="w", padding=(10, 8))
    for name in ("TEntry", "TCombobox", "TSpinbox", "Treeview"):
        style.configure(name, fieldbackground=p["surface"], background=p["surface"], padding=4)
        style.map(name, fieldbackground=[("disabled", p["background"]), ("readonly", p["surface"])],
                  foreground=[("disabled", p["disabled"])])
    style.map("Treeview", background=[("selected", p["accent"])],
              foreground=[("selected", p["surface"])])
    style.configure("Treeview.Heading", background=p["background"], padding=(8, 7))
    style.configure("TNotebook", tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", padding=(12, 7))
    style.map("TNotebook.Tab", background=[("selected", p["surface"])],
              foreground=[("selected", p["accent"])])
    style.configure("TLabelframe", borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", foreground=p["muted"])
    style.configure("TProgressbar", background=p["accent"])
    apply_scale(root, None, getattr(root, "_theme_scale", 1.0))
    return style


def apply_scale(root, font, scale=1.0):
    """Set user UI scale without changing Tk DPI or preview image magnification.

    Updates and returns the supplied Font (or creates one when None).
    No automatic scale selection is performed.
    """
    scale = float(scale)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("UI scale must be a finite positive multiplier")
    families = set(tkfont.families(root))
    family = next((name for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI")
                   if name in families), tkfont.nametofont("TkDefaultFont", root=root).cget("family"))
    fonts = getattr(root, "_theme_fonts", None)
    if fonts is None:
        fonts = {key: tkfont.Font(root=root) for key in ("body", "header", "section")}
        root._theme_fonts = fonts
    if font is not None:
        fonts["body"] = font
    size = max(1, round(10 * scale))
    fonts["body"].configure(family=family, size=size)
    fonts["header"].configure(family=family, size=max(1, round(15 * scale)), weight="bold")
    fonts["section"].configure(family=family, size=size, weight="bold")
    style = ttk.Style(root)
    style.configure(".", font=fonts["body"])
    style.configure("Header.TLabel", font=fonts["header"])
    style.configure("Section.TButton", font=fonts["section"])
    style.configure("Treeview", rowheight=max(20, round(28 * scale),
                                             fonts['body'].metrics('linespace') + 8))
    root.option_add("*Font", str(fonts["body"]))
    root._theme_scale = scale
    return fonts["body"]
