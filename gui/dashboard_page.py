import os
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog
from gui.confirm_dialog import ask_yes_no, ask_yes_no_cancel
import difflib
from core.hasher import Hasher

class DashboardPage(tk.Frame):
    def __init__(self, parent, app, engine, db_manager):
        super().__init__(parent)
        self.app = app
        self.engine = engine
        self.db = db_manager
        
        self.target_dir = tk.StringVar()
        self.card_labels = {}
        self.auto_timer_id = None
        self.prev_auto_changed_count = None
        # Set by App.check_threshold() to indicate alert-speed mode is active
        self._alert_speed_active = False
        self._clearing_selection = False

        # Live auto-diff tracking & manual selection pause (30s)
        self._user_selected_until = 0.0
        self._known_threat_hashes = {}

        # Load last target path from settings
        saved_target = self.db.get_setting("last_target_path", "")
        if saved_target and os.path.exists(saved_target):
            self.target_dir.set(saved_target)

        # Track target changes to auto-persist
        self.target_dir.trace_add("write", self._on_target_changed)

        # Load initial threshold and interval settings from database defaults (default interval 2s)
        init_threshold = 5
        try:
            init_threshold = int(self.db.get_setting("alert_threshold", 5))
        except (ValueError, TypeError):
            init_threshold = 5

        init_interval = 2
        try:
            init_interval = int(self.db.get_setting("auto_scan_interval", 2))
        except (ValueError, TypeError):
            init_interval = 2

        self.threshold_var = tk.IntVar(value=init_threshold)
        self.auto_interval_var = tk.IntVar(value=init_interval)
        self.auto_scan_var = tk.BooleanVar(value=False)

        self.setup_ui()

    def _on_target_changed(self, *args):
        val = self.target_dir.get().strip()
        if val:
            try:
                self.db.set_setting("last_target_path", val)
            except Exception:
                pass

    def setup_ui(self):
        # 1. Top Section: Target Environment Configuration
        self.top_frame = ttk.LabelFrame(self, text=" Target Environment Configuration ", padding=10)
        self.top_frame.pack(fill="x", padx=15, pady=10)
        
        ttk.Label(self.top_frame, text="Target Path (File/Folder):").pack(side="left", padx=5)
        ttk.Entry(self.top_frame, textvariable=self.target_dir, width=60).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(self.top_frame, text="Browse...", command=self.browse_directory).pack(side="left", padx=5)
        
        # 2. Control Action Buttons & Automation Panel
        btn_frame = ttk.Frame(self, padding=5)
        btn_frame.pack(fill="x", padx=15, pady=5)
        
        self.baseline_btn = ttk.Button(btn_frame, text="🛡️ Generate Baseline Matrix", command=self.run_baseline)
        self.baseline_btn.pack(side="left", padx=4)

        ttk.Button(btn_frame, text="🔍 Execute Integrity Verification Check", command=self.run_verification).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✅ Accept Changes", command=self.accept_changes).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="📜 Scan History", command=lambda: self.app.show_page("Scan History")).pack(side="left", padx=4)

        # Ransomware Alert Threshold Spinbox
        ttk.Label(btn_frame, text="Alert threshold (changed files):").pack(side="left", padx=(8, 2))
        self.threshold_spinbox = ttk.Spinbox(
            btn_frame,
            from_=1,
            to=1000,
            textvariable=self.threshold_var,
            width=4
        )
        self.threshold_spinbox.pack(side="left", padx=2)

        # Auto-scan controls
        self.auto_scan_cb = ttk.Checkbutton(
            btn_frame,
            text="Auto-scan",
            variable=self.auto_scan_var,
            command=self.toggle_auto_scan
        )
        self.auto_scan_cb.pack(side="left", padx=(10, 2))

        self.auto_status_lbl = ttk.Label(btn_frame, text="Auto-scan: OFF", font=("Arial", 9, "bold"))
        self.auto_status_lbl.pack(side="left", padx=4)

        ttk.Label(btn_frame, text="every (seconds):").pack(side="left", padx=(4, 2))
        self.auto_interval_spinbox = ttk.Spinbox(
            btn_frame,
            from_=2,
            to=60,
            textvariable=self.auto_interval_var,
            width=3
        )
        self.auto_interval_spinbox.pack(side="left", padx=2)

        # Summary Cards: Row of 5 small labelled boxes
        cards_frame = ttk.Frame(self, padding=5)
        cards_frame.pack(fill="x", padx=15, pady=(0, 5))

        card_configs = [
            ("Total", "#f8f9fa", "#333333"),
            ("Unchanged", "#ffffff", "#333333"),
            ("Modified", "#ffcccc", "#990000"),
            ("Created", "#d4edda", "#155724"),
            ("Deleted", "#fff3cd", "#856404"),
        ]

        for title, bg_col, fg_col in card_configs:
            card = tk.Frame(cards_frame, bg=bg_col, relief="groove", bd=1, padx=10, pady=4)
            card.pack(side="left", fill="x", expand=True, padx=4)

            lbl_title = tk.Label(card, text=title, bg=bg_col, fg=fg_col, font=("Arial", 8, "bold"))
            lbl_title.pack()

            lbl_count = tk.Label(card, text="0", bg=bg_col, fg=fg_col, font=("Arial", 13, "bold"))
            lbl_count.pack()

            self.card_labels[title] = lbl_count

        # 3. Bottom Section: Split Workspace Panel
        workspace_frame = ttk.Frame(self)
        workspace_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        # --- Left Panel: Threats and Clean Files (Stacked Vertically) ---
        left_panel = ttk.Frame(workspace_frame)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))

        columns = ("filepath", "status")

        # Top Table: Threats (Modified, Created, Deleted)
        self.threats_frame = ttk.LabelFrame(left_panel, text=" ⚠ Threats (0) ", padding=5)
        self.threats_frame.pack(side="top", fill="both", expand=True, pady=(0, 5))

        self.threats_tree = ttk.Treeview(self.threats_frame, columns=columns, show="headings", height=7)
        self.threats_tree.heading("filepath", text="Monitored File Path")
        self.threats_tree.heading("status", text="Integrity Status State")

        self.threats_tree.column("filepath", width=250, anchor="w")
        self.threats_tree.column("status", width=140, anchor="center")

        self.threats_tree.tag_configure("Modified", background="#ffcccc", foreground="#990000")
        self.threats_tree.tag_configure("Created", background="#d4edda", foreground="#155724")
        self.threats_tree.tag_configure("Deleted", background="#fff3cd", foreground="#856404")
        self.threats_tree.tag_configure("notice", background="#ffffff", foreground="#666666")

        threats_scroll = ttk.Scrollbar(self.threats_frame, orient="vertical", command=self.threats_tree.yview)
        self.threats_tree.configure(yscrollcommand=threats_scroll.set)
        self.threats_tree.pack(side="left", fill="both", expand=True)
        threats_scroll.pack(side="right", fill="y")

        self.threats_tree.bind("<<TreeviewSelect>>", self.handle_threats_selection)

        # Bottom Table: Clean files (Unchanged)
        self.clean_frame = ttk.LabelFrame(left_panel, text=" Clean files (0) ", padding=5)
        self.clean_frame.pack(side="bottom", fill="both", expand=True, pady=(5, 0))

        self.clean_tree = ttk.Treeview(self.clean_frame, columns=columns, show="headings", height=7)
        self.clean_tree.heading("filepath", text="Monitored File Path")
        self.clean_tree.heading("status", text="Integrity Status State")

        self.clean_tree.column("filepath", width=250, anchor="w")
        self.clean_tree.column("status", width=140, anchor="center")

        self.clean_tree.tag_configure("Unchanged", background="#ffffff", foreground="#333333")

        clean_scroll = ttk.Scrollbar(self.clean_frame, orient="vertical", command=self.clean_tree.yview)
        self.clean_tree.configure(yscrollcommand=clean_scroll.set)
        self.clean_tree.pack(side="left", fill="both", expand=True)
        clean_scroll.pack(side="right", fill="y")

        self.clean_tree.bind("<<TreeviewSelect>>", self.handle_clean_selection)

        # Alias self.tree to self.threats_tree for any legacy callers
        self.tree = self.threats_tree

        # --- Right Panel: Forensic Side-by-Side Diff Engine View ---
        right_panel = ttk.LabelFrame(workspace_frame, text=" Forensic Line-by-Line Diff Engine View ", padding=10)
        right_panel.pack(side="right", fill="both", expand=True)

        shared_scroll_y = ttk.Scrollbar(right_panel, orient="vertical")
        shared_scroll_y.pack(side="right", fill="y")

        # Shared vertical scrolling logic
        diff_container = ttk.Frame(right_panel)
        diff_container.pack(side="left", fill="both", expand=True)
        diff_container.columnconfigure(0, weight=1, uniform="diff_col")
        diff_container.columnconfigure(1, weight=1, uniform="diff_col")
        diff_container.rowconfigure(0, weight=1)

        # Left side-by-side pane: Baseline (trusted)
        left_box = ttk.LabelFrame(diff_container, text=" Baseline (trusted) ", padding=5)
        left_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.diff_left = tk.Text(left_box, wrap="none", font=("Courier", 10), bg="#ffffff")
        left_scroll_x = ttk.Scrollbar(left_box, orient="horizontal", command=self.diff_left.xview)
        self.diff_left.configure(xscrollcommand=left_scroll_x.set)
        left_scroll_x.pack(side="bottom", fill="x")
        self.diff_left.pack(side="left", fill="both", expand=True)

        # Right side-by-side pane: Current (live)
        right_box = ttk.LabelFrame(diff_container, text=" Current (live) ", padding=5)
        right_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        self.diff_right = tk.Text(right_box, wrap="none", font=("Courier", 10), bg="#ffffff")
        right_scroll_x = ttk.Scrollbar(right_box, orient="horizontal", command=self.diff_right.xview)
        self.diff_right.configure(xscrollcommand=right_scroll_x.set)
        right_scroll_x.pack(side="bottom", fill="x")
        self.diff_right.pack(side="left", fill="both", expand=True)

        self.diff_left.tag_configure("diff_change", background="#ffcccc", foreground="#990000")
        self.diff_right.tag_configure("diff_change", background="#d4edda", foreground="#155724")

        # Shared vertical scrolling logic
        self._syncing_scroll = False

        def on_scroll(*args):
            self.diff_left.yview(*args)
            self.diff_right.yview(*args)

        def on_left_scroll(*args):
            shared_scroll_y.set(*args)
            if not self._syncing_scroll:
                self._syncing_scroll = True
                self.diff_right.yview_moveto(args[0])
                self._syncing_scroll = False

        def on_right_scroll(*args):
            shared_scroll_y.set(*args)
            if not self._syncing_scroll:
                self._syncing_scroll = True
                self.diff_left.yview_moveto(args[0])
                self._syncing_scroll = False

        def on_mouse_wheel(event):
            delta = int(-1 * (event.delta / 120))
            self.diff_left.yview_scroll(delta, "units")
            self.diff_right.yview_scroll(delta, "units")
            return "break"

        shared_scroll_y.configure(command=on_scroll)
        self.diff_left.configure(yscrollcommand=on_left_scroll)
        self.diff_right.configure(yscrollcommand=on_right_scroll)
        self.diff_left.bind("<MouseWheel>", on_mouse_wheel)
        self.diff_right.bind("<MouseWheel>", on_mouse_wheel)

        self.update_diff_view_text("Select a modified record from the left panel to review file transformations.")

    def apply_settings(self, threshold=None, interval=None):
        """Immediately applies settings without restarting."""
        if threshold is not None:
            self.threshold_var.set(threshold)
        if interval is not None:
            self.auto_interval_var.set(interval)
            if self.auto_scan_var.get():
                self.auto_status_lbl.config(text=f"Auto-scan: ON (every {interval} s)")

    def toggle_auto_scan(self):
        """Starts or stops the recurring auto-scan timer."""
        if self.auto_scan_var.get():
            target = self.target_dir.get().strip()
            if not target or not os.path.exists(target):
                self.auto_scan_var.set(False)
                self.auto_status_lbl.config(text="Auto-scan: OFF")
                if hasattr(self.app, "set_status_monitoring"):
                    self.app.set_status_monitoring(False)
                self.app.show_toast("Please select a valid existing target path before starting Auto-scan.", "error")
                return

            try:
                seconds = int(self.auto_interval_spinbox.get())
                if seconds < 2:
                    seconds = 2
                elif seconds > 60:
                    seconds = 60
            except (ValueError, tk.TclError):
                seconds = 2

            self.auto_status_lbl.config(text=f"Auto-scan: ON (every {seconds} s)")
            if hasattr(self.app, "set_status_monitoring"):
                self.app.set_status_monitoring(True)
            self.baseline_btn.config(state="disabled")
            self.prev_auto_changed_count = None
            self.run_auto_scan()
        else:
            self.stop_auto_scan()

    def stop_auto_scan(self):
        """Cancels any scheduled auto-scan and re-enables controls."""
        if self.auto_timer_id is not None:
            self.app.root.after_cancel(self.auto_timer_id)
            self.auto_timer_id = None
        self.auto_scan_var.set(False)
        self.auto_status_lbl.config(text="Auto-scan: OFF")
        if hasattr(self.app, "set_status_monitoring"):
            self.app.set_status_monitoring(False)
        self.baseline_btn.config(state="normal")
        self.prev_auto_changed_count = None

    def run_auto_scan(self):
        """Performs one cycle of auto-scan and reschedules via root.after()."""
        if not self.auto_scan_var.get():
            return

        target = self.target_dir.get().strip()
        if not target or not os.path.exists(target):
            self.stop_auto_scan()
            self.app.show_toast("Auto-scan stopped: Target path is empty or no longer exists.", "error")
            return

        self.run_verification(is_auto=True)

        if self.auto_scan_var.get():
            try:
                seconds = int(self.auto_interval_spinbox.get())
                if seconds < 2:
                    seconds = 2
                elif seconds > 60:
                    seconds = 60
            except (ValueError, tk.TclError):
                seconds = 2

            self.auto_status_lbl.config(text=f"Auto-scan: ON (every {seconds} s)")
            self.auto_timer_id = self.app.root.after(seconds * 1000, self.run_auto_scan)

    def update_summary_cards(self, total=0, unchanged=0, modified=0, created=0, deleted=0):
        """Updates count numbers on the top summary cards."""
        if "Total" in self.card_labels:
            self.card_labels["Total"].config(text=str(total))
            self.card_labels["Unchanged"].config(text=str(unchanged))
            self.card_labels["Modified"].config(text=str(modified))
            self.card_labels["Created"].config(text=str(created))
            self.card_labels["Deleted"].config(text=str(deleted))

    def browse_directory(self):
        choice = ask_yes_no_cancel(
            self,
            "Select Scan Type", 
            "Would you like to monitor an entire FOLDER?\n\n(Click 'Yes' for Folder, 'No' for a Single File)"
        )
        if hasattr(self.app, "spider"):
            self.app.spider.resume()

        selected_path = None
        if choice is True:
            selected_path = filedialog.askdirectory(title="Select Target Folder to Monitor")
        elif choice is False:
            selected_path = filedialog.askopenfilename(
                title="Select Specific Configuration File to Monitor",
                filetypes=[("All Files", "*.*"), ("Text Files", "*.txt"), ("Config Files", "*.conf;*.ini;*.json")]
            )

        if hasattr(self.app, "spider"):
            self.app.spider.resume()

        if selected_path:
            self.target_dir.set(selected_path)
            try:
                self.db.set_setting("last_target_path", selected_path)
            except Exception:
                pass

    def run_baseline(self):
        target = self.target_dir.get().strip()
        if not target:
            self.app.show_toast("Please pick a valid target path baseline source.", "error")
            return

        self.db.set_setting("last_target_path", target)
        count = self.engine.generate_baseline(target)
        if hasattr(self.app, "spider"):
            self.app.spider.notify("baseline_done")
        if hasattr(self.app, "sounds"):
            self.app.sounds.play("baseline_done")
        self.app.show_toast(f"Baseline saved! {count} files committed to baseline.", "success")
        self.run_verification(is_auto=True)

        # (a) Right after Generate Baseline succeeds: start auto-scan automatically if continuous monitoring is ON
        continuous = str(self.db.get_setting("continuous_monitoring", "true")).lower() != "false"
        if continuous and not self.auto_scan_var.get():
            self.auto_scan_var.set(True)
            self.toggle_auto_scan()

    def _sync_threats_table(self, threat_matches, is_alert_active):
        """
        Updates threats_tree in place: inserts new rows, updates changed rows,
        removes obsolete rows, preserving selection and scroll position.
        Returns list of newly changed filepaths.
        """
        current_selection = self.threats_tree.selection()
        selected_path = None
        if current_selection:
            vals = self.threats_tree.item(current_selection[0], "values")
            if vals and len(vals) > 0 and vals[0] != "-":
                selected_path = vals[0]

        existing_children = self.threats_tree.get_children()
        existing_by_path = {}
        notice_items = []
        for iid in existing_children:
            tags = self.threats_tree.item(iid, "tags") or ()
            if "notice" in tags:
                notice_items.append(iid)
                continue
            vals = self.threats_tree.item(iid, "values")
            if vals and len(vals) > 0:
                existing_by_path[vals[0]] = iid

        # If no threats exist
        if not threat_matches:
            for iid in existing_by_path.values():
                self.threats_tree.delete(iid)
            if not notice_items:
                self.threats_tree.insert("", "end", values=("-", "No threats detected"), tags=("notice",))
            return []

        # Remove notice item if threats exist
        for niid in notice_items:
            try:
                self.threats_tree.delete(niid)
            except Exception:
                pass

        threats_display = list(reversed(threat_matches))
        target_paths = set()
        newly_changed = []

        for idx, item in enumerate(threats_display):
            filepath, status = item[0], item[2]
            target_paths.add(filepath)
            display_status = "Suspected Malicious" if is_alert_active else status
            new_hash = item[5] if len(item) > 5 else status

            if filepath not in self._known_threat_hashes or self._known_threat_hashes[filepath] != new_hash:
                newly_changed.append(filepath)

            if filepath in existing_by_path:
                iid = existing_by_path[filepath]
                curr_vals = self.threats_tree.item(iid, "values")
                curr_tags = self.threats_tree.item(iid, "tags") or ()
                new_vals = (filepath, display_status)
                new_tags = (status,)
                if curr_vals != new_vals or curr_tags != new_tags:
                    self.threats_tree.item(iid, values=new_vals, tags=new_tags)
            else:
                self.threats_tree.insert("", idx, values=(filepath, display_status), tags=(status,))

        # Delete rows that moved out of threats
        for fpath, iid in existing_by_path.items():
            if fpath not in target_paths:
                self.threats_tree.delete(iid)

        # Restore previous selection if still present
        if selected_path and selected_path in target_paths:
            for iid in self.threats_tree.get_children():
                vals = self.threats_tree.item(iid, "values")
                if vals and vals[0] == selected_path:
                    if self.threats_tree.selection() != (iid,):
                        self._clearing_selection = True
                        try:
                            self.threats_tree.selection_set(iid)
                        finally:
                            self._clearing_selection = False
                    break

        self._known_threat_hashes = {
            m[0]: (m[5] if len(m) > 5 else m[2]) for m in threat_matches
        }
        return newly_changed

    def _sync_clean_table(self, clean_matches):
        """Updates clean_tree in place: inserts new, updates existing, deletes removed."""
        current_selection = self.clean_tree.selection()
        selected_path = None
        if current_selection:
            vals = self.clean_tree.item(current_selection[0], "values")
            if vals and len(vals) > 0:
                selected_path = vals[0]

        existing_children = self.clean_tree.get_children()
        existing_by_path = {}
        for iid in existing_children:
            vals = self.clean_tree.item(iid, "values")
            if vals and len(vals) > 0:
                existing_by_path[vals[0]] = iid

        target_paths = set()
        for item in clean_matches:
            filepath, status = item[0], item[2]
            target_paths.add(filepath)

            if filepath in existing_by_path:
                iid = existing_by_path[filepath]
                curr_vals = self.clean_tree.item(iid, "values")
                curr_tags = self.clean_tree.item(iid, "tags") or ()
                new_vals = (filepath, status)
                new_tags = (status,)
                if curr_vals != new_vals or curr_tags != new_tags:
                    self.clean_tree.item(iid, values=new_vals, tags=new_tags)
            else:
                self.clean_tree.insert("", "end", values=(filepath, status), tags=(status,))

        for fpath, iid in existing_by_path.items():
            if fpath not in target_paths:
                self.clean_tree.delete(iid)

        if selected_path and selected_path in target_paths:
            for iid in self.clean_tree.get_children():
                vals = self.clean_tree.item(iid, "values")
                if vals and vals[0] == selected_path:
                    if self.clean_tree.selection() != (iid,):
                        self._clearing_selection = True
                        try:
                            self.clean_tree.selection_set(iid)
                        finally:
                            self._clearing_selection = False
                    break

    def run_verification(self, is_auto=False):
        target = self.target_dir.get().strip()
        if not target:
            if not is_auto:
                self.app.show_toast("Please choose a deployment path to check.", "error")
            return

        matches = self.engine.verify_integrity(target)

        # Counts by status
        total_files = len(matches)
        unchanged = sum(1 for m in matches if m[2] == "Unchanged")
        modified = sum(1 for m in matches if m[2] == "Modified")
        created = sum(1 for m in matches if m[2] == "Created")
        deleted = sum(1 for m in matches if m[2] == "Deleted")
        changed_count = modified + created + deleted

        # Update summary cards on every scan
        self.update_summary_cards(
            total=total_files,
            unchanged=unchanged,
            modified=modified,
            created=created,
            deleted=deleted
        )

        # Check ransomware activity threshold via central app
        self.app.check_threshold(changed_count)

        # Check if alert is active
        threshold = 5
        try:
            threshold = int(self.threshold_var.get())
        except Exception:
            threshold = 5
        is_alert_active = bool(getattr(self.app, "alert_triggered", False)) or (changed_count >= threshold)

        threat_matches = [m for m in matches if m[2] in ("Modified", "Created", "Deleted")]
        self.threats_frame.config(text=f" ⚠ Threats ({len(threat_matches)}) ")

        # Live in-place update of Threats table
        newly_changed = self._sync_threats_table(threat_matches, is_alert_active)

        # Live in-place update of Clean table
        clean_matches = [m for m in matches if m[2] == "Unchanged"]
        self.clean_frame.config(text=f" Clean files ({len(clean_matches)}) ")
        self._sync_clean_table(clean_matches)

        # Automatic diff view: follow newly changed file or refresh selected file
        now = time.time()
        curr_threat_sel = self.threats_tree.selection()
        curr_threat_path = None
        if curr_threat_sel:
            vals = self.threats_tree.item(curr_threat_sel[0], "values")
            if vals and len(vals) > 0 and vals[0] != "-":
                curr_threat_path = vals[0]

        if curr_threat_path and curr_threat_path in newly_changed:
            # Selected file changed again: refresh diff live
            self.handle_row_selection()
        elif now >= self._user_selected_until and newly_changed:
            # Auto-follow the most recently changed file (first item in newly_changed)
            target_to_select = newly_changed[0]
            for iid in self.threats_tree.get_children():
                vals = self.threats_tree.item(iid, "values")
                if vals and vals[0] == target_to_select:
                    self._clearing_selection = True
                    try:
                        self.threats_tree.selection_set(iid)
                        self.clean_tree.selection_set(())
                    finally:
                        self._clearing_selection = False
                    self.threats_tree.see(iid)
                    self.handle_row_selection()
                    break

        # Spider overlay and sound hooks for scan finished (using threats_tree for outlines)
        if hasattr(self.app, "spider"):
            self.app.spider.notify("scan_done", {"tree": self.threats_tree, "matches": matches, "changed": changed_count})
        if changed_count > 0 and hasattr(self.app, "sounds"):
            self.app.sounds.play("scan_done")

        # Determine whether to record this scan in history
        should_save = True
        if is_auto:
            if self.prev_auto_changed_count is not None and self.prev_auto_changed_count == changed_count:
                should_save = False
            self.prev_auto_changed_count = changed_count

        if should_save:
            scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            run_id = self.db.save_scan_run(
                scan_time, target, total_files, unchanged, modified, created, deleted
            )

            for item in matches:
                filepath, status = item[0], item[2]
                old_hash = item[4] if len(item) > 4 else ""
                new_hash = item[5] if len(item) > 5 else ""
                if status in ("Modified", "Created", "Deleted"):
                    self.db.save_scan_detail(run_id, filepath, status, old_hash or "", new_hash or "")

    def accept_changes(self):
        target = self.target_dir.get().strip()
        if not target:
            self.app.show_toast("Please choose a deployment path first.", "error")
            return

        confirm = ask_yes_no(
            self,
            "Confirm Accept Changes",
            "Are you sure you want to update the baseline with current disk changes?\n\nThis will re-save modified/created files and remove deleted files from the database."
        )
        if hasattr(self.app, "spider"):
            self.app.spider.resume()

        if not confirm:
            return

        self.engine.accept_changes(target)
        if hasattr(self.app, "spider"):
            self.app.spider.notify("accept_changes")
        if hasattr(self.app, "sounds"):
            self.app.sounds.play("accept_changes")
        self.run_verification()

    def handle_threats_selection(self, event=None):
        """Called when a row in the threats table is clicked. Clears selection in clean table."""
        try:
            if getattr(self, "_clearing_selection", False):
                return
            if event is not None:
                # User manually clicked a row: pause auto-following for 30s
                self._user_selected_until = time.time() + 30.0
            selected = self.threats_tree.selection()
            if selected:
                self._clearing_selection = True
                try:
                    self.clean_tree.selection_set(())
                finally:
                    self._clearing_selection = False
                self.handle_row_selection(event)
        finally:
            if hasattr(self.app, "spider"):
                self.app.spider.resume()

    def handle_clean_selection(self, event=None):
        """Called when a row in the clean table is clicked. Clears selection in threats table."""
        try:
            if getattr(self, "_clearing_selection", False):
                return
            if event is not None:
                # User manually clicked clean table: pause auto-following for 30s
                self._user_selected_until = time.time() + 30.0
            selected = self.clean_tree.selection()
            if selected:
                self._clearing_selection = True
                try:
                    self.threats_tree.selection_set(())
                finally:
                    self._clearing_selection = False
                self.update_diff_view_text("Selected file is Unchanged.\nDiff line tracing is isolated only to files flagged as 'Modified'.")
        finally:
            if hasattr(self.app, "spider"):
                self.app.spider.resume()

    def handle_row_selection(self, event=None):
        try:
            selected = self.threats_tree.selection()
            if not selected:
                return
                
            item_values = self.threats_tree.item(selected[0], "values")
            if not item_values or len(item_values) < 2:
                return
                
            filepath, display_status = item_values[0], item_values[1]
            tags = self.threats_tree.item(selected[0], "tags") or ()
            actual_status = tags[0] if tags else display_status

            if filepath == "-" or "notice" in tags:
                return

            for widget in (self.diff_left, self.diff_right):
                widget.config(state="normal")
                widget.delete("1.0", "end")

            if actual_status == "Created":
                self.diff_left.insert("end", "[Created File - Not present in baseline]\n\n(No baseline version exists for this newly detected file.)")
                _, live_content = Hasher.calculate_sha256(filepath)
                self.diff_right.insert("end", live_content or "(Empty file)", "diff_change")
                for widget in (self.diff_left, self.diff_right):
                    widget.config(state="disabled")
                return

            if actual_status == "Deleted":
                old_content_raw = self.db.get_file_content(filepath)
                old_str = old_content_raw[0] if isinstance(old_content_raw, tuple) else (old_content_raw or "")
                self.diff_left.insert("end", old_str or "(Empty file)", "diff_change")
                self.diff_right.insert("end", "[Deleted File - No longer present on disk]\n\n(This file was deleted after the baseline was generated.)")
                for widget in (self.diff_left, self.diff_right):
                    widget.config(state="disabled")
                return

            if actual_status != "Modified":
                self.update_diff_view_text(f"File status state is currently [{actual_status}].\nDiff line tracing is isolated only to files flagged as 'Modified'.")
                return
                
            old_content_raw = self.db.get_file_content(filepath)
            _, current_content_raw = Hasher.calculate_sha256(filepath)
            
            old_str = old_content_raw[0] if isinstance(old_content_raw, tuple) else (old_content_raw or "")
            new_str = current_content_raw or ""

            old_lines = old_str.splitlines()
            new_lines = new_str.splitlines()
            
            if not old_lines and not new_lines:
                self.update_diff_view_text("[Information Notice] Minor hash mismatch detected, but binary text sequences contain no printable unified row variances.")
                return

            matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
            opcodes = matcher.get_opcodes()

            has_changes = any(tag != "equal" for tag, _, _, _, _ in opcodes)
            if not has_changes:
                self.update_diff_view_text("[Information Notice] Minor hash mismatch detected, but binary text sequences contain no printable unified row variances.")
                return

            for tag, i1, i2, j1, j2 in opcodes:
                if tag == "equal":
                    for k in range(i2 - i1):
                        line = old_lines[i1 + k]
                        self.diff_left.insert("end", line + "\n")
                        self.diff_right.insert("end", line + "\n")
                elif tag == "replace":
                    left_sub = old_lines[i1:i2]
                    right_sub = new_lines[j1:j2]
                    max_len = max(len(left_sub), len(right_sub))
                    for k in range(max_len):
                        if k < len(left_sub):
                            self.diff_left.insert("end", left_sub[k] + "\n", "diff_change")
                        else:
                            self.diff_left.insert("end", "\n")
                        if k < len(right_sub):
                            self.diff_right.insert("end", right_sub[k] + "\n", "diff_change")
                        else:
                            self.diff_right.insert("end", "\n")
                elif tag == "delete":
                    for k in range(i2 - i1):
                        self.diff_left.insert("end", old_lines[i1 + k] + "\n", "diff_change")
                        self.diff_right.insert("end", "\n")
                elif tag == "insert":
                    for k in range(j2 - j1):
                        self.diff_left.insert("end", "\n")
                        self.diff_right.insert("end", new_lines[j1 + k] + "\n", "diff_change")

            for widget in (self.diff_left, self.diff_right):
                widget.config(state="disabled")
        except Exception as e:
            print(f"[Diff View Selection Error] {e}")
            import traceback
            traceback.print_exc()
        finally:
            if hasattr(self.app, "spider"):
                self.app.spider.resume()

    def update_diff_view_text(self, plain_text):
        """Helper method to update notification descriptions on the screen."""
        for widget in (self.diff_left, self.diff_right):
            widget.config(state="normal")
            widget.delete("1.0", "end")
        self.diff_left.insert("end", plain_text)
        for widget in (self.diff_left, self.diff_right):
            widget.config(state="disabled")
