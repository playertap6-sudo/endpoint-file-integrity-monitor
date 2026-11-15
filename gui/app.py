import os
import time
import queue
import threading
import psutil
import tkinter as tk
from tkinter import ttk
from gui.confirm_dialog import ask_yes_no
from core.backup_manager import BackupManager
from core.process_monitor import ProcessMonitor
from gui.dashboard_page import DashboardPage
from gui.history_page import HistoryPage
from gui.backup_page import BackupPage
from gui.settings_page import SettingsPage
from gui.about_page import AboutPage
from gui.spider_overlay import SpiderOverlay
from gui.sounds import SoundManager


class App(tk.Frame):
    def __init__(self, root, engine, db_manager, backup_manager=None):
        super().__init__(root)
        self.root = root
        self.engine = engine
        self.db = db_manager
        self.backup_manager = backup_manager or BackupManager(db_manager, engine=engine)
        self.sounds = SoundManager(self.db)
        self.process_monitor = ProcessMonitor(
            on_kill_success=lambda pid, name: self.post_to_ui(self._on_process_killed_event)
        )

        if not self.engine.backup_manager:
            self.engine.backup_manager = self.backup_manager
        self.backup_manager.engine = self.engine

        self.alert_triggered = False
        self.active_page_name = "Dashboard"
        self.nav_buttons = {}
        self.pages = {}

        # Thread-safe UI dispatch queue (processed by root.after)
        self._ui_queue = queue.Queue()
        self._ui_queue_timer = None

        # Tracks whether a background investigation scan or pipeline is running
        self._investigation_running = False
        self._pipeline_running = False
        self._last_restore_time = 0.0
        self._pipeline_runs_timestamps = []

        self.pack(fill="both", expand=True)
        self.setup_ui()

        # Start UI queue processor via root.after()
        self._schedule_ui_queue()

        # Transparent procedural spider overlay (starts automatically)
        self.spider = SpiderOverlay(self.root, self, self.db)

        # Check if continuous monitoring should auto-start at launch
        self.root.after(200, self._check_auto_start_monitoring)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def setup_ui(self):
        # 0. Global Ransomware Alert Banner
        self.banner = tk.Frame(self, bg="#cc0000", pady=4)

        # --- Top row of banner: alert text + action buttons ---
        banner_top = tk.Frame(self.banner, bg="#cc0000")
        banner_top.pack(fill="x")

        self.banner_lbl = tk.Label(
            banner_top,
            text="",
            bg="#cc0000",
            fg="#ffffff",
            font=("Arial", 11, "bold")
        )
        self.banner_lbl.pack(side="left", padx=(15, 12))

        self.banner_restore_btn = tk.Button(
            banner_top,
            text="🚨 Restore Now",
            font=("Arial", 9, "bold"),
            bg="#ffffff",
            fg="#cc0000",
            activebackground="#ffe6e6",
            activeforeground="#cc0000",
            relief="raised",
            cursor="hand2",
            padx=10,
            pady=2,
            command=self.restore_from_banner
        )
        self.banner_restore_btn.pack(side="left", padx=4)

        self.banner_investigate_btn = tk.Button(
            banner_top,
            text="🔍 Investigate Processes",
            font=("Arial", 9, "bold"),
            bg="#ffffff",
            fg="#1e222d",
            activebackground="#f0f0f0",
            activeforeground="#1e222d",
            relief="raised",
            cursor="hand2",
            padx=10,
            pady=2,
            command=self.open_process_investigator
        )
        self.banner_investigate_btn.pack(side="left", padx=4)

        # Scanning label shown while background investigation is running
        self.banner_scan_lbl = tk.Label(
            banner_top,
            text="",
            bg="#cc0000",
            fg="#ffe0e0",
            font=("Arial", 9, "italic")
        )
        self.banner_scan_lbl.pack(side="left", padx=8)

        # --- Inline suspects mini-table inside the banner ---
        self.banner_suspects_frame = tk.Frame(self.banner, bg="#aa0000", pady=3)
        # Will be packed/unpacked dynamically in _update_banner_suspects()

        self.banner_suspects_tree = ttk.Treeview(
            self.banner_suspects_frame,
            columns=("pid", "name", "cmdline"),
            show="headings",
            height=3
        )
        self.banner_suspects_tree.heading("pid", text="PID")
        self.banner_suspects_tree.heading("name", text="Process")
        self.banner_suspects_tree.heading("cmdline", text="Command Line")
        self.banner_suspects_tree.column("pid", width=60, anchor="center")
        self.banner_suspects_tree.column("name", width=140, anchor="w")
        self.banner_suspects_tree.column("cmdline", width=600, anchor="w")
        self.banner_suspects_tree.pack(fill="x", padx=10, pady=2)

        # Main horizontal layout container
        self.body_container = tk.Frame(self)
        self.body_container.pack(fill="both", expand=True)

        # 1. Left Dark Navigation Sidebar
        self.sidebar = tk.Frame(self.body_container, bg="#1e222d", width=190)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand_frame = tk.Frame(self.sidebar, bg="#1e222d", pady=18)
        brand_frame.pack(fill="x")
        tk.Label(
            brand_frame,
            text="🛡️ FIM CONSOLE",
            font=("Arial", 11, "bold"),
            fg="#ffffff",
            bg="#1e222d"
        ).pack(anchor="center")

        sep = tk.Frame(self.sidebar, height=1, bg="#2a303c")
        sep.pack(fill="x", padx=10, pady=(0, 10))

        # 2. Right Content Area
        self.content_area = tk.Frame(self.body_container, bg="#f5f6f8")
        self.content_area.pack(side="left", fill="both", expand=True)

        # Instantiate all sub-pages
        self.pages["Dashboard"] = DashboardPage(self.content_area, self, self.engine, self.db)
        self.pages["Scan History"] = HistoryPage(self.content_area, self.db)
        self.pages["Backup & Restore"] = BackupPage(self.content_area, self, self.backup_manager)
        self.pages["Settings"] = SettingsPage(self.content_area, self, self.db)
        self.pages["About"] = AboutPage(self.content_area)

        # Navigation menu items
        nav_items = [
            ("Dashboard", "📊 Dashboard"),
            ("Scan History", "📜 Scan History"),
            ("Backup & Restore", "💾 Backup & Restore"),
            ("Settings", "⚙️ Settings"),
            ("About", "ℹ️ About"),
        ]

        for key, label in nav_items:
            btn = tk.Button(
                self.sidebar,
                text=label,
                font=("Arial", 10, "bold"),
                bg="#1e222d",
                fg="#cbd5e1",
                activebackground="#2a303c",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=15,
                pady=10,
                anchor="w",
                cursor="hand2",
                command=lambda k=key: self.show_page(k)
            )
            btn.pack(fill="x", padx=8, pady=3)
            self.nav_buttons[key] = btn

        # 3. Bottom Status Bar
        self.status_bar = tk.Frame(self, bg="#1e222d", height=24)
        self.status_bar.pack(side="bottom", fill="x")

        self.status_bar_lbl = tk.Label(
            self.status_bar,
            text="Monitoring: IDLE",
            font=("Arial", 9, "bold"),
            bg="#1e222d",
            fg="#94a3b8"
        )
        self.status_bar_lbl.pack(side="left", padx=15, pady=2)

        self.toast_lbl = tk.Label(
            self.status_bar,
            text="",
            font=("Arial", 9, "bold"),
            bg="#1e222d",
            fg="#ffffff"
        )
        self.toast_lbl.pack(side="right", padx=15, pady=2)
        self._toast_timer = None

        self.show_page("Dashboard")

    def show_toast(self, message: str, kind: str = "info", duration_ms: int = 3000):
        """Displays a non-blocking toast in the status bar that auto-hides after duration_ms (default 3s)."""
        if not hasattr(self, "toast_lbl"):
            return
        colors = {
            "info": "#38bdf8",     # Sky blue
            "success": "#4ade80",  # Green
            "warning": "#facc15",  # Amber / Yellow
            "error": "#f87171",    # Red
        }
        fg = colors.get(kind, "#ffffff")
        prefix = {
            "info": "ℹ ",
            "success": "✓ ",
            "warning": "⚠ ",
            "error": "✕ ",
        }.get(kind, "")

        self.toast_lbl.config(text=f"{prefix}{message}", fg=fg)

        if self._toast_timer:
            try:
                self.root.after_cancel(self._toast_timer)
            except Exception:
                pass
            self._toast_timer = None
        self._toast_timer = self.root.after(duration_ms, self._clear_toast)

    def _clear_toast(self):
        self._toast_timer = None
        if hasattr(self, "toast_lbl"):
            self.toast_lbl.config(text="")

    def set_status_monitoring(self, active: bool):
        """Updates status bar label indicating whether continuous monitoring is active."""
        if hasattr(self, "status_bar_lbl"):
            if active:
                self.status_bar_lbl.config(text="Monitoring: ACTIVE", fg="#22c55e")
            else:
                self.status_bar_lbl.config(text="Monitoring: IDLE", fg="#94a3b8")

    def _check_auto_start_monitoring(self):
        """Auto-starts monitoring at app launch if a baseline exists for the saved target."""
        dashboard = self.pages.get("Dashboard")
        if not dashboard:
            return
        target = dashboard.target_dir.get().strip()
        continuous = str(self.db.get_setting("continuous_monitoring", "true")).lower() != "false"
        if continuous and target and os.path.exists(target):
            if self.db.has_baseline_for_target(target):
                dashboard.auto_scan_var.set(True)
                dashboard.toggle_auto_scan()

    def _schedule_ui_queue(self):
        """Schedules UI queue processing via root.after()."""
        try:
            if not self.winfo_exists():
                return
            self._ui_queue_timer = self.root.after(30, self._process_ui_queue)
        except Exception:
            pass

    def _process_ui_queue(self):
        """Processes thread-safe dispatches on the main thread via root.after()."""
        try:
            if not self.winfo_exists():
                return
            while not self._ui_queue.empty():
                try:
                    fn, args, kwargs = self._ui_queue.get_nowait()
                    fn(*args, **kwargs)
                except Exception as e:
                    print(f"[UI Queue Exec Error] {e}")
        finally:
            if self.winfo_exists():
                self._schedule_ui_queue()

    def post_to_ui(self, fn, *args, **kwargs):
        """Thread-safe dispatch to main UI thread, processed via root.after()."""
        self._ui_queue.put((fn, args, kwargs))

    # ------------------------------------------------------------------
    # Page switching
    # ------------------------------------------------------------------

    def show_page(self, page_name):
        """Switches active page in the content area."""
        for name, page in self.pages.items():
            if hasattr(page, "on_leave"):
                page.on_leave()
            page.pack_forget()

        target_page = self.pages.get(page_name)
        if target_page:
            target_page.pack(fill="both", expand=True)
            if hasattr(target_page, "refresh"):
                target_page.refresh()
            if hasattr(target_page, "refresh_stats"):
                target_page.refresh_stats()
            if hasattr(target_page, "load_settings"):
                target_page.load_settings()
            if hasattr(target_page, "on_enter"):
                target_page.on_enter()

        self.active_page_name = page_name
        self.update_sidebar()

        # Resume spider overlay on page switch
        if hasattr(self, "spider"):
            self.spider.resume()

    def update_sidebar(self):
        """Highlights the active sidebar navigation button."""
        for name, btn in self.nav_buttons.items():
            if name == self.active_page_name:
                btn.config(bg="#2563eb", fg="#ffffff")
            else:
                btn.config(bg="#1e222d", fg="#cbd5e1")

    def apply_settings(self, threshold=None, interval=None, sound_effects=None, spider_animation=None, continuous_monitoring=None, auto_response=None):
        """Propagates updated settings immediately across the app without restart."""
        dashboard = self.pages.get("Dashboard")
        if dashboard and hasattr(dashboard, "apply_settings"):
            dashboard.apply_settings(threshold, interval)
        if sound_effects is not None and hasattr(self, "sounds"):
            self.sounds.set_enabled(sound_effects)
        if spider_animation is not None and hasattr(self, "spider"):
            self.spider.set_enabled(spider_animation)

    # ------------------------------------------------------------------
    # Threshold check + Automated Response Pipeline
    # ------------------------------------------------------------------

    def check_threshold(self, changed_count):
        """
        Global ransomware threshold checker; banner remains visible across all pages.
        When automatic response is ON (default): executes automated 6-step background pipeline.
        When automatic response is OFF: shows manual confirmation and action buttons.
        """
        threshold = 5
        dashboard = self.pages.get("Dashboard")
        if dashboard and hasattr(dashboard, "threshold_var"):
            try:
                threshold = int(dashboard.threshold_var.get())
            except (ValueError, tk.TclError):
                threshold = 5

        if changed_count >= threshold:
            now = time.time()
            # Loop protection rule 1: wait 3 seconds after a restore before next alert can start pipeline
            if now - self._last_restore_time < 3.0:
                return

            # Loop protection rule 2: if pipeline has run 3 times within 1 minute, halt auto-response
            self._pipeline_runs_timestamps = [t for t in self._pipeline_runs_timestamps if now - t < 60.0]
            if len(self._pipeline_runs_timestamps) >= 3:
                self.banner_lbl.config(
                    text="⚠ Repeated attacks: manual action needed"
                )
                if not self.banner.winfo_manager():
                    self.banner.pack(side="top", fill="x", before=self.body_container)
                self.banner_restore_btn.pack(side="left", padx=4)
                self.banner_investigate_btn.pack(side="left", padx=4)
                self.db.log_activity("ALERT_TRIGGERED", "Repeated attacks: manual action needed (3 attacks within 1 minute)")
                return

            # Check if automatic response is enabled (default ON)
            auto_response_enabled = str(self.db.get_setting("auto_response", "true")).lower() != "false"
            if auto_response_enabled:
                if not self._pipeline_running:
                    self._start_automatic_pipeline(changed_count)
                return

            # Manual mode (when automatic response is OFF):
            self.banner_lbl.config(
                text=f"⚠ POSSIBLE RANSOMWARE ACTIVITY: {changed_count} files changed (limit {threshold})"
            )
            if not self.banner.winfo_manager():
                self.banner.pack(side="top", fill="x", before=self.body_container)
            self.banner_restore_btn.pack(side="left", padx=4)
            self.banner_investigate_btn.pack(side="left", padx=4)

            if not self.alert_triggered:
                self.alert_triggered = True
                self.sounds.play("alert")
                self.spider.notify("alert")
                self.db.log_activity(
                    "ALERT_TRIGGERED",
                    f"Ransomware alert triggered: {changed_count} files changed (threshold {threshold})"
                )
                self.show_toast(
                    f"Possible ransomware activity detected: {changed_count} files changed!",
                    kind="error",
                    duration_ms=4000
                )

            self._apply_alert_scan_speed(active=True)
            self._start_background_investigation()

        else:
            if not self._pipeline_running:
                if self.banner.winfo_manager():
                    self.banner.pack_forget()
                if self.alert_triggered:
                    self.spider.notify("alert_cleared")
                self.alert_triggered = False
                self._apply_alert_scan_speed(active=False)

    def _start_automatic_pipeline(self, changed_count):
        """
        Runs the 6-step automated response pipeline in a background thread:
        Detected -> Investigating -> Process killed -> Restoring files -> Restored and verified -> Back to monitoring.
        """
        if self._pipeline_running:
            return
        self._pipeline_running = True
        self._pipeline_runs_timestamps.append(time.time())
        self.alert_triggered = True

        dashboard = self.pages.get("Dashboard")
        target = dashboard.target_dir.get().strip() if dashboard else ""

        if not self.banner.winfo_manager():
            self.banner.pack(side="top", fill="x", before=self.body_container)

        # Hide manual action buttons during automated pipeline
        self.banner_restore_btn.pack_forget()
        self.banner_investigate_btn.pack_forget()

        def _pipeline_worker():
            try:
                # Step 1: Detected
                step1_text = f"Step 1/6: Detected ransomware activity ({changed_count} changed files)"
                self.post_to_ui(self._set_banner_step, step1_text, sound="alert", spider="alert")
                self.db.log_activity("PIPELINE_STEP_1", step1_text)
                time.sleep(0.8)

                # Step 2: Investigating
                step2_text = "Step 2/6: Investigating suspect processes in background..."
                self.post_to_ui(self._set_banner_step, step2_text)
                self.db.log_activity("PIPELINE_STEP_2", step2_text)

                suspects = []
                try:
                    suspects = self.process_monitor.find_suspects(target)
                except Exception as e:
                    print(f"[Pipeline Investigation Error] {e}")

                self.post_to_ui(self._update_banner_suspects, suspects)

                high_conf = [s for s in suspects if s.get("high_confidence", False)]

                # Step 3: Process killed
                if high_conf:
                    suspect = high_conf[0]
                    pid = suspect["pid"]
                    name = suspect["name"]

                    step3_text = f"Step 3/6: killing {name} PID {pid}"
                    self.post_to_ui(self._set_banner_step, step3_text)
                    self.db.log_activity("PIPELINE_STEP_3", f"Attempting kill on {name} PID {pid}")

                    # Attempt kill (with built-in protected list and own PID safety checks)
                    success, msg = self.process_monitor.kill_process(pid)

                    # Check if process is confirmed gone
                    is_gone = not psutil.pid_exists(pid)
                    if not is_gone:
                        # Retry kill once
                        time.sleep(0.5)
                        self.post_to_ui(self._set_banner_step, f"Step 3/6: Retrying kill for {name} PID {pid}...")
                        success, msg = self.process_monitor.kill_process(pid)
                        is_gone = not psutil.pid_exists(pid)

                    if not is_gone:
                        # Kill failed after retry: show "Manual action needed" and do NOT restore
                        fail_text = f"Step 3/6: Kill failed for {name} PID {pid}. Manual action needed"
                        self.post_to_ui(self._set_banner_step, fail_text, show_buttons=True)
                        self.db.log_activity("PIPELINE_FAILED", fail_text)
                        self._pipeline_running = False
                        return

                    # Confirmed terminated!
                    killed_text = f"Step 3/6: Process {name} PID {pid} killed and confirmed gone"
                    self.post_to_ui(self._set_banner_step, killed_text, sound="process_killed", spider="process_killed")
                    self.db.log_activity("PIPELINE_STEP_3", killed_text)
                    time.sleep(0.8)
                else:
                    # Restore only after 5 seconds if no suspect was found
                    wait_text = "Step 2/6: No suspect found. Waiting 5 seconds before restore..."
                    self.post_to_ui(self._set_banner_step, wait_text)
                    time.sleep(5.0)

                # Step 4: Restoring files
                step4_text = "Step 4/6: Restoring modified and deleted files from baseline backup..."
                self.post_to_ui(self._set_banner_step, step4_text)
                self.db.log_activity("PIPELINE_STEP_4", step4_text)

                restored, verified, failed = self.backup_manager.restore_files(target)
                self.db.log_activity("PIPELINE_STEP_4", f"Files restored: {restored} restored, {verified} verified, {failed} failed")
                time.sleep(0.5)

                # Step 5: Restored and verified
                step5_text = f"Step 5/6: Restored {restored} files ({verified} verified)"
                self.post_to_ui(self._set_banner_step, step5_text, sound="restore_done", spider="restore_done")
                self.db.log_activity("PIPELINE_STEP_5", step5_text)
                self._last_restore_time = time.time()
                time.sleep(1.0)

                # Step 6: Back to monitoring
                step6_text = "Step 6/6: Threat neutralized. Back to monitoring"
                self.post_to_ui(self._set_banner_step, step6_text, spider="idle")
                self.db.log_activity("PIPELINE_STEP_6", step6_text)

                # Trigger re-scan on main thread to clear alert
                self.post_to_ui(self._pipeline_finish_rescan, target)

            except Exception as e:
                err_text = f"Pipeline error: {e}"
                print(f"[Pipeline Exception] {e}")
                self.post_to_ui(self._set_banner_step, f"Error: {e}. Manual action needed", show_buttons=True)
                self.db.log_activity("PIPELINE_ERROR", err_text)
                self._pipeline_running = False

        t = threading.Thread(target=_pipeline_worker, daemon=True)
        t.start()

    def _set_banner_step(self, text, sound=None, spider=None, show_buttons=False):
        """Thread-safe UI callback to update banner message and trigger sounds/spider."""
        self.banner_lbl.config(text=text)
        if show_buttons:
            self.banner_restore_btn.pack(side="left", padx=4)
            self.banner_investigate_btn.pack(side="left", padx=4)
        if sound and hasattr(self, "sounds"):
            self.sounds.play(sound)
        if spider and hasattr(self, "spider"):
            self.spider.notify(spider)

    def _pipeline_finish_rescan(self, target):
        """Called on main thread when pipeline completes to refresh state and clear alert."""
        dashboard = self.pages.get("Dashboard")
        if dashboard and hasattr(dashboard, "run_verification"):
            dashboard.run_verification(is_auto=True)

        matches = self.engine.verify_integrity(target)
        changed = sum(1 for m in matches if m[2] in ("Modified", "Created", "Deleted"))
        if changed == 0:
            self.alert_triggered = False
            self.spider.notify("alert_cleared")
            self.spider.notify("idle")
            self.banner_lbl.config(text="✓ Threat resolved — all files verified. Monitoring active.")
            self.root.after(2500, self._hide_banner_if_safe)
        self._pipeline_running = False

    def _hide_banner_if_safe(self):
        """Hides banner if alert is cleared and pipeline is not running."""
        if not self.alert_triggered and not self._pipeline_running:
            if self.banner.winfo_manager():
                self.banner.pack_forget()

    def _apply_alert_scan_speed(self, active):
        """
        While an alert is active, override the auto-scan interval to 1 second.
        When cleared, restore the user-configured interval.
        """
        dashboard = self.pages.get("Dashboard")
        if not dashboard or not hasattr(dashboard, "auto_scan_var"):
            return
        if not dashboard.auto_scan_var.get():
            return  # Auto-scan not running; nothing to adjust

        if active:
            # Only override if not already at 1 s to avoid loop churn
            if hasattr(dashboard, "_alert_speed_active") and dashboard._alert_speed_active:
                return
            dashboard._alert_speed_active = True
            # Cancel existing timer and reschedule at 1 s
            if dashboard.auto_timer_id is not None:
                self.root.after_cancel(dashboard.auto_timer_id)
                dashboard.auto_timer_id = None
            dashboard.auto_timer_id = self.root.after(1000, dashboard.run_auto_scan)
        else:
            dashboard._alert_speed_active = False
            # Normal rescheduling resumes through run_auto_scan()

    # ------------------------------------------------------------------
    # Background process investigation
    # ------------------------------------------------------------------

    def _start_background_investigation(self):
        """
        Launches find_suspects() in a daemon background thread.
        Results are pushed back to the UI thread via root.after().
        Shows a 'Scanning...' label in the banner while running.
        If auto-kill is ON, kills high-confidence suspects automatically.
        """
        if self._investigation_running:
            return  # Already scanning

        dashboard = self.pages.get("Dashboard")
        target = ""
        if dashboard and hasattr(dashboard, "target_dir"):
            target = dashboard.target_dir.get().strip()

        if not target or not os.path.exists(target):
            return

        self._investigation_running = True
        self.banner_scan_lbl.config(text="🔍 Scanning processes…")

        def _worker():
            try:
                suspects = self.process_monitor.find_suspects(target)
            except Exception:
                suspects = []
            # Push results back to main thread
            self.post_to_ui(self._on_investigation_done, suspects, target)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _on_process_killed_event(self):
        """Called on main thread when any process termination succeeds."""
        if hasattr(self, "sounds"):
            self.sounds.play("process_killed")
        if hasattr(self, "spider"):
            self.spider.notify("process_killed")

    def _on_investigation_done(self, suspects, target):
        """Called from root.after() when the background scan finishes."""
        self._investigation_running = False
        self.banner_scan_lbl.config(text="")

        # Update the inline mini-table in the banner
        self._update_banner_suspects(suspects)

        if suspects:
            if hasattr(self, "sounds"):
                self.sounds.play("suspect_found")
            if hasattr(self, "spider"):
                self.spider.notify("suspect_found", {"suspects": suspects})

        # Auto-kill: only for high-confidence (Stage-1) suspects when setting is ON
        auto_kill_enabled = str(self.db.get_setting("auto_kill_suspect", "false")).lower() == "true"
        if auto_kill_enabled and suspects:
            high_conf = [s for s in suspects if s.get("high_confidence", False)]
            for suspect in high_conf:
                pid = suspect["pid"]
                name = suspect["name"]
                success, msg = self.process_monitor.kill_process(pid)
                if success:
                    self.db.log_activity(
                        "PROCESS_KILLED",
                        f"AUTO-KILL: Terminated '{name}' (PID: {pid}) — {msg}"
                    )
                    self.sounds.play("process_killed")
                    self.spider.notify("process_killed")
                    # After auto-kill, trigger restore automatically
                    self._auto_restore_after_kill(target)
                else:
                    self.db.log_activity(
                        "PROCESS_KILLED",
                        f"AUTO-KILL FAILED for '{name}' (PID: {pid}): {msg}"
                    )

    def _auto_restore_after_kill(self, target):
        """Automatically restores files from backup after an auto-kill."""
        try:
            restored, verified, failed = self.backup_manager.restore_files(target)
            self.db.log_activity(
                "FILES_RESTORED",
                f"Auto-restore after kill: {restored} restored ({verified} verified, {failed} failed) for {target}"
            )
            self.sounds.play("restore_done")
            self.spider.notify("restore_done")
            # Re-run scan to refresh dashboard and potentially clear the alert
            dashboard = self.pages.get("Dashboard")
            if dashboard and hasattr(dashboard, "run_verification"):
                dashboard.run_verification(is_auto=True)
        except Exception as e:
            self.db.log_activity("FILES_RESTORED", f"Auto-restore error: {e}")

    def _update_banner_suspects(self, suspects):
        """
        Shows or hides the small suspects table inside the alert banner.
        Called from the main thread only.
        """
        # Clear existing rows
        for row in self.banner_suspects_tree.get_children():
            self.banner_suspects_tree.delete(row)

        if suspects and self.banner.winfo_manager():
            for s in suspects:
                confidence = " ⚡" if s.get("high_confidence") else ""
                self.banner_suspects_tree.insert(
                    "", "end",
                    values=(s["pid"], s["name"] + confidence, s["cmdline"])
                )
            # Show the suspects frame
            if not self.banner_suspects_frame.winfo_manager():
                self.banner_suspects_frame.pack(fill="x")
        else:
            # Hide the suspects frame
            if self.banner_suspects_frame.winfo_manager():
                self.banner_suspects_frame.pack_forget()

    # ------------------------------------------------------------------
    # Banner action: Restore Now
    # ------------------------------------------------------------------

    def restore_from_banner(self):
        """Emergency restoration triggered directly from the ransomware alert banner."""
        dashboard = self.pages.get("Dashboard")
        target = ""
        if dashboard and hasattr(dashboard, "target_dir"):
            target = dashboard.target_dir.get().strip()

        if not target or not os.path.exists(target):
            self.show_toast("Please select a valid target path on the Dashboard first.", "error")
            return

        confirm = ask_yes_no(
            self,
            "Confirm Emergency Restore",
            f"⚠ EMERGENCY RECOVERY\n\nDo you want to restore all Modified and Deleted files for:\n{target}?\n\n"
            "This will revert modified files back to the baseline and recover deleted files.\n"
            "Created files will NOT be deleted."
        )
        if hasattr(self, "spider"):
            self.spider.resume()

        if not confirm:
            return

        restored, verified, failed = self.backup_manager.restore_files(target)

        self.db.log_activity(
            "FILES_RESTORED",
            f"Emergency restore: {restored} files restored ({verified} verified, {failed} failed) for {target}"
        )
        self.sounds.play("restore_done")
        self.spider.notify("restore_done")

        if dashboard and hasattr(dashboard, "run_verification"):
            dashboard.run_verification()

        backup_page = self.pages.get("Backup & Restore")
        if backup_page and hasattr(backup_page, "refresh_stats"):
            backup_page.refresh_stats()

        self.show_toast(
            f"Restore complete: {restored} restored ({verified} verified, {failed} failed)",
            kind="success" if failed == 0 else "warning"
        )

    # ------------------------------------------------------------------
    # Manual Process Investigator window
    # ------------------------------------------------------------------

    def open_process_investigator(self):
        """
        Opens the full Process Investigator Toplevel window.
        The initial scan runs in a background thread to keep the UI responsive.
        """
        dashboard = self.pages.get("Dashboard")
        target = ""
        if dashboard and hasattr(dashboard, "target_dir"):
            target = dashboard.target_dir.get().strip()

        win = tk.Toplevel(self.root)
        win.title("Process Investigator — Suspect Process Inspection")
        win.geometry("900x500")

        # Top Information
        top_frame = ttk.Frame(win, padding=10)
        top_frame.pack(fill="x")
        ttk.Label(top_frame, text="Active Process Investigator", font=("Arial", 12, "bold")).pack(side="left")
        ttk.Label(
            top_frame,
            text=f"Monitored Target: {target if target else 'No target specified'}",
            font=("Courier", 9)
        ).pack(side="right")

        # Notice/Status banner
        status_banner = tk.Label(
            win,
            text="",
            font=("Arial", 10, "bold"),
            bg="#f8f9fa",
            fg="#666666",
            pady=6
        )
        status_banner.pack(fill="x", padx=10, pady=(0, 5))

        # Suspects table
        table_frame = ttk.LabelFrame(
            win,
            text=" Suspect Processes (⚡ = high-confidence cmd-line match) ",
            padding=8
        )
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)

        cols = ("pid", "name", "cmdline", "open_files")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        tree.heading("pid", text="PID")
        tree.heading("name", text="Process Name")
        tree.heading("cmdline", text="Command Line")
        tree.heading("open_files", text="Open Monitored Files")

        tree.column("pid", width=70, anchor="center")
        tree.column("name", width=160, anchor="w")
        tree.column("cmdline", width=460, anchor="w")
        tree.column("open_files", width=140, anchor="center")

        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        scroll_x.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        # Action Buttons frame
        btn_frame = ttk.Frame(win, padding=10)
        btn_frame.pack(fill="x")

        refresh_btn = ttk.Button(btn_frame, text="🔄 Refresh")
        refresh_btn.pack(side="left", padx=5)
        kill_btn = ttk.Button(btn_frame, text="☠️ Kill Selected Process")
        kill_btn.pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Close", command=win.destroy).pack(side="right", padx=5)

        def _populate_tree(suspects):
            """Fill the treeview (must be called from the main thread)."""
            for row in tree.get_children():
                tree.delete(row)

            if not suspects:
                status_banner.config(
                    text="No processes with open file handles found in monitored path.",
                    bg="#d4edda",
                    fg="#155724"
                )
            else:
                status_banner.config(
                    text=f"⚠ {len(suspects)} suspect process(es) found!  ⚡ = high-confidence (cmd-line match)",
                    bg="#ffcccc",
                    fg="#990000"
                )
                for s in suspects:
                    confidence = " ⚡" if s.get("high_confidence") else ""
                    tree.insert(
                        "", "end",
                        iid=str(s["pid"]),
                        values=(s["pid"], s["name"] + confidence, s["cmdline"], s["open_files"])
                    )

        def load_suspects_bg():
            """Start a background scan and push results to the tree via root.after()."""
            # Reset cache so this always gives fresh results
            self.process_monitor.invalidate_cache()

            refresh_btn.config(state="disabled", text="⏳ Scanning…")
            status_banner.config(text="Scanning for suspect processes…", bg="#fff3cd", fg="#856404")
            for row in tree.get_children():
                tree.delete(row)

            if not target or not os.path.exists(target):
                status_banner.config(
                    text="Target path is not set or does not exist on disk.",
                    bg="#fff3cd",
                    fg="#856404"
                )
                refresh_btn.config(state="normal", text="🔄 Refresh")
                return

            def _worker():
                try:
                    suspects = self.process_monitor.find_suspects(target)
                except Exception:
                    suspects = []
                win.after(0, lambda: _done(suspects))

            def _done(suspects):
                if not win.winfo_exists():
                    return
                refresh_btn.config(state="normal", text="🔄 Refresh")
                _populate_tree(suspects)

            threading.Thread(target=_worker, daemon=True).start()

        def kill_selected():
            selected = tree.selection()
            if not selected:
                self.show_toast("Please select a suspect process from the table first.", "warning")
                return

            pid = int(selected[0])
            item = tree.item(selected[0], "values")
            p_name = item[1] if len(item) > 1 else "Unknown"

            confirm = ask_yes_no(
                win,
                "Confirm Process Termination",
                f"Are you sure you want to terminate this process?\n\nProcess Name: {p_name}\nPID: {pid}"
            )
            if hasattr(self, "spider"):
                self.spider.resume()

            if not confirm:
                return

            success, msg = self.process_monitor.kill_process(pid)
            if success:
                self.db.log_activity("PROCESS_KILLED", f"Terminated process '{p_name}' (PID: {pid})")
                self.sounds.play("process_killed")
                self.spider.notify("process_killed")
                self.show_toast(f"Terminated process '{p_name}' (PID: {pid})", "success")
            else:
                self.show_toast(f"Termination failed: {msg}", "error")

            load_suspects_bg()

        refresh_btn.config(command=load_suspects_bg)
        kill_btn.config(command=kill_selected)

        # Initial scan in background
        load_suspects_bg()
