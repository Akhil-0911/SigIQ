"""ttk theming to match the reference look: light, clean, Windows-desktop-app
style -- white panels on a soft gray background, one blue accent, subtle
borders, no gradients."""
import tkinter as tk
from tkinter import ttk

BG = "#f0f1f3"
PANEL = "#ffffff"
BORDER = "#d7dade"
TEXT = "#1b1f27"
MUTED = "#5b6472"
ACCENT = "#2456c4"
ACCENT_HOVER = "#1c46a8"
GOOD = "#1a7f4a"
BAD = "#b3261e"

FONT_FAMILY = "Segoe UI"


def apply_theme(root: tk.Tk):
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", font=(FONT_FAMILY, 9), background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL, relief="solid", borderwidth=1, bordercolor=BORDER)
    style.configure("Inner.TFrame", background=PANEL, relief="flat", borderwidth=0)
    style.configure("Header.TFrame", background=PANEL)

    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT_FAMILY, 9))
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=(FONT_FAMILY, 9))
    style.configure("Title.TLabel", background=PANEL, foreground=TEXT, font=(FONT_FAMILY, 18, "bold"))
    style.configure("Subtitle.TLabel", background=PANEL, foreground=MUTED, font=(FONT_FAMILY, 9))
    style.configure("Brand.TLabel", background=PANEL, foreground=ACCENT, font=(FONT_FAMILY, 14, "bold"))
    style.configure("SectionHeading.TLabel", background=PANEL, foreground=TEXT, font=(FONT_FAMILY, 11, "bold"))

    style.configure("TEntry", fieldbackground="white", bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.configure("TCombobox", fieldbackground="white", bordercolor=BORDER)

    style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
    style.configure("TRadiobutton", background=PANEL, foreground=TEXT)

    style.configure("TLabelframe", background=PANEL, bordercolor=BORDER, relief="solid")
    style.configure("TLabelframe.Label", background=PANEL, foreground=MUTED, font=(FONT_FAMILY, 9))

    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                     font=(FONT_FAMILY, 9, "bold"), padding=(14, 7), borderwidth=0)
    style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#c6cad2")],
              foreground=[("disabled", "#8a8f98")])

    style.configure("Secondary.TButton", background="#e8eaed", foreground=TEXT,
                     padding=(10, 6), borderwidth=1, bordercolor=BORDER)
    style.map("Secondary.TButton", background=[("active", "#dcdfe3")])

    style.configure("TNotebook", background=PANEL, bordercolor=BORDER, tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", background="#e8eaed", foreground=MUTED,
                     padding=(14, 7), font=(FONT_FAMILY, 9))
    style.map("TNotebook.Tab",
              background=[("selected", PANEL)],
              foreground=[("selected", ACCENT)])

    style.configure("Treeview", background="white", fieldbackground="white",
                     foreground=TEXT, rowheight=24, bordercolor=BORDER, borderwidth=1)
    style.configure("Treeview.Heading", background="#f4f5f7", foreground=MUTED,
                     font=(FONT_FAMILY, 9, "bold"), relief="flat")
    style.map("Treeview", background=[("selected", "#dce6fb")], foreground=[("selected", TEXT)])

    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e8eaed",
                     bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)

    return style
