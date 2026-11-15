import tkinter as tk
from tkinter import ttk

class HistoryPage(tk.Frame):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.db = db_manager
        self.setup_ui()

    def setup_ui(self):
        # Header frame with title and refresh button
        header_frame = ttk.Frame(self, padding=8)
        header_frame.pack(fill="x")
        
        ttk.Label(header_frame, text="Audit Log: Historical Scan Verification Runs", font=("Arial", 12, "bold")).pack(side="left")
        ttk.Button(header_frame, text="🔄 Refresh History", command=self.refresh).pack(side="right")

        # 1. Top Section: Past Scans table
        top_frame = ttk.LabelFrame(self, text=" Past Scans (Double-click a scan to view details) ", padding=8)
        top_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        scan_cols = ("time", "path", "total", "unchanged", "modified", "created", "deleted")
        self.runs_tree = ttk.Treeview(top_frame, columns=scan_cols, show="headings", height=5)
        self.runs_tree.heading("time", text="Scan Time")
        self.runs_tree.heading("path", text="Target Path")
        self.runs_tree.heading("total", text="Total Files")
        self.runs_tree.heading("unchanged", text="Unchanged")
        self.runs_tree.heading("modified", text="Modified")
        self.runs_tree.heading("created", text="Created")
        self.runs_tree.heading("deleted", text="Deleted")

        self.runs_tree.column("time", width=140, anchor="center")
        self.runs_tree.column("path", width=300, anchor="w")
        self.runs_tree.column("total", width=70, anchor="center")
        self.runs_tree.column("unchanged", width=80, anchor="center")
        self.runs_tree.column("modified", width=70, anchor="center")
        self.runs_tree.column("created", width=70, anchor="center")
        self.runs_tree.column("deleted", width=70, anchor="center")

        runs_scroll = ttk.Scrollbar(top_frame, orient="vertical", command=self.runs_tree.yview)
        self.runs_tree.configure(yscrollcommand=runs_scroll.set)
        self.runs_tree.pack(side="left", fill="both", expand=True)
        runs_scroll.pack(side="right", fill="y")

        # 2. Middle Section: Problem Files Details table
        mid_frame = ttk.LabelFrame(self, text=" Problem Files Details ", padding=8)
        mid_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        detail_cols = ("filepath", "status", "old_hash", "new_hash")
        self.details_tree = ttk.Treeview(mid_frame, columns=detail_cols, show="headings", height=5)
        self.details_tree.heading("filepath", text="File Path")
        self.details_tree.heading("status", text="Status")
        self.details_tree.heading("old_hash", text="Old Hash")
        self.details_tree.heading("new_hash", text="New Hash")

        self.details_tree.column("filepath", width=340, anchor="w")
        self.details_tree.column("status", width=90, anchor="center")
        self.details_tree.column("old_hash", width=220, anchor="center")
        self.details_tree.column("new_hash", width=220, anchor="center")

        self.details_tree.tag_configure("Modified", background="#ffcccc", foreground="#990000")
        self.details_tree.tag_configure("Created", background="#d4edda", foreground="#155724")
        self.details_tree.tag_configure("Deleted", background="#fff3cd", foreground="#856404")
        self.details_tree.tag_configure("Unchanged", background="#ffffff", foreground="#333333")

        details_scroll_y = ttk.Scrollbar(mid_frame, orient="vertical", command=self.details_tree.yview)
        details_scroll_x = ttk.Scrollbar(mid_frame, orient="horizontal", command=self.details_tree.xview)
        self.details_tree.configure(yscrollcommand=details_scroll_y.set, xscrollcommand=details_scroll_x.set)
        details_scroll_x.pack(side="bottom", fill="x")
        self.details_tree.pack(side="left", fill="both", expand=True)
        details_scroll_y.pack(side="right", fill="y")

        # 3. Bottom Section: Security Activity Log table
        bottom_frame = ttk.LabelFrame(self, text=" Security Activity Log (Alerts, Terminations, Restores) ", padding=8)
        bottom_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        act_cols = ("time", "event_type", "details")
        self.activity_tree = ttk.Treeview(bottom_frame, columns=act_cols, show="headings", height=5)
        self.activity_tree.heading("time", text="Timestamp")
        self.activity_tree.heading("event_type", text="Event Type")
        self.activity_tree.heading("details", text="Activity Details")

        self.activity_tree.column("time", width=140, anchor="center")
        self.activity_tree.column("event_type", width=160, anchor="center")
        self.activity_tree.column("details", width=550, anchor="w")

        self.activity_tree.tag_configure("ALERT_TRIGGERED", background="#ffcccc", foreground="#990000")
        self.activity_tree.tag_configure("PROCESS_KILLED", background="#fff3cd", foreground="#856404")
        self.activity_tree.tag_configure("FILES_RESTORED", background="#d4edda", foreground="#155724")

        act_scroll = ttk.Scrollbar(bottom_frame, orient="vertical", command=self.activity_tree.yview)
        self.activity_tree.configure(yscrollcommand=act_scroll.set)
        self.activity_tree.pack(side="left", fill="both", expand=True)
        act_scroll.pack(side="right", fill="y")

        self.runs_tree.bind("<Double-1>", self.on_scan_double_click)
        self.refresh()

    def refresh(self):
        """Reloads scan runs and activity logs from the database (newest first)."""
        for row in self.runs_tree.get_children():
            self.runs_tree.delete(row)
        for row in self.details_tree.get_children():
            self.details_tree.delete(row)
        for row in self.activity_tree.get_children():
            self.activity_tree.delete(row)

        scan_runs = self.db.get_scan_runs()
        for run in scan_runs:
            run_id, scan_time, path, total, unchanged, modified, created, deleted = run
            self.runs_tree.insert("", "end", iid=str(run_id), values=(scan_time, path, total, unchanged, modified, created, deleted))

        activity_logs = self.db.get_activity_log()
        for log in activity_logs:
            log_time, event_type, details = log
            self.activity_tree.insert("", "end", values=(log_time, event_type, details), tags=(event_type,))

    def on_scan_double_click(self, event):
        selected = self.runs_tree.selection()
        if not selected:
            row_id = self.runs_tree.identify_row(event.y)
            if row_id:
                selected = (row_id,)
        if not selected:
            return

        run_id = selected[0]
        for row in self.details_tree.get_children():
            self.details_tree.delete(row)

        details = self.db.get_scan_details(run_id)
        for filepath, status, old_hash, new_hash in details:
            display_old = old_hash if old_hash else "-"
            display_new = new_hash if new_hash else "-"
            self.details_tree.insert("", "end", values=(filepath, status, display_old, display_new), tags=(status,))
