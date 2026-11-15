import os
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from gui.confirm_dialog import ask_yes_no

class BackupPage(tk.Frame):
    def __init__(self, parent, app, backup_manager):
        super().__init__(parent)
        self.app = app
        self.backup_manager = backup_manager
        self.setup_ui()

    def setup_ui(self):
        container = ttk.LabelFrame(self, text=" Backup & Disaster Recovery Management ", padding=15)
        container.pack(fill="both", expand=True, padx=20, pady=15)

        title_lbl = ttk.Label(
            container,
            text="Backup & Restore Console",
            font=("Arial", 14, "bold")
        )
        title_lbl.pack(anchor="w", pady=(0, 10))

        # 1. Backup Repository Information Card
        info_frame = ttk.LabelFrame(container, text=" Backup Storage Information ", padding=12)
        info_frame.pack(fill="x", pady=6)

        # Folder path
        p_row = ttk.Frame(info_frame)
        p_row.pack(fill="x", pady=3)
        ttk.Label(p_row, text="Backup Folder Path:", font=("Arial", 9, "bold"), width=22).pack(side="left")
        self.path_lbl = ttk.Label(p_row, text=self.backup_manager.backup_dir, font=("Courier", 9))
        self.path_lbl.pack(side="left", fill="x", expand=True)

        # File count and last backup time
        stats_row = ttk.Frame(info_frame)
        stats_row.pack(fill="x", pady=3)

        ttk.Label(stats_row, text="Backed-up Files:", font=("Arial", 9, "bold"), width=22).pack(side="left")
        self.count_lbl = ttk.Label(stats_row, text="0 files", font=("Arial", 9))
        self.count_lbl.pack(side="left", padx=(0, 30))

        ttk.Label(stats_row, text="Last Backup Time:", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 5))
        self.time_lbl = ttk.Label(stats_row, text="Never", font=("Arial", 9))
        self.time_lbl.pack(side="left")

        # 2. Restore Actions Card
        action_frame = ttk.LabelFrame(container, text=" File Recovery Actions ", padding=12)
        action_frame.pack(fill="x", pady=8)

        desc_text = (
            "Restore will copy pristine baseline files from the backup repository back to their original disk locations.\n"
            "• Only files with status 'Modified' or 'Deleted' will be restored.\n"
            "• Missing parent folders will be recreated automatically.\n"
            "• 'Created' (unknown) files will NEVER be deleted.\n"
            "• Restored files are cryptographically validated against their baseline SHA-256 hash."
        )
        ttk.Label(action_frame, text=desc_text, font=("Arial", 9), justify="left").pack(anchor="w", pady=(0, 10))

        btn_row = ttk.Frame(action_frame)
        btn_row.pack(fill="x")

        restore_btn = ttk.Button(
            btn_row,
            text="🔄 Restore Modified & Deleted Files",
            command=self.run_restore
        )
        restore_btn.pack(side="left", padx=(0, 10))

        refresh_btn = ttk.Button(
            btn_row,
            text="Refresh Stats",
            command=self.refresh_stats
        )
        refresh_btn.pack(side="left")

        # 3. Restoration Results Box Card
        results_frame = ttk.LabelFrame(container, text=" Restoration Audit Report ", padding=10)
        results_frame.pack(fill="both", expand=True, pady=8)

        self.results_box = tk.Text(
            results_frame,
            wrap="none",
            font=("Courier", 10),
            bg="#ffffff",
            height=10
        )
        res_scroll_y = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_box.yview)
        self.results_box.configure(yscrollcommand=res_scroll_y.set)

        self.results_box.pack(side="left", fill="both", expand=True)
        res_scroll_y.pack(side="right", fill="y")

        self.results_box.insert("end", "No restore operations run in this session.\nClick 'Restore Modified & Deleted Files' to recover compromised or missing files.")
        self.results_box.config(state="disabled")

        self.refresh_stats()

    def refresh_stats(self):
        """Updates display statistics from the backup manager."""
        target = ""
        dashboard = self.app.pages.get("Dashboard")
        if dashboard and hasattr(dashboard, "target_dir"):
            target = dashboard.target_dir.get().strip()

        stats = self.backup_manager.get_backup_stats(target if target else None)
        self.path_lbl.config(text=stats["backup_dir"])
        self.count_lbl.config(text=f"{stats['file_count']} files")
        self.time_lbl.config(text=stats["last_backup_time"])

    def run_restore(self):
        """Prompts for confirmation, executes restoration, logs activity, and refreshes Dashboard."""
        dashboard = self.app.pages.get("Dashboard")
        target = ""
        if dashboard and hasattr(dashboard, "target_dir"):
            target = dashboard.target_dir.get().strip()

        if not target or not os.path.exists(target):
            self.app.show_toast("Please select a valid target path on the Dashboard first.", "error")
            return

        confirm = ask_yes_no(
            self,
            "Confirm Restore",
            f"Are you sure you want to restore files for:\n{target}\n\n"
            "This will revert all Modified files and restore Deleted files from backup.\n"
            "Created files will NOT be deleted."
        )
        if hasattr(self.app, "spider"):
            self.app.spider.resume()

        if not confirm:
            return

        # Perform restoration
        restored, verified, failed = self.backup_manager.restore_files(target)

        if hasattr(self.app, "spider"):
            self.app.spider.notify("restore_done")
        if hasattr(self.app, "sounds"):
            self.app.sounds.play("restore_done")

        # Log to activity log table
        self.app.db.log_activity(
            "FILES_RESTORED",
            f"Restored {restored} files ({verified} verified, {failed} failed) in {target}"
        )

        # Update results box
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = (
            f"==========================================================\n"
            f"[✓] RESTORATION AUDIT REPORT - {now_str}\n"
            f"Target Monitored Path: {target}\n"
            f"----------------------------------------------------------\n"
            f"• Files Restored:            {restored}\n"
            f"• Verified via SHA-256 Hash: {verified}\n"
            f"• Failed Restorations:       {failed}\n"
            f"----------------------------------------------------------\n"
        )
        if failed == 0 and restored > 0:
            report += "STATUS: SUCCESS — All restored files match baseline hash.\n"
        elif restored == 0 and failed == 0:
            report += "STATUS: NOTICE — No Modified or Deleted files found to restore.\n"
        else:
            report += f"STATUS: WARNING — {failed} files failed copy or hash verification.\n"
        report += "==========================================================\n"

        self.results_box.config(state="normal")
        self.results_box.delete("1.0", "end")
        self.results_box.insert("end", report)
        self.results_box.config(state="disabled")

        # Re-run scan so Dashboard refreshes
        if dashboard and hasattr(dashboard, "run_verification"):
            dashboard.run_verification()

        self.refresh_stats()
        self.app.show_toast(
            f"Restore complete: {restored} restored ({verified} verified, {failed} failed)",
            kind="success" if failed == 0 else "warning"
        )
