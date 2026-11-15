import hashlib
import os

class Hasher:
    @staticmethod
    def calculate_sha256(filepath):
        """Computes SHA-256 and safely extracts text content from a file."""
        sha256_hash = hashlib.sha256()
        content = ""
        try:
            # Read block chunks for large files securely
            with open(filepath, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            
            # Only store file content for files under 1 MB that decode as text
            if os.path.getsize(filepath) < 1024 * 1024:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                except UnicodeDecodeError:
                    content = ""
                
            return sha256_hash.hexdigest(), content
        except (OSError, PermissionError, FileNotFoundError):
            return None, ""
