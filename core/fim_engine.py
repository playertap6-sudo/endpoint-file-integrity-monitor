import os
from datetime import datetime
from core.hasher import Hasher

class FIMEngine:
    def __init__(self, db_manager, backup_manager=None):
        self.db = db_manager
        self.backup_manager = backup_manager

    def generate_baseline(self, target_path):
        """Scans a directory or a single file, commits baselines to DB, and backs up files."""
        if not target_path or not os.path.exists(target_path):
            return 0

        # Standardize target_path for mapping uniformity
        target_path = os.path.abspath(target_path)
        count = 0
        valid_files = []
        
        if os.path.isfile(target_path):
            file = os.path.basename(target_path)
            sha_hash, content = Hasher.calculate_sha256(target_path)
            if sha_hash:
                self.db.save_baseline(target_path, file, sha_hash, content)
                count += 1
                valid_files.append(target_path)
        else:
            for root, _, files in os.walk(target_path):
                for file in files:
                    full_path = os.path.abspath(os.path.join(root, file))
                    sha_hash, content = Hasher.calculate_sha256(full_path)
                    if sha_hash:
                        self.db.save_baseline(full_path, file, sha_hash, content)
                        count += 1
                        valid_files.append(full_path)

        # Mirror baseline to secure backup folder
        if self.backup_manager:
            self.backup_manager.create_baseline_backup(target_path, valid_files)

        return count

    def verify_integrity(self, target_path):
        """Compares current file or directory states against the stored baseline state."""
        results = []
        if not target_path:
            return results

        target_path = os.path.abspath(target_path)
        db_records = self.db.get_all_records()
        current_files = set()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Step 1: Detect changes and additions if path physically exists on disk
        if os.path.exists(target_path):
            if os.path.isfile(target_path):
                file = os.path.basename(target_path)
                current_files.add(target_path)
                current_hash, _ = Hasher.calculate_sha256(target_path)
                
                if current_hash:
                    if target_path not in db_records:
                        results.append((target_path, file, "Created", timestamp, None, current_hash))
                    elif current_hash != db_records[target_path]["hash"]:
                        results.append((target_path, file, "Modified", timestamp, db_records[target_path]["hash"], current_hash))
                    else:
                        results.append((target_path, file, "Unchanged", db_records[target_path]["seen"], db_records[target_path]["hash"], current_hash))
            else:
                for root, _, files in os.walk(target_path):
                    for file in files:
                        full_path = os.path.abspath(os.path.join(root, file))
                        current_files.add(full_path)
                        current_hash, _ = Hasher.calculate_sha256(full_path)

                        if not current_hash:
                            continue

                        if full_path not in db_records:
                            results.append((full_path, file, "Created", timestamp, None, current_hash))
                        elif current_hash != db_records[full_path]["hash"]:
                            results.append((full_path, file, "Modified", timestamp, db_records[full_path]["hash"], current_hash))
                        else:
                            results.append((full_path, file, "Unchanged", db_records[full_path]["seen"], db_records[full_path]["hash"], current_hash))

        # Step 2: Detect structural deletions
        for missing_path, meta in db_records.items():
            normalized_missing = os.path.abspath(missing_path)
            
            # Check if this database item belongs inside our targeted check path
            is_match = False
            if target_path == normalized_missing:
                is_match = True
            elif os.path.isdir(target_path) and normalized_missing.startswith(target_path + os.sep):
                is_match = True
                
            if is_match and normalized_missing not in current_files:
                results.append((normalized_missing, meta["filename"], "Deleted", timestamp, meta["hash"], None))

        return results

    def accept_changes(self, target_path):
        """Updates baseline and backup: updates Modified/Created files and removes Deleted files."""
        if not target_path:
            return 0

        target_path = os.path.abspath(target_path)
        scan_results = self.verify_integrity(target_path)
        count = 0

        for item in scan_results:
            filepath, filename, status = item[0], item[1], item[2]
            if status in ("Modified", "Created"):
                sha_hash, content = Hasher.calculate_sha256(filepath)
                if sha_hash:
                    self.db.save_baseline(filepath, filename, sha_hash, content)
                    count += 1
            elif status == "Deleted":
                self.db.delete_record(filepath)
                count += 1

        # Keep backup in sync with accepted baseline
        if self.backup_manager:
            self.backup_manager.update_backup_on_accept(target_path, scan_results)

        return count
