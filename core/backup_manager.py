import os
import shutil
import hashlib
from datetime import datetime
from core.hasher import Hasher

class BackupManager:
    def __init__(self, db_manager, backup_dir="fim_backups", engine=None):
        self.db = db_manager
        self.engine = engine
        self.backup_dir = os.path.abspath(backup_dir)
        os.makedirs(self.backup_dir, exist_ok=True)

    def get_target_backup_dir(self, target_path):
        """Generates a dedicated subfolder path inside fim_backups for the monitored target."""
        norm = os.path.abspath(target_path)
        base = os.path.basename(norm.rstrip("\\/")) or "target"
        safe_base = "".join(c for c in base if c.isalnum() or c in ("-", "_")).rstrip()
        target_hash = hashlib.sha256(norm.lower().encode("utf-8")).hexdigest()[:12]
        return os.path.join(self.backup_dir, f"{safe_base}_{target_hash}")

    def get_backup_path_for_file(self, target_path, file_path):
        """Resolves the backup destination path maintaining relative folder structure."""
        norm_target = os.path.abspath(target_path)
        norm_file = os.path.abspath(file_path)
        target_backup_dir = self.get_target_backup_dir(norm_target)

        if os.path.isfile(norm_target):
            rel_path = os.path.basename(norm_file)
        else:
            rel_path = os.path.relpath(norm_file, norm_target)

        return os.path.join(target_backup_dir, rel_path)

    def create_baseline_backup(self, target_path, files=None):
        """Copies every valid hashed file into the backup directory for this target."""
        if not target_path or not os.path.exists(target_path):
            return 0

        target_path = os.path.abspath(target_path)
        target_backup_dir = self.get_target_backup_dir(target_path)

        # Clear old backup for this target so backup matches latest baseline
        shutil.rmtree(target_backup_dir, ignore_errors=True)
        os.makedirs(target_backup_dir, exist_ok=True)

        copied_count = 0

        if files is not None:
            # files can be a list of paths or (path, hash) tuples
            for item in files:
                filepath = item[0] if isinstance(item, (tuple, list)) else item
                if os.path.exists(filepath):
                    dest = self.get_backup_path_for_file(target_path, filepath)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(filepath, dest)
                    copied_count += 1
        else:
            if os.path.isfile(target_path):
                sha_hash, _ = Hasher.calculate_sha256(target_path)
                if sha_hash:
                    dest = self.get_backup_path_for_file(target_path, target_path)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(target_path, dest)
                    copied_count += 1
            else:
                for root, _, filenames in os.walk(target_path):
                    for fname in filenames:
                        full_path = os.path.abspath(os.path.join(root, fname))
                        sha_hash, _ = Hasher.calculate_sha256(full_path)
                        if sha_hash:
                            dest = self.get_backup_path_for_file(target_path, full_path)
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.copy2(full_path, dest)
                            copied_count += 1

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.set_setting("last_backup_time", timestamp)
        self.db.save_backup_record(timestamp, target_path, copied_count)
        return copied_count

    def update_backup_on_accept(self, target_path, scan_results):
        """Updates backup on Accept Changes: re-copies Modified/Created and removes Deleted."""
        if not target_path or not scan_results:
            return

        target_path = os.path.abspath(target_path)
        updated_count = 0

        for item in scan_results:
            filepath = item[0]
            status = item[2]

            if status in ("Modified", "Created"):
                if os.path.exists(filepath):
                    sha_hash, _ = Hasher.calculate_sha256(filepath)
                    if sha_hash:
                        dest = self.get_backup_path_for_file(target_path, filepath)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(filepath, dest)
                        updated_count += 1
            elif status == "Deleted":
                dest = self.get_backup_path_for_file(target_path, filepath)
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                        updated_count += 1
                    except OSError:
                        pass

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.set_setting("last_backup_time", timestamp)

    def restore_files(self, target_path, statuses=None):
        """
        Restores Modified and Deleted files from backup and verifies hashes against baseline.
        Never deletes Created (unknown) files.
        Returns: (restored_count, verified_count, failed_count)
        """
        if not target_path:
            return 0, 0, 0

        target_path = os.path.abspath(target_path)

        if statuses is None:
            if hasattr(self, "engine") and self.engine:
                statuses = self.engine.verify_integrity(target_path)
            else:
                statuses = []

        db_records = self.db.get_all_records()
        restored_count = 0
        verified_count = 0
        failed_count = 0

        for item in statuses:
            filepath = item[0]
            status = item[2]

            # Only restore files that are Modified or Deleted; NEVER touch or delete Created files
            if status not in ("Modified", "Deleted"):
                continue

            backup_file = self.get_backup_path_for_file(target_path, filepath)
            if not os.path.exists(backup_file):
                failed_count += 1
                continue

            try:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                shutil.copy2(backup_file, filepath)
                restored_count += 1

                # Verify restored file hash matches the trusted baseline in SQLite
                current_hash, _ = Hasher.calculate_sha256(filepath)
                expected_hash = db_records.get(filepath, {}).get("hash")

                if current_hash and expected_hash and current_hash == expected_hash:
                    verified_count += 1
                else:
                    failed_count += 1
            except (OSError, PermissionError):
                failed_count += 1

        return restored_count, verified_count, failed_count

    def get_backup_stats(self, target_path=None):
        """Returns statistics about the current backups."""
        last_time = self.db.get_setting("last_backup_time", "Never")
        if target_path:
            tdir = self.get_target_backup_dir(target_path)
            if os.path.exists(tdir):
                file_count = sum(len(files) for _, _, files in os.walk(tdir))
            else:
                file_count = 0
        else:
            if os.path.exists(self.backup_dir):
                file_count = sum(len(files) for _, _, files in os.walk(self.backup_dir))
            else:
                file_count = 0

        return {
            "backup_dir": self.backup_dir,
            "last_backup_time": last_time,
            "file_count": file_count
        }
