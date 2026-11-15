import os
import sqlite3
from datetime import datetime

class DBManager:
    def __init__(self, db_name="fim_repository.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        """Creates baseline, history, settings, backup, and activity log tables if they do not exist."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_baseline (
                    filepath TEXT PRIMARY KEY,
                    filename TEXT,
                    sha256_hash TEXT,
                    last_seen TEXT,
                    file_content TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_time TEXT,
                    target_path TEXT,
                    total_files INTEGER,
                    unchanged INTEGER,
                    modified INTEGER,
                    created INTEGER,
                    deleted INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    filepath TEXT,
                    status TEXT,
                    old_hash TEXT,
                    new_hash TEXT,
                    FOREIGN KEY (run_id) REFERENCES scan_runs (id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_time TEXT,
                    target_path TEXT,
                    file_count INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_time TEXT,
                    event_type TEXT,
                    details TEXT
                )
            """)
            conn.commit()

    def save_baseline(self, filepath, filename, sha256_hash, content):
        """Inserts or replaces file metadata into the database."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO file_baseline (filepath, filename, sha256_hash, last_seen, file_content)
                VALUES (?, ?, ?, ?, ?)
            """, (filepath, filename, sha256_hash, timestamp, content))
            conn.commit()

    def delete_record(self, filepath):
        """Removes a baseline record from the database by filepath."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM file_baseline WHERE filepath = ?", (filepath,))
            conn.commit()

    def get_all_records(self):
        """Fetches all records mapped by filepath for easy memory comparisons."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filepath, filename, sha256_hash, last_seen FROM file_baseline")
            rows = cursor.fetchall()
            
        # Correctly maps raw elements explicitly using indexed rows
        return {row[0]: {"filename": row[1], "hash": row[2], "seen": row[3]} for row in rows}

    def has_baseline_for_target(self, target_path):
        """Returns True if there are any baseline records associated with target_path."""
        if not target_path:
            return False
        norm_target = os.path.normpath(os.path.abspath(target_path)).lower()
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filepath FROM file_baseline")
            rows = cursor.fetchall()
            for row in rows:
                p = os.path.normpath(os.path.abspath(row[0])).lower()
                if p == norm_target or p.startswith(norm_target + os.sep) or p.startswith(norm_target + "/"):
                    return True
        return False

    def get_file_content(self, filepath):
        """Retrieves historical baseline content for a specific file."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_content FROM file_baseline WHERE filepath = ?", (filepath,))
            row = cursor.fetchone()
        
        if row:
            return row[0] if isinstance(row, tuple) else row
        return ""

    def save_scan_run(self, scan_time, target_path, total_files, unchanged, modified, created, deleted):
        """Inserts a scan run record and returns the new run id."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scan_runs (scan_time, target_path, total_files, unchanged, modified, created, deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (scan_time, target_path, total_files, unchanged, modified, created, deleted))
            conn.commit()
            return cursor.lastrowid

    def save_scan_detail(self, run_id, filepath, status, old_hash, new_hash):
        """Inserts a scan detail record for a problem file."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scan_details (run_id, filepath, status, old_hash, new_hash)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, filepath, status, old_hash, new_hash))
            conn.commit()

    def get_scan_runs(self):
        """Fetches all scan runs, newest first."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, scan_time, target_path, total_files, unchanged, modified, created, deleted
                FROM scan_runs
                ORDER BY id DESC
            """)
            return cursor.fetchall()

    def get_scan_details(self, run_id):
        """Fetches problem file details for a specific scan run."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT filepath, status, old_hash, new_hash
                FROM scan_details
                WHERE run_id = ?
                ORDER BY id ASC
            """, (run_id,))
            return cursor.fetchall()

    def get_setting(self, key, default=None):
        """Retrieves a configuration setting by key, returning default if missing."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row is not None:
                return row[0]
            return default

    def set_setting(self, key, value):
        """Stores or updates a configuration setting key/value pair."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value)
                VALUES (?, ?)
            """, (key, str(value)))
            conn.commit()

    def save_backup_record(self, backup_time, target_path, file_count):
        """Records a backup operation in the backups table."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO backups (backup_time, target_path, file_count)
                VALUES (?, ?, ?)
            """, (backup_time, target_path, file_count))
            conn.commit()

    def get_latest_backup(self, target_path=None):
        """Retrieves the most recent backup timestamp and file count."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            if target_path:
                cursor.execute("""
                    SELECT backup_time, target_path, file_count
                    FROM backups
                    WHERE target_path = ?
                    ORDER BY id DESC LIMIT 1
                """, (target_path,))
            else:
                cursor.execute("""
                    SELECT backup_time, target_path, file_count
                    FROM backups
                    ORDER BY id DESC LIMIT 1
                """)
            return cursor.fetchone()

    def log_activity(self, event_type, details):
        """Records an event into the activity log."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO activity_log (log_time, event_type, details)
                VALUES (?, ?, ?)
            """, (timestamp, event_type, details))
            conn.commit()

    def get_activity_log(self, limit=100):
        """Retrieves recent security activity logs, newest first."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT log_time, event_type, details
                FROM activity_log
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()
