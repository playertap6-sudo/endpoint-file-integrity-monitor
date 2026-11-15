import os
import time
import threading
import concurrent.futures
import psutil


class SuspectInfo(dict):
    """Dictionary representing suspect process details with tuple unpacking support."""
    def __iter__(self):
        return iter((self['pid'], self['name'], self['cmdline'], self['open_files']))


class ProcessMonitor:
    PROTECTED_PROCESSES = {
        "explorer.exe",
        "svchost.exe",
        "system",
        "csrss.exe",
        "wininit.exe",
        "winlogon.exe",
        "services.exe",
        "lsass.exe"
    }

    # Script interpreters whose age we do NOT skip regardless of creation time
    SCRIPT_INTERPRETERS = {
        "python.exe",
        "pythonw.exe",
        "powershell.exe",
        "cmd.exe",
        "wscript.exe",
        "cscript.exe",
        "node.exe"
    }

    # Stage-2 open_files() scan: total wall-clock timeout (seconds)
    _STAGE2_TIMEOUT = 2.0
    # Number of parallel worker threads for stage-2
    _STAGE2_WORKERS = 16
    # Cache TTL in seconds
    _CACHE_TTL = 5.0

    def __init__(self, on_kill_success=None):
        self._cache_lock = threading.Lock()
        self._cache_key = None          # (norm_target, timestamp_bucket)
        self._cache_result = None       # list[SuspectInfo]
        self._cache_time = 0.0
        self.on_kill_success = on_kill_success

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_suspects(self, target_path):
        """
        Two-stage fast suspect scan.

        Stage 1 (instant): flag processes whose command line contains the
        monitored folder path (case-insensitive).  These are high-confidence
        and returned immediately merged at the top.

        Stage 2 (parallel): for the remaining processes that survive the
        pruning rules, call open_files() in a ThreadPoolExecutor (16 workers,
        2-second total wall-clock timeout).  Any process that errors or times
        out is silently skipped.

        Results are cached for _CACHE_TTL seconds so rapid repeated calls
        (auto-kill + UI update) do not trigger a fresh scan every time.
        """
        if not target_path or not os.path.exists(target_path):
            return []

        norm_target = os.path.abspath(target_path).replace("\\", "/").lower()

        # Return cached result if still fresh
        with self._cache_lock:
            if (self._cache_key == norm_target
                    and (time.monotonic() - self._cache_time) < self._CACHE_TTL):
                return list(self._cache_result)

        my_pid = os.getpid()
        try:
            parent_pid = psutil.Process(my_pid).ppid()
        except Exception:
            parent_pid = None

        now = time.time()
        one_hour_ago = now - 3600

        # Collect all process snapshots upfront (one cheap call)
        try:
            all_procs = list(psutil.process_iter(
                ["pid", "name", "cmdline", "exe", "create_time"]
            ))
        except Exception:
            all_procs = []

        stage1_pids = set()
        high_confidence = []
        stage2_candidates = []

        for proc in all_procs:
            try:
                info = proc.info
                pid = info["pid"]

                # Always exclude own process, parent, and kernel PIDs
                if pid == my_pid or pid in (0, 4):
                    continue
                if parent_pid and pid == parent_pid:
                    continue

                name_lower = (info.get("name") or "").lower()

                # --- Stage 1: cmdline contains the target path ---
                cmdline_parts = info.get("cmdline") or []
                cmdline_str = " ".join(cmdline_parts)
                cmdline_norm = cmdline_str.replace("\\", "/").lower()

                if norm_target in cmdline_norm:
                    stage1_pids.add(pid)
                    high_confidence.append(SuspectInfo({
                        "pid": pid,
                        "name": info.get("name") or "Unknown",
                        "cmdline": cmdline_str,
                        "open_files": 1,          # cmd-line match = at least 1 file involved
                        "high_confidence": True
                    }))
                    continue

                # --- Stage 2 pruning ---
                # Skip protected names
                if name_lower in self.PROTECTED_PROCESSES:
                    continue

                # Skip processes with no exe or running from C:\Windows
                exe = (info.get("exe") or "").replace("\\", "/").lower()
                if not exe:
                    continue
                if exe.startswith("c:/windows/"):
                    continue

                # Skip old non-interpreter processes
                create_time = info.get("create_time") or 0
                if create_time < one_hour_ago and name_lower not in self.SCRIPT_INTERPRETERS:
                    continue

                stage2_candidates.append((proc, info))

            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except Exception:
                continue

        # --- Stage 2: parallel open_files() scan ---
        stage2_suspects = self._stage2_scan(stage2_candidates, norm_target)

        # Merge: high-confidence first, then open-files matches (no dups)
        seen_pids = set(s["pid"] for s in high_confidence)
        merged = list(high_confidence)
        for s in stage2_suspects:
            if s["pid"] not in seen_pids:
                merged.append(s)
                seen_pids.add(s["pid"])

        # Update cache
        with self._cache_lock:
            self._cache_key = norm_target
            self._cache_result = list(merged)
            self._cache_time = time.monotonic()

        return merged

    def invalidate_cache(self):
        """Force the next find_suspects() call to do a fresh scan."""
        with self._cache_lock:
            self._cache_time = 0.0

    def kill_process(self, pid):
        """
        Terminates the specified process (terminate → wait 3 s → kill if alive).
        Returns (success: bool, message: str).
        Refuses to kill app's own PID, PID 0/4, parent PID, or any
        critically protected system process.
        """
        if pid is None or pid in (0, 4):
            return False, "Refused: Cannot terminate system idle or kernel process (PID 0/4)."

        my_pid = os.getpid()
        if pid == my_pid:
            return False, "Refused: Cannot terminate this application's own process."

        try:
            parent_pid = psutil.Process(my_pid).ppid()
            if pid == parent_pid:
                return False, "Refused: Cannot terminate the parent process of this application."
        except Exception:
            pass

        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False, f"Process with PID {pid} does not exist or has already terminated."
        except psutil.AccessDenied:
            return False, f"Access denied: Insufficient permissions to inspect PID {pid}."

        if proc_name.lower() in self.PROTECTED_PROCESSES:
            return False, f"Refused: '{proc_name}' (PID {pid}) is a critical protected system process."

        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            self.invalidate_cache()
            if self.on_kill_success:
                try:
                    self.on_kill_success(pid, proc_name)
                except Exception:
                    pass
            return True, f"Successfully terminated process '{proc_name}' (PID {pid})."
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            self.invalidate_cache()
            if self.on_kill_success:
                try:
                    self.on_kill_success(pid, proc_name)
                except Exception:
                    pass
            return True, f"Process '{proc_name}' (PID {pid}) has been terminated."
        except psutil.AccessDenied:
            return False, f"Access denied: Administrator privileges required to terminate PID {pid}."
        except Exception as e:
            return False, f"Failed to terminate PID {pid}: {str(e)}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _stage2_scan(self, candidates, norm_target):
        """
        Runs open_files() on each candidate process in a thread pool.
        Returns a list of SuspectInfo for those with matching open handles.
        Total wall-clock time is capped at _STAGE2_TIMEOUT seconds.
        """
        suspects = []
        if not candidates:
            return suspects

        def check_one(proc_and_info):
            proc, info = proc_and_info
            try:
                open_files = proc.open_files()
            except Exception:
                return None

            matched = 0
            for f in open_files:
                try:
                    f_norm = os.path.abspath(f.path).replace("\\", "/").lower()
                    if os.path.isfile(norm_target):
                        if f_norm == norm_target:
                            matched += 1
                    else:
                        if f_norm == norm_target or f_norm.startswith(norm_target + "/"):
                            matched += 1
                except Exception:
                    continue

            if matched > 0:
                cmdline_parts = info.get("cmdline") or []
                return SuspectInfo({
                    "pid": info["pid"],
                    "name": info.get("name") or "Unknown",
                    "cmdline": " ".join(cmdline_parts),
                    "open_files": matched,
                    "high_confidence": False
                })
            return None

        deadline = time.monotonic() + self._STAGE2_TIMEOUT

        with concurrent.futures.ThreadPoolExecutor(max_workers=self._STAGE2_WORKERS) as ex:
            futures = {ex.submit(check_one, c): c for c in candidates}
            try:
                for fut in concurrent.futures.as_completed(
                    futures, timeout=max(0.1, deadline - time.monotonic())
                ):
                    try:
                        result = fut.result(timeout=0)
                        if result is not None:
                            suspects.append(result)
                    except Exception:
                        continue
            except (TimeoutError, Exception):
                pass

        return suspects
