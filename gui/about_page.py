import tkinter as tk
from tkinter import ttk

class AboutPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        # Scrollable container for about content
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=20)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 1. Main Title Header
        title_lbl = ttk.Label(
            scrollable_frame,
            text="Endpoint File Integrity Monitor & Anti-Tamper Console",
            font=("Arial", 15, "bold")
        )
        title_lbl.pack(anchor="w", pady=(0, 15))

        # 2. Description Card
        desc_card = ttk.LabelFrame(scrollable_frame, text=" Overview & Cryptographic Fingerprinting ", padding=12)
        desc_card.pack(fill="x", pady=6)

        desc_text = (
            "What It Does:\n"
            "This application provides real-time and scheduled endpoint integrity verification for critical files "
            "and directories. It computes cryptographic snapshots of files to form a trusted baseline, then verifies "
            "live disk state against this baseline to immediately detect tampering, unauthorized alterations, or ransomware.\n\n"
            "How SHA-256 Fingerprinting Works:\n"
            "Every monitored file is processed in binary chunks through the secure SHA-256 algorithm (Secure Hash "
            "Algorithm, 256-bit). This produces a deterministic 64-character hexadecimal digest unique to that file's exact contents. "
            "Due to the avalanche effect in cryptographic hash functions, changing even a single character or byte in a file "
            "drastically alters the resulting hash, making tampering immediately detectable."
        )
        ttk.Label(desc_card, text=desc_text, font=("Arial", 9), wraplength=950, justify="left").pack(anchor="w")

        # 3. Technologies Used Card
        tech_card = ttk.LabelFrame(scrollable_frame, text=" Core Technologies ", padding=12)
        tech_card.pack(fill="x", pady=6)

        tech_text = (
            "• Python 3: Core programming language and runtime environment\n"
            "• Tkinter: Native graphical user interface framework with synchronized diff viewing\n"
            "• SQLite: Embedded ACID-compliant database for baseline snapshots, run history, and settings\n"
            "• hashlib: Cryptographic SHA-256 hashing engine for secure file integrity signatures\n"
            "• difflib: Unified and side-by-side delta analysis engine (SequenceMatcher)"
        )
        ttk.Label(tech_card, text=tech_text, font=("Arial", 9), justify="left").pack(anchor="w")

        # 4. Integrity Result States Card
        states_card = ttk.LabelFrame(scrollable_frame, text=" Integrity Status States ", padding=12)
        states_card.pack(fill="x", pady=6)

        states_text = (
            "• Unchanged: File hash and content strictly match the trusted baseline snapshot.\n"
            "• Modified: File hash differs from baseline; changes can be reviewed in the side-by-side diff view.\n"
            "• Created: New file discovered in the monitored path that was not part of the baseline snapshot.\n"
            "• Deleted: File registered in the baseline is missing or has been removed from disk."
        )
        ttk.Label(states_card, text=states_text, font=("Arial", 9), justify="left").pack(anchor="w")

        # 5. Limitations Card
        limit_card = ttk.LabelFrame(scrollable_frame, text=" Limitations & Threat Model ", padding=12)
        limit_card.pack(fill="x", pady=6)

        limit_text = (
            "Important Security Notice:\n"
            "An attacker with direct database access or local administrator/root privileges could alter stored hashes "
            "and baseline records directly in the SQLite database without detection. In enterprise production environments, "
            "the baseline repository database must be protected with strict filesystem access controls, verified against remote "
            "digital signatures, or stored on an append-only remote server to prevent local tamper."
        )
        ttk.Label(limit_card, text=limit_text, font=("Arial", 9), wraplength=950, foreground="#990000", justify="left").pack(anchor="w")

        # 6. Team Members Card
        team_card = ttk.LabelFrame(scrollable_frame, text=" Project Team Members ", padding=12)
        team_card.pack(fill="x", pady=6)

        team_text = (
            "=======================================================================\n"
            "PROJECT TEAM MEMBERS:\n"
            "1. [ Ayush Kumar Sharma / RA2511030010445 ]\n"
            "2. [ Shivangi Kumari / RA2511030010465 ]\n"
            "3. [ Deepayan Roy / RA2511030010494 ]\n"
            "======================================================================="
        )
        ttk.Label(team_card, text=team_text, font=("Courier", 10, "bold"), foreground="#1e222d", justify="left").pack(anchor="w")
