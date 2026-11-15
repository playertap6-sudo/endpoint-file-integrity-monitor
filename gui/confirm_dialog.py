"""
gui/confirm_dialog.py
Reusable modal confirmation dialog using Tkinter Toplevel.
Replaces native messagebox.askyesno and askyesnocancel to prevent blocking Tk timers
and to ensure the procedural spider overlay and background tasks continue animating.
"""

import tkinter as tk
from tkinter import ttk


class ConfirmDialog(tk.Toplevel):
    """
    Modal confirmation dialog that runs on Tkinter's event loop via wait_window(),
    allowing background timers (including the spider animation) to continue running.
    """

    def __init__(self, parent, title: str, message: str, has_cancel: bool = False):
        super().__init__(parent)
        self.parent = parent
        self.result = None  # True (Yes), False (No), None (Cancel / Closed)
        self.has_cancel = has_cancel

        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg="#ffffff")

        # Container frame
        container = tk.Frame(self, bg="#ffffff", padx=20, pady=20)
        container.pack(fill="both", expand=True)

        # Header icon + title
        header_frame = tk.Frame(container, bg="#ffffff")
        header_frame.pack(fill="x", pady=(0, 12))

        icon_lbl = tk.Label(
            header_frame,
            text="⚠️" if "warning" in title.lower() or "delete" in title.lower() or "restore" in title.lower() else "❓",
            font=("Segoe UI Emoji", 20),
            bg="#ffffff"
        )
        icon_lbl.pack(side="left", padx=(0, 10))

        title_lbl = tk.Label(
            header_frame,
            text=title,
            font=("Arial", 11, "bold"),
            fg="#1e222d",
            bg="#ffffff"
        )
        title_lbl.pack(side="left", anchor="w")

        # Message body
        msg_lbl = tk.Label(
            container,
            text=message,
            font=("Arial", 10),
            fg="#334155",
            bg="#ffffff",
            justify="left",
            wraplength=420
        )
        msg_lbl.pack(fill="both", expand=True, pady=(0, 18), anchor="w")

        # Separator line
        sep = tk.Frame(container, height=1, bg="#e2e8f0")
        sep.pack(fill="x", pady=(0, 15))

        # Button bar
        btn_frame = tk.Frame(container, bg="#ffffff")
        btn_frame.pack(fill="x")

        # Cancel button (if requested)
        if self.has_cancel:
            cancel_btn = tk.Button(
                btn_frame,
                text="Cancel",
                font=("Arial", 9),
                bg="#f1f5f9",
                fg="#475569",
                activebackground="#e2e8f0",
                relief="flat",
                padx=14,
                pady=5,
                cursor="hand2",
                command=self._on_cancel
            )
            cancel_btn.pack(side="right", padx=(6, 0))

        # No button
        no_btn = tk.Button(
            btn_frame,
            text="No",
            font=("Arial", 9),
            bg="#f1f5f9",
            fg="#475569",
            activebackground="#e2e8f0",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._on_no
        )
        no_btn.pack(side="right", padx=(6, 0))

        # Yes button
        yes_btn = tk.Button(
            btn_frame,
            text="Yes",
            font=("Arial", 9, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=5,
            cursor="hand2",
            command=self._on_yes
        )
        yes_btn.pack(side="right")

        # Key bindings
        self.bind("<Return>", lambda e: self._on_yes())
        self.bind("<Escape>", lambda e: self._on_cancel() if self.has_cancel else self._on_no())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Center on parent window
        self._center_on_parent()

        # Set modal grab
        self.focus_set()
        yes_btn.focus_set()
        self.grab_set()

    def _center_on_parent(self):
        try:
            self.update_idletasks()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()

            w = max(420, self.winfo_reqwidth())
            h = max(180, self.winfo_reqheight())

            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _on_yes(self):
        self.result = True
        self.destroy()

    def _on_no(self):
        self.result = False
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

    def _on_close(self):
        self.result = None if self.has_cancel else False
        self.destroy()


def ask_yes_no(parent, title: str, message: str) -> bool:
    """
    Shows a non-blocking Tkinter modal Yes/No confirmation dialog.
    Returns True for Yes, False for No or dialog dismissal.
    """
    dialog = ConfirmDialog(parent, title, message, has_cancel=False)
    parent.wait_window(dialog)
    return bool(dialog.result is True)


def ask_yes_no_cancel(parent, title: str, message: str):
    """
    Shows a non-blocking Tkinter modal Yes/No/Cancel confirmation dialog.
    Returns True for Yes, False for No, None for Cancel or dialog dismissal.
    """
    dialog = ConfirmDialog(parent, title, message, has_cancel=True)
    parent.wait_window(dialog)
    return dialog.result
