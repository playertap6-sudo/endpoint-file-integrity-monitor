#!/usr/bin/env python3
"""
=============================================================================
CLASSROOM PRESENTATION SIMULATOR ONLY
=============================================================================
This script is a harmless classroom educational demonstration tool designed
solely to test and present the File Integrity Monitor's ransomware detection,
process investigation, and backup-restoration capabilities.

SAFETY SAFEGUARDS:
- Must only be pointed at an isolated test directory.
- Refuses to run on drive roots (e.g. C:\\ or /) or user home folders.
- Requires explicit user confirmation ("YES") before execution.
- Only touches .txt files in the top-level directory (never recurses).
- Does not rename files, does not touch the network, does not copy itself,
  and does not persist or modify startup settings.
- Scrambling is non-destructive (reversible base64 encoding).

USAGE:
    python fake_ransomware.py <path_to_test_folder> [--delay SECONDS]

    --delay SECONDS   Pause between processing each file (default: 3).
                      Each file handle is also held open for the same duration
                      so the Process Investigator can catch the open handle.
=============================================================================
"""

import os
import sys
import time
import base64
import argparse


def is_drive_root(path):
    """Checks if a normalized path represents a drive root."""
    norm = os.path.abspath(path)
    drive, rest = os.path.splitdrive(norm)
    if rest in ('\\', '/', '', '\\\\') or norm == os.path.abspath(drive + '\\'):
        return True
    return norm in ('/', '\\')


def is_user_home(path):
    """Checks if a normalized path represents the user's home directory."""
    norm = os.path.abspath(path).lower()
    home = os.path.abspath(os.path.expanduser("~")).lower()
    return norm == home


def main():
    parser = argparse.ArgumentParser(
        description="Educational ransomware simulator for FIM classroom demo."
    )
    parser.add_argument("target_dir", help="Path to the isolated test folder to simulate on.")
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        metavar="SECONDS",
        help="Seconds to hold each file handle open and pause between files (default: 3)."
    )
    args = parser.parse_args()

    target_dir = args.target_dir
    delay = max(0.5, args.delay)   # floor at 0.5 s to keep demo safe

    # Verification checks
    if not os.path.exists(target_dir):
        print(f"Error: Target path '{target_dir}' does not exist.")
        sys.exit(1)

    if not os.path.isdir(target_dir):
        print(f"Error: Target path '{target_dir}' is not a directory.")
        sys.exit(1)

    abs_target = os.path.abspath(target_dir)

    if is_drive_root(abs_target):
        print(f"SECURITY REFUSAL: Cannot target a drive root ({abs_target})!")
        sys.exit(1)

    if is_user_home(abs_target):
        print(f"SECURITY REFUSAL: Cannot target the user home directory ({abs_target})!")
        sys.exit(1)

    print("=================================================================")
    print("      EDUCATIONAL CLASSROOM RANSOMWARE SIMULATION TOOL           ")
    print("=================================================================")
    print(f"Process PID   : {os.getpid()}")
    print(f"Target        : {abs_target}")
    print(f"Handle delay  : {delay} second(s) per file")
    print("Action        : Reversible base64 scramble of top-level .txt files")
    print("=================================================================")
    print("WARNING: Type YES in all-caps to proceed, or anything else to abort.")

    try:
        confirm = input("Confirm: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(0)

    if confirm != "YES":
        print("Confirmation failed. Simulation aborted.")
        sys.exit(0)

    # Process .txt files in top-level target_dir only (no subfolders)
    txt_files = [
        f for f in os.listdir(abs_target)
        if os.path.isfile(os.path.join(abs_target, f)) and f.lower().endswith('.txt')
    ]

    if not txt_files:
        print(f"No .txt files found in {abs_target}. Nothing to simulate.")
        sys.exit(0)

    print(f"\n[!] Starting simulated encryption attack on {len(txt_files)} file(s)…")
    print(f"[!] PID {os.getpid()} — the FIM Process Investigator should detect this process.\n")

    for fname in txt_files:
        full_path = os.path.join(abs_target, fname)
        print(f"[>] Attacking: {fname}  (holding handle open for {delay}s)…", flush=True)

        try:
            # Open file with read/write access and hold handle open for `delay` seconds
            # so the FIM Process Investigator can capture the open file handle.
            with open(full_path, "r+b") as f:
                content = f.read()

                # Hold the handle open — this is what the Process Investigator detects
                time.sleep(delay)

                # Reversibly scramble content using base64 encoding
                scrambled = b"ENCRYPTED_SIMULATION::" + base64.b64encode(content)
                f.seek(0)
                f.write(scrambled)
                f.truncate()

            print(f"[✓] Scrambled: {fname}")
        except Exception as e:
            print(f"[!] Error attacking {fname}: {e}")

        # Pause between files (matches the handle-hold delay so both together = 2×delay
        # for maximum detectability; remove or reduce if you need a faster demo)
        if fname != txt_files[-1]:
            print(f"    Waiting {delay}s before next file…", flush=True)
            time.sleep(delay)

    print("\n[!] Simulated ransomware attack cycle complete.")
    print(f"[!] Use 'Restore Now' in the FIM banner to recover all scrambled files.")


if __name__ == "__main__":
    main()
