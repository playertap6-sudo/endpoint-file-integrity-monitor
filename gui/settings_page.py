import tkinter as tk
from tkinter import ttk


class SettingsPage(tk.Frame):
    def __init__(self, parent, app, db_manager):
        super().__init__(parent)
        self.app = app
        self.db = db_manager

        self.threshold_var = tk.IntVar(value=5)
        self.interval_var = tk.IntVar(value=2)
        self.continuous_var = tk.BooleanVar(value=True)
        self.auto_response_var = tk.BooleanVar(value=True)
        # Keep alias auto_kill_var pointing to auto_response_var for legacy callers
        self.auto_kill_var = self.auto_response_var
        self.sound_effects_var = tk.BooleanVar(value=True)
        self.spider_anim_var = tk.BooleanVar(value=True)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        container = ttk.LabelFrame(self, text=" System Configuration & Preferences ", padding=20)
        container.pack(fill="both", expand=True, padx=25, pady=25)

        title_lbl = ttk.Label(
            container,
            text="Settings",
            font=("Arial", 14, "bold")
        )
        title_lbl.pack(anchor="w", pady=(0, 20))

        # Alert Threshold Field
        thresh_frame = ttk.Frame(container, padding=5)
        thresh_frame.pack(fill="x", pady=5)

        ttk.Label(
            thresh_frame,
            text="Ransomware Alert Threshold (changed files):",
            font=("Arial", 10, "bold"),
            width=42
        ).pack(side="left")

        self.threshold_spin = ttk.Spinbox(
            thresh_frame,
            from_=1,
            to=1000,
            textvariable=self.threshold_var,
            width=8
        )
        self.threshold_spin.pack(side="left", padx=10)

        ttk.Label(
            thresh_frame,
            text="(Range: 1 – 1000 files)",
            font=("Arial", 9),
            foreground="#666666"
        ).pack(side="left")

        # Auto-scan Interval Field
        interval_frame = ttk.Frame(container, padding=5)
        interval_frame.pack(fill="x", pady=5)

        ttk.Label(
            interval_frame,
            text="Default Auto-scan Interval (seconds):",
            font=("Arial", 10, "bold"),
            width=42
        ).pack(side="left")

        self.interval_spin = ttk.Spinbox(
            interval_frame,
            from_=2,
            to=60,
            textvariable=self.interval_var,
            width=8
        )
        self.interval_spin.pack(side="left", padx=10)

        ttk.Label(
            interval_frame,
            text="(Range: 2 – 60 seconds)",
            font=("Arial", 9),
            foreground="#666666"
        ).pack(side="left")

        # Continuous Monitoring Checkbox (default ON)
        cont_frame = ttk.Frame(container, padding=5)
        cont_frame.pack(fill="x", pady=5)

        ttk.Label(
            cont_frame,
            text="Continuous monitoring:",
            font=("Arial", 10, "bold"),
            width=42
        ).pack(side="left")

        self.continuous_cb = ttk.Checkbutton(
            cont_frame,
            variable=self.continuous_var,
            text="Enabled  (auto-start on app launch and baseline)"
        )
        self.continuous_cb.pack(side="left", padx=10)

        # Automatic response (kill and restore) - default ON
        auto_resp_frame = ttk.Frame(container, padding=5)
        auto_resp_frame.pack(fill="x", pady=5)

        ttk.Label(
            auto_resp_frame,
            text="Automatic response (kill and restore):",
            font=("Arial", 10, "bold"),
            width=42
        ).pack(side="left")

        self.auto_response_cb = ttk.Checkbutton(
            auto_resp_frame,
            variable=self.auto_response_var,
            text="Enabled  (automated 6-step detection, kill, and restore pipeline)"
        )
        self.auto_response_cb.pack(side="left", padx=10)

        # Aliases for backwards compatibility
        self.auto_kill_cb = self.auto_response_cb

        # Sound Effects Checkbox
        sound_frame = ttk.Frame(container, padding=5)
        sound_frame.pack(fill="x", pady=5)

        ttk.Label(
            sound_frame,
            text="Sound effects:",
            font=("Arial", 10, "bold"),
            width=42
        ).pack(side="left")

        self.sound_cb = ttk.Checkbutton(
            sound_frame,
            variable=self.sound_effects_var,
            text="Enabled  (synthesized audio chimes & alerts)"
        )
        self.sound_cb.pack(side="left", padx=10)

        # Spider Animation Checkbox
        spider_frame = ttk.Frame(container, padding=5)
        spider_frame.pack(fill="x", pady=5)

        ttk.Label(
            spider_frame,
            text="Spider animation:",
            font=("Arial", 10, "bold"),
            width=42
        ).pack(side="left")

        self.spider_cb = ttk.Checkbutton(
            spider_frame,
            variable=self.spider_anim_var,
            text="Enabled  (transparent procedural spider overlay)"
        )
        self.spider_cb.pack(side="left", padx=10)

        # Action Buttons and Status
        btn_frame = ttk.Frame(container, padding=10)
        btn_frame.pack(anchor="w", pady=(20, 10))

        save_btn = ttk.Button(
            btn_frame,
            text="💾 Save Settings",
            command=self.save_settings
        )
        save_btn.pack(side="left", padx=(0, 15))

        self.test_sound_btn = ttk.Button(
            btn_frame,
            text="🔊 Test Sounds",
            command=self.test_sounds
        )
        self.test_sound_btn.pack(side="left", padx=(0, 15))

        self.status_lbl = ttk.Label(
            btn_frame,
            text="",
            font=("Arial", 10, "bold"),
            foreground="#155724"
        )
        self.status_lbl.pack(side="left")

    def test_sounds(self):
        """Sequentially plays each synthesized audio tone with short intervals."""
        if hasattr(self.app, "sounds") and not self.app.sounds.is_ready():
            self.status_lbl.config(text="Sound system initializing...")
            self.after(300, self.test_sounds)
            return

        sound_sequence = [
            ("alert", "Alert Chime"),
            ("suspect_found", "Suspect Found"),
            ("process_killed", "Process Killed"),
            ("scan_done", "Scan Click"),
            ("baseline_done", "Baseline Confirmation"),
            ("restore_done", "Restore Chime"),
        ]
        self.status_lbl.config(text="🔊 Testing audio chimes...")

        def _play_step(idx):
            if idx < len(sound_sequence):
                s_key, s_name = sound_sequence[idx]
                self.status_lbl.config(text=f"🔊 Playing: {s_name} ({idx+1}/{len(sound_sequence)})")
                if hasattr(self.app, "sounds"):
                    self.app.sounds.play(s_key)
                self.after(550, lambda: _play_step(idx + 1))
            else:
                self.status_lbl.config(text="✓ Audio test complete!")

        _play_step(0)

    def load_settings(self):
        """Loads settings from database into input fields."""
        try:
            thresh = int(self.db.get_setting("alert_threshold", 5))
            self.threshold_var.set(thresh)
        except (ValueError, TypeError):
            self.threshold_var.set(5)

        try:
            interval = int(self.db.get_setting("auto_scan_interval", 2))
            self.interval_var.set(interval)
        except (ValueError, TypeError):
            self.interval_var.set(2)

        # Load continuous monitoring setting (default ON)
        cont_val = self.db.get_setting("continuous_monitoring", "true")
        self.continuous_var.set(str(cont_val).lower() != "false")

        # Load automatic response setting (default ON, replaces auto_kill)
        auto_resp_val = self.db.get_setting("auto_response", "")
        if auto_resp_val == "":
            auto_resp_val = self.db.get_setting("auto_kill_suspect", "true")
        self.auto_response_var.set(str(auto_resp_val).lower() != "false")

        # Load sound effects setting (default ON)
        sound_val = self.db.get_setting("sound_effects", "true")
        self.sound_effects_var.set(str(sound_val).lower() != "false")

        # Load spider animation setting (default ON)
        spider_val = self.db.get_setting("spider_animation", "true")
        self.spider_anim_var.set(str(spider_val).lower() != "false")

    def save_settings(self):
        """Persists settings and applies them immediately across the app."""
        try:
            threshold_val = int(self.threshold_var.get())
            if threshold_val < 1:
                threshold_val = 1
            elif threshold_val > 1000:
                threshold_val = 1000
        except (ValueError, tk.TclError):
            self.app.show_toast("Please enter a valid numeric threshold between 1 and 1000.", "error")
            return

        try:
            interval_val = int(self.interval_var.get())
            if interval_val < 2:
                interval_val = 2
            elif interval_val > 60:
                interval_val = 60
        except (ValueError, tk.TclError):
            self.app.show_toast("Please enter a valid numeric interval between 2 and 60.", "error")
            return

        cont_val = bool(self.continuous_var.get())
        auto_resp_val = bool(self.auto_response_var.get())
        sound_val = bool(self.sound_effects_var.get())
        spider_val = bool(self.spider_anim_var.get())

        # Commit to database
        self.db.set_setting("alert_threshold", str(threshold_val))
        self.db.set_setting("auto_scan_interval", str(interval_val))
        self.db.set_setting("continuous_monitoring", "true" if cont_val else "false")
        self.db.set_setting("auto_response", "true" if auto_resp_val else "false")
        self.db.set_setting("auto_kill_suspect", "true" if auto_resp_val else "false")
        self.db.set_setting("sound_effects", "true" if sound_val else "false")
        self.db.set_setting("spider_animation", "true" if spider_val else "false")

        # Apply directly to Dashboard, Sounds, and Spider Overlay without restart
        self.app.apply_settings(
            threshold=threshold_val,
            interval=interval_val,
            sound_effects=sound_val,
            spider_animation=spider_val,
            continuous_monitoring=cont_val,
            auto_response=auto_resp_val
        )

        self.status_lbl.config(text="✓ Settings saved and applied successfully!")
        self.app.show_toast("Settings saved and applied successfully.", "success")
