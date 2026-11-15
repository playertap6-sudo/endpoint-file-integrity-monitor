"""
gui/spider_overlay.py
Procedural arachnid overlay rendered on a click-through transparent Toplevel canvas.

Features:
- Borderless Toplevel synced to main window geometry across all pages (never topmost).
- Transparent background via -transparentcolor allowing all clicks to pass through.
- Procedural 8-legged inverse-kinematics spider with glowing cyan dual-stroke legs.
- Runs constantly across all sidebar pages. Only pauses when main window is iconic (minimized).
- 2-second watchdog timer automatically revives the animation loop if interrupted.
- Event-driven behaviors via spider.notify(event, data):
  • idle: wandering and resting anywhere across the entire window.
  • scan_done: crawls to changed rows in the Threats table and draws colored outline boxes.
    Falls back to banner or sidebar if not on Dashboard.
  • alert: rushes to ransomware banner, pulsing red, patrolling quickly until cleared.
  • suspect_found: scuttles to investigation banner with alert pulse.
  • process_killed: pounces with an expanding ring, then resumes idle.
  • restore_done: celebration spin with green sparkles, then resumes idle.
"""

import math
import random
import time
import tkinter as tk


class SpiderOverlay:
    """Transparent overlay hosting the procedural spider and interactive visual effects."""

    TRANS_COLOR = "#050505"      # Unique color keyed for Windows transparency
    CYAN_GLOW   = "#22d3ee"      # Light glowing cyan for spider body & legs
    CYAN_DARK   = "#082f49"      # Dim outline color for legs
    RED_PULSE   = "#ef4444"      # Alert state red pulse
    TICK_MS     = 30             # ~33 FPS animation interval

    STATUS_COLORS = {
        "Modified": "#ef4444",
        "Created":  "#22c55e",
        "Deleted":  "#eab308",
    }

    def __init__(self, root, app, db_manager=None):
        self.root = root
        self.app = app
        self.db = db_manager

        # Animation state and preferences
        self.enabled = True
        if self.db:
            try:
                setting_val = self.db.get_setting("spider_animation", "true")
                self.enabled = str(setting_val).lower() != "false"
            except Exception:
                self.enabled = True

        # Exactly one animation loop with is_running flag & single after id
        self.is_running = False
        self.anim_timer = None
        self.watchdog_timer = None
        self.last_heartbeat = time.time()
        self.current_fps_delay = self.TICK_MS

        # Geometry sync debounce & deduplication
        self._last_root_geom = None
        self._last_overlay_geom = None
        self._sync_debounce_id = None
        self._in_sync = False

        # Spider position & kinematic state
        self.x = 220.0
        self.y = 220.0
        self.angle = 0.0
        self.speed = 2.2
        self.color_glow = self.CYAN_GLOW
        self.alert_pulse_phase = 0

        # Behavioral state machine: "idle", "crawl_rows", "alert", "pounce", "celebrate"
        self.mode = "idle"
        self.target_x = 320.0
        self.target_y = 320.0
        self.pause_ticks = 0

        # Row crawling queue for scan_done
        self.row_targets = []

        # Visual FX state
        self.fx_ticks = 0
        self.fx_data = {}

        # Persistent canvas items for coords() reuse
        self.leg_items = []
        self.item_abdomen = None
        self.item_thorax = None
        self.item_head = None
        self.item_eyes = []
        self.item_shockwave = None
        self.item_sparkles = []
        self._last_drawn_glow = None

        # Procedural 8 legs (nominal foot offsets relative to body)
        self.nominal_feet = [
            (-24.0, -14.0), (-30.0, -3.0), (-30.0, 7.0), (-22.0, 18.0),
            ( 24.0, -14.0), ( 30.0, -3.0), ( 30.0, 7.0), ( 22.0, 18.0),
        ]
        self.feet_pos = [None] * 8
        self.feet_stepping = [False] * 8
        self.feet_step_start = [None] * 8
        self.feet_step_target = [None] * 8
        self.feet_step_progress = [1.0] * 8
        self.gait_group = 0
        self.gait_counter = 0
        self.gait_a = [0, 2, 5, 7]
        self.gait_b = [1, 3, 4, 6]

        self._setup_overlay()
        self.init_feet()
        self.pick_random_wander()

        if self.enabled:
            self.start_loop()

        # Start 2-second persistent watchdog
        self._schedule_watchdog()

    # ─────────────────────────────────────────────────────────────────
    # Overlay Window Creation & Geometry Sync
    # ─────────────────────────────────────────────────────────────────

    def _setup_overlay(self):
        try:
            self.win = tk.Toplevel(self.root)
            self.win.overrideredirect(True)
            self.win.transient(self.root)

            # Transparent click-through canvas on Windows
            self.win.config(bg=self.TRANS_COLOR)
            try:
                self.win.attributes("-transparentcolor", self.TRANS_COLOR)
            except Exception:
                pass

            self.canvas = tk.Canvas(
                self.win,
                bg=self.TRANS_COLOR,
                highlightthickness=0,
                bd=0
            )
            self.canvas.pack(fill="both", expand=True)

            # Pre-create reusable canvas items once
            self._init_canvas_items()

            # Bind window lifecycle events for continuous overlay synchronization
            self.root.bind("<Configure>", self._on_root_configure, add="+")
            self.root.bind("<Map>", self._on_root_map, add="+")
            self.root.bind("<Unmap>", self._on_root_unmap, add="+")
            self.root.bind("<FocusIn>", self._on_root_focus_in, add="+")
            self.root.bind("<Visibility>", self._on_root_visibility, add="+")

            self.sync_geometry()
        except Exception as e:
            print(f"[Spider Setup Error] {e}")

    def _init_canvas_items(self):
        """Creates canvas items once so tick() updates coords() without delete/create overhead."""
        self.leg_items = []
        for _ in range(8):
            self.leg_items.append({
                "u_dark": self.canvas.create_line(0, 0, 0, 0, fill=self.CYAN_DARK, width=3.5, capstyle="round", tags="spider"),
                "l_dark": self.canvas.create_line(0, 0, 0, 0, fill=self.CYAN_DARK, width=3.0, capstyle="round", tags="spider"),
                "u_glow": self.canvas.create_line(0, 0, 0, 0, fill=self.CYAN_GLOW, width=1.8, capstyle="round", tags="spider"),
                "l_glow": self.canvas.create_line(0, 0, 0, 0, fill=self.CYAN_GLOW, width=1.5, capstyle="round", tags="spider"),
            })

        self.item_abdomen = self.canvas.create_oval(
            0, 0, 0, 0, fill=self.CYAN_GLOW, outline=self.CYAN_DARK, width=1.5, tags="spider"
        )
        self.item_thorax = self.canvas.create_oval(
            0, 0, 0, 0, fill=self.CYAN_GLOW, outline=self.CYAN_DARK, width=1.2, tags="spider"
        )
        self.item_head = self.canvas.create_oval(
            0, 0, 0, 0, fill=self.CYAN_GLOW, outline=self.CYAN_DARK, width=1.0, tags="spider"
        )
        self.item_eyes = [
            self.canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline="", tags="spider"),
            self.canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline="", tags="spider")
        ]

        self.item_shockwave = self.canvas.create_oval(
            0, 0, 0, 0, outline=self.CYAN_GLOW, width=2, state="hidden", tags="fx"
        )
        self.item_sparkles = [
            self.canvas.create_oval(0, 0, 0, 0, fill="#22c55e", outline="#86efac", width=1, state="hidden", tags="fx")
            for _ in range(14)
        ]
        self._last_drawn_glow = self.CYAN_GLOW

    def sync_geometry(self):
        """Matches overlay geometry exactly to root window position and size without recursion."""
        if self._in_sync:
            return
        self._in_sync = True
        try:
            if not self.win or not self.win.winfo_exists():
                return
            if self.root.state() == "iconic":
                return

            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()

            if rw > 50 and rh > 50:
                target_geom = f"{rw}x{rh}+{rx}+{ry}"
                if target_geom != self._last_overlay_geom:
                    self._last_overlay_geom = target_geom
                    self.win.geometry(target_geom)
        except Exception:
            pass
        finally:
            self._in_sync = False

    def _on_root_configure(self, event):
        """Only reacts when the configure event is dispatched for the root window itself."""
        if event.widget is not self.root:
            return

        try:
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
        except Exception:
            return

        curr_geom = (rx, ry, rw, rh)
        if curr_geom == self._last_root_geom:
            return
        self._last_root_geom = curr_geom

        # Debounce geometry update by 50ms
        if self._sync_debounce_id is not None:
            try:
                self.root.after_cancel(self._sync_debounce_id)
            except Exception:
                pass
            self._sync_debounce_id = None

        self._sync_debounce_id = self.root.after(50, self._debounced_sync)

    def _debounced_sync(self):
        self._sync_debounce_id = None
        self.sync_geometry()

    def _on_root_map(self, event=None):
        if event and event.widget is not self.root:
            return
        self.resume()

    def _on_root_unmap(self, event=None):
        if event and event.widget is not self.root:
            return
        try:
            if self.win and self.win.winfo_exists():
                self.win.withdraw()
        except Exception:
            pass

    def _on_root_focus_in(self, event=None):
        if event and event.widget is not self.root:
            return
        self.resume()

    def _on_root_visibility(self, event=None):
        if event and event.widget is not self.root:
            return
        self.resume()

    def resume(self):
        """
        Resumes the spider animation after window focus change, dialog close, page switch, or user action.
        Cancels the old loop id, re-syncs overlay geometry, calls deiconify() and lift(),
        clears stuck states, and starts exactly one new animation loop.
        """
        if not self.enabled:
            return
        try:
            # 1. Cancel old loop id
            if self.anim_timer is not None:
                try:
                    self.root.after_cancel(self.anim_timer)
                except Exception:
                    pass
                self.anim_timer = None
            self.is_running = False

            # 2. Reset geometry sync locks
            self._in_sync = False
            self._last_overlay_geom = None
            self._last_root_geom = None

            # 3. Re-show and lift overlay
            if self.win and self.win.winfo_exists():
                try:
                    if self.root.state() != "iconic":
                        self.win.deiconify()
                        self.win.lift()
                except Exception:
                    pass

            # 4. Re-sync geometry to main window
            self.sync_geometry()

            # 5. Clear stuck behavioral states
            self.pause_ticks = 0
            if self.mode not in ("alert", "crawl_rows", "pounce", "celebrate"):
                self.mode = "idle"
                self.speed = 2.2
            if self.mode == "crawl_rows" and not self.row_targets:
                self.mode = "idle"
                self.speed = 2.2
                self.pick_random_wander()

            # 6. Start exactly one new loop
            self.start_loop()
        except Exception as e:
            print(f"[Spider Resume Error] {e}")
            import traceback
            traceback.print_exc()
            self.start_loop()

    def _schedule_watchdog(self):
        """Maintains exactly one watchdog instance every 1 second."""
        if self.watchdog_timer is not None:
            try:
                self.root.after_cancel(self.watchdog_timer)
            except Exception:
                pass
            self.watchdog_timer = None
        self.watchdog_timer = self.root.after(1000, self._run_watchdog)

    def _run_watchdog(self):
        """Watchdog check: restarts loop if heartbeat > 1.5s, re-shows if hidden, and re-syncs if drifted."""
        self.watchdog_timer = None
        try:
            if not self.enabled:
                return

            if self.root.state() == "iconic":
                return

            now = time.time()
            restarted = False

            # 1. Heartbeat check (> 1.5s or not running)
            heartbeat_age = now - self.last_heartbeat
            if not self.is_running:
                print(f"[Spider Watchdog] Restarting loop: animation was not running (heartbeat age: {heartbeat_age:.2f}s)")
                self.resume()
                restarted = True
            elif heartbeat_age > 1.5:
                print(f"[Spider Watchdog] Restarting loop: heartbeat timed out ({heartbeat_age:.2f}s > 1.5s)")
                self.resume()
                restarted = True

            # 2. Check visibility (hidden or withdrawn)
            if self.win and self.win.winfo_exists():
                try:
                    if not self.win.winfo_viewable() and self.root.state() != "iconic":
                        self.win.deiconify()
                        self.win.lift()
                        if not restarted:
                            print("[Spider Watchdog] Re-showing overlay: window was hidden or withdrawn")
                            self.resume()
                            restarted = True
                except Exception:
                    pass

            # 3. Geometry drift check
            if not restarted and self.win and self.win.winfo_exists() and self.root.state() != "iconic":
                try:
                    rx = self.root.winfo_rootx()
                    ry = self.root.winfo_rooty()
                    rw = self.root.winfo_width()
                    rh = self.root.winfo_height()

                    ox = self.win.winfo_rootx()
                    oy = self.win.winfo_rooty()
                    ow = self.win.winfo_width()
                    oh = self.win.winfo_height()

                    if abs(rx - ox) > 2 or abs(ry - oy) > 2 or abs(rw - ow) > 2 or abs(rh - oh) > 2:
                        print("[Spider Watchdog] Re-syncing overlay geometry: drifted from main window")
                        self.sync_geometry()
                        self.win.lift()
                except Exception:
                    pass

        except Exception as e:
            print(f"[Spider Watchdog Error] {e}")
        finally:
            self._schedule_watchdog()

    def set_enabled(self, enabled: bool):
        """Enables or disables the spider animation overlay."""
        self.enabled = bool(enabled)
        if self.enabled:
            try:
                if self.win and self.win.winfo_exists():
                    self.win.deiconify()
                    self.sync_geometry()
            except Exception:
                pass
            self.start_loop()
        else:
            self.stop_loop()
            try:
                if self.win and self.win.winfo_exists():
                    self.win.withdraw()
            except Exception:
                pass

    def start_loop(self):
        """Starts the animation loop, ensuring only one instance runs."""
        if not self.enabled:
            return
        if self.anim_timer is not None:
            try:
                self.root.after_cancel(self.anim_timer)
            except Exception:
                pass
            self.anim_timer = None

        self.is_running = True
        self.last_heartbeat = time.time()
        self.anim_timer = self.root.after(self.current_fps_delay, self.tick)

    def stop_loop(self):
        """Stops the animation loop and cancels the scheduled timer."""
        self.is_running = False
        if self.anim_timer is not None:
            try:
                self.root.after_cancel(self.anim_timer)
            except Exception:
                pass
            self.anim_timer = None

    # ─────────────────────────────────────────────────────────────────
    # Event Hook: spider.notify(event, data)
    # ─────────────────────────────────────────────────────────────────

    def notify(self, event: str, data=None):
        """
        Receives notification events from core application lifecycle:
        'scan_done', 'alert', 'alert_cleared', 'suspect_found', 'process_killed', 'restore_done', 'idle', etc.
        """
        try:
            if event == "scan_done":
                self._handle_scan_done(data)
            elif event == "alert":
                self.mode = "alert"
                self.speed = 8.0
                self.pause_ticks = 0
            elif event == "alert_cleared":
                self.mode = "idle"
                self.color_glow = self.CYAN_GLOW
                self.speed = 2.2
                self.pick_random_wander()
            elif event == "suspect_found":
                self.mode = "alert"
                self.speed = 7.5
                self.pause_ticks = 0
            elif event == "process_killed":
                self._handle_process_killed()
            elif event == "restore_done":
                self._handle_restore_done()
            elif event in ("idle", "baseline_done", "accept_changes"):
                self.mode = "idle"
                self.speed = 2.2
                self.pick_random_wander()
        except Exception as e:
            print(f"[Spider Notify Error] (event={event}): {e}")
            import traceback
            traceback.print_exc()
            self.mode = "idle"
            self.color_glow = self.CYAN_GLOW
            self.speed = 2.2
            self.pick_random_wander()

    def _handle_scan_done(self, data):
        """Queues visible changed rows from the Threats table, or falls back to banner/sidebar."""
        try:
            try:
                self.canvas.delete("scan_outline")
            except Exception:
                pass

            self.row_targets = []
            is_on_dashboard = (getattr(self.app, "active_page_name", "") == "Dashboard")

            # If not on Dashboard, spider goes to the banner or sidebar instead of failing
            if not is_on_dashboard or not data:
                self._fallback_to_banner_or_sidebar()
                return

            tree = data.get("tree")
            matches = data.get("matches", [])
            if not tree or not matches:
                self._fallback_to_banner_or_sidebar()
                return

            # Filter changed files (Modified, Created, Deleted), capped at 15
            changed_matches = [
                m for m in matches if len(m) > 2 and m[2] in ("Modified", "Created", "Deleted")
            ][:15]

            if not changed_matches:
                self.mode = "idle"
                self.pick_random_wander()
                return

            # Measure root and tree position once (without calling update_idletasks)
            try:
                tree_root_x = tree.winfo_rootx() - self.root.winfo_rootx()
                tree_root_y = tree.winfo_rooty() - self.root.winfo_rooty()
                tree_w = tree.winfo_width()
            except Exception:
                self._fallback_to_banner_or_sidebar()
                return

            items = tree.get_children()
            iid_by_path = {}
            for iid in items:
                vals = tree.item(iid, "values")
                if vals and len(vals) > 0:
                    iid_by_path[vals[0]] = iid

            for m in changed_matches:
                fpath = m[0]
                status = m[2]
                iid = iid_by_path.get(fpath)
                if not iid:
                    continue

                try:
                    bbox = tree.bbox(iid)
                except Exception:
                    bbox = None

                if bbox and len(bbox) == 4:
                    x1 = tree_root_x + bbox[0]
                    y1 = tree_root_y + bbox[1]
                    x2 = tree_root_x + tree_w - 24
                    y2 = tree_root_y + bbox[1] + bbox[3]

                    color = self.STATUS_COLORS.get(status, self.CYAN_GLOW)
                    self.row_targets.append({
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "target_x": (x1 + x2) / 2.0,
                        "target_y": (y1 + y2) / 2.0,
                        "color": color
                    })

            if self.row_targets:
                self.mode = "crawl_rows"
                self.speed = 3.5
                self.pause_ticks = 0
                first_target = self.row_targets[0]
                self.target_x = first_target["target_x"]
                self.target_y = first_target["target_y"]
            else:
                self._fallback_to_banner_or_sidebar()
        except Exception as e:
            print(f"[Spider Scan Done Error] {e}")
            import traceback
            traceback.print_exc()
            self.mode = "idle"
            self.speed = 2.2
            self.pick_random_wander()

    def _fallback_to_banner_or_sidebar(self):
        """Fallback navigation when target rows are not present on the current page."""
        try:
            banner = getattr(self.app, "banner", None)
            if banner and banner.winfo_manager():
                bx = banner.winfo_rootx() - self.root.winfo_rootx() + banner.winfo_width() / 2.0
                by = banner.winfo_rooty() - self.root.winfo_rooty() + 20.0
                self.target_x = bx
                self.target_y = by
            else:
                self.target_x = 90.0
                self.target_y = random.uniform(140.0, 360.0)
            self.mode = "crawl_rows"
            self.speed = 4.5
            self.pause_ticks = 10
            self.row_targets = []
        except Exception:
            self.mode = "idle"
            self.pick_random_wander()

    def _handle_process_killed(self):
        """Triggers quick pounce animation with an expanding shockwave ring."""
        self.mode = "pounce"
        self.fx_ticks = 18
        self.fx_data = {
            "origin_x": self.x,
            "origin_y": self.y,
            "radius": 6.0
        }

    def _handle_restore_done(self):
        """Triggers celebration spin animation with radiating green sparkles."""
        self.mode = "celebrate"
        self.fx_ticks = 24
        sparkles = []
        for _ in range(14):
            angle = random.uniform(0, 2 * math.pi)
            spd = random.uniform(2.5, 5.5)
            sparkles.append({
                "x": self.x,
                "y": self.y,
                "dx": math.cos(angle) * spd,
                "dy": math.sin(angle) * spd,
            })
        self.fx_data = {"sparkles": sparkles}

    # ─────────────────────────────────────────────────────────────────
    # Procedural Spider Stepping & Kinematics
    # ─────────────────────────────────────────────────────────────────

    def init_feet(self):
        cos_a = math.cos(self.angle - math.pi / 2)
        sin_a = math.sin(self.angle - math.pi / 2)
        for i in range(8):
            rx, ry = self.nominal_feet[i]
            wx = self.x + (rx * cos_a - ry * sin_a)
            wy = self.y + (rx * sin_a + ry * cos_a)
            self.feet_pos[i] = (wx, wy)
            self.feet_stepping[i] = False
            self.feet_step_progress[i] = 1.0

    def update_feet(self, moving=True):
        cos_a = math.cos(self.angle - math.pi / 2)
        sin_a = math.sin(self.angle - math.pi / 2)

        self.gait_counter += 1
        if moving and self.gait_counter % 3 == 0:
            self.gait_group = 1 - self.gait_group

        active_group = self.gait_a if self.gait_group == 0 else self.gait_b
        lead_x = math.cos(self.angle) * (self.speed * 2.4)
        lead_y = math.sin(self.angle) * (self.speed * 2.4)

        step_dist_limit = 13.0

        for i in range(8):
            rx, ry = self.nominal_feet[i]
            ideal_x = self.x + (rx * cos_a - ry * sin_a) + (lead_x if moving else 0.0)
            ideal_y = self.y + (rx * sin_a + ry * cos_a) + (lead_y if moving else 0.0)

            cur_x, cur_y = self.feet_pos[i]

            if self.feet_stepping[i]:
                self.feet_step_progress[i] += 0.38
                p = min(1.0, self.feet_step_progress[i])
                sx, sy = self.feet_step_start[i]
                tx, ty = self.feet_step_target[i]
                self.feet_pos[i] = (sx + (tx - sx) * p, sy + (ty - sy) * p)
                if p >= 1.0:
                    self.feet_stepping[i] = False
            else:
                dist = math.hypot(cur_x - ideal_x, cur_y - ideal_y)
                if moving and dist > step_dist_limit and (i in active_group):
                    self.feet_stepping[i] = True
                    self.feet_step_start[i] = (cur_x, cur_y)
                    self.feet_step_target[i] = (
                        ideal_x + random.uniform(-1.5, 1.5),
                        ideal_y + random.uniform(-1.5, 1.5)
                    )
                    self.feet_step_progress[i] = 0.0

    # ─────────────────────────────────────────────────────────────────
    # Core Animation Tick Loop (Always Alive, Single Timer, Dynamic FPS)
    # ─────────────────────────────────────────────────────────────────

    def tick(self):
        """Executes one frame of procedural animation."""
        if not self.enabled:
            self.is_running = False
            self.anim_timer = None
            return

        self.last_heartbeat = time.time()
        t_start = time.perf_counter()

        # If minimized (iconic), pause motion and check again
        try:
            if self.root.state() == "iconic":
                self.anim_timer = self.root.after(250, self.tick)
                return
        except Exception:
            pass

        try:
            if self.mode == "idle":
                self._tick_idle()
            elif self.mode == "crawl_rows":
                self._tick_crawl_rows()
            elif self.mode == "alert":
                self._tick_alert()
            elif self.mode == "pounce":
                self._tick_pounce()
            elif self.mode == "celebrate":
                self._tick_celebrate()
            else:
                self.mode = "idle"
                self.pick_random_wander()

            self.draw_spider()
            self.draw_fx()
        except Exception as e:
            print(f"[Spider Frame Error] {e}")
            import traceback
            traceback.print_exc()
            self.mode = "idle"
            self.color_glow = self.CYAN_GLOW
            self.speed = 2.2
            self.pick_random_wander()
        finally:
            if self.enabled:
                self.is_running = True
                frame_duration = time.perf_counter() - t_start
                # Lower frame rate to ~25 fps if frame takes longer than 8ms
                if frame_duration > 0.008:
                    self.current_fps_delay = 40
                else:
                    self.current_fps_delay = self.TICK_MS
                self.anim_timer = self.root.after(self.current_fps_delay, self.tick)
            else:
                self.is_running = False
                self.anim_timer = None

    def _tick_idle(self):
        if self.pause_ticks > 0:
            self.pause_ticks -= 1
            self.update_feet(moving=False)
            return

        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy)

        if dist < 6.0:
            self.pause_ticks = random.randint(30, 80)
            self.pick_random_wander()
            self.update_feet(moving=False)
        else:
            self._steer_towards(dx, dy)
            self.x += math.cos(self.angle) * self.speed
            self.y += math.sin(self.angle) * self.speed
            self.update_feet(moving=True)

    def _tick_crawl_rows(self):
        try:
            if self.pause_ticks > 0:
                self.pause_ticks -= 1
                self.update_feet(moving=False)
                return

            if not self.row_targets:
                self.mode = "idle"
                self.speed = 2.2
                self.pick_random_wander()
                return

            current_row = self.row_targets[0]
            tx, ty = current_row.get("target_x"), current_row.get("target_y")
            if tx is None or ty is None:
                self.row_targets.pop(0)
                if not self.row_targets:
                    self.mode = "idle"
                    self.speed = 2.2
                    self.pick_random_wander()
                return

            dx = tx - self.x
            dy = ty - self.y
            dist = math.hypot(dx, dy)

            if dist < self.speed + 2.0:
                self.x = tx
                self.y = ty
                # Draw colored outline rectangle on this row
                try:
                    self.canvas.create_rectangle(
                        current_row["x1"], current_row["y1"],
                        current_row["x2"], current_row["y2"],
                        outline=current_row["color"],
                        width=2,
                        fill="",
                        tags="scan_outline"
                    )
                except Exception:
                    pass
                self.pause_ticks = 8
                self.row_targets.pop(0)
                if self.row_targets:
                    next_row = self.row_targets[0]
                    self.target_x = next_row.get("target_x", self.x)
                    self.target_y = next_row.get("target_y", self.y)
                else:
                    self.mode = "idle"
                    self.speed = 2.2
                    self.pick_random_wander()
                self.update_feet(moving=False)
            else:
                self._steer_towards(dx, dy)
                self.x += math.cos(self.angle) * self.speed
                self.y += math.sin(self.angle) * self.speed
                self.update_feet(moving=True)
        except Exception as e:
            print(f"[Spider Crawl Rows Error] {e}")
            import traceback
            traceback.print_exc()
            self.mode = "idle"
            self.speed = 2.2
            self.pick_random_wander()

    def _tick_alert(self):
        self.alert_pulse_phase = (self.alert_pulse_phase + 1) % 20
        self.color_glow = self.RED_PULSE if self.alert_pulse_phase < 10 else self.CYAN_GLOW

        banner_w = self.root.winfo_width()
        banner_x = banner_w / 2.0 + math.sin(self.alert_pulse_phase * 0.4) * 90.0
        banner_y = 40.0 + math.cos(self.alert_pulse_phase * 0.3) * 16.0

        dx = banner_x - self.x
        dy = banner_y - self.y
        self._steer_towards(dx, dy)
        self.x += math.cos(self.angle) * self.speed
        self.y += math.sin(self.angle) * self.speed
        self.update_feet(moving=True)

    def _tick_pounce(self):
        self.fx_ticks -= 1
        self.x += math.cos(self.angle) * 3.2
        self.y += math.sin(self.angle) * 3.2
        self.update_feet(moving=True)
        if self.fx_ticks <= 0:
            self.mode = "idle"
            self.speed = 2.2
            self.pick_random_wander()

    def _tick_celebrate(self):
        self.fx_ticks -= 1
        self.angle += 0.55
        self.update_feet(moving=False)
        for sp in self.fx_data.get("sparkles", []):
            sp["x"] += sp["dx"]
            sp["y"] += sp["dy"]
        if self.fx_ticks <= 0:
            self.mode = "idle"
            self.speed = 2.2
            self.pick_random_wander()

    def _steer_towards(self, dx, dy):
        desired = math.atan2(dy, dx)
        diff = (desired - self.angle + math.pi) % (2 * math.pi) - math.pi
        self.angle += diff * 0.32

    def pick_random_wander(self):
        """Picks a random target position covering the application window."""
        try:
            w = max(200, self.root.winfo_width() - 80)
            h = max(200, self.root.winfo_height() - 80)
        except Exception:
            w, h = 900, 600
        self.target_x = random.uniform(80.0, w)
        self.target_y = random.uniform(80.0, h)

    # ─────────────────────────────────────────────────────────────────
    # Procedural Spider Drawing (Persistent Canvas Items with coords())
    # ─────────────────────────────────────────────────────────────────

    def draw_spider(self):
        """Updates positions of pre-created canvas items using coords(). Fast and allocation-free."""
        if not self.win or not self.canvas:
            return

        bx, by = self.x, self.y
        cos_a = math.cos(self.angle - math.pi / 2)
        sin_a = math.sin(self.angle - math.pi / 2)
        glow = self.color_glow

        joint_offsets = [
            (-8.0, -7.0), (-10.0, -1.0), (-10.0, 5.0), (-8.0, 11.0),
            ( 8.0, -7.0), ( 10.0, -1.0), ( 10.0, 5.0), ( 8.0, 11.0),
        ]

        # Update stroke fill only if changed
        if glow != self._last_drawn_glow:
            self._last_drawn_glow = glow
            for leg in self.leg_items:
                self.canvas.itemconfigure(leg["u_glow"], fill=glow)
                self.canvas.itemconfigure(leg["l_glow"], fill=glow)
            self.canvas.itemconfigure(self.item_abdomen, fill=glow)
            self.canvas.itemconfigure(self.item_thorax, fill=glow)
            self.canvas.itemconfigure(self.item_head, fill=glow)
            eye_col = "#ffffff" if glow != self.RED_PULSE else "#ffcccc"
            for eye in self.item_eyes:
                self.canvas.itemconfigure(eye, fill=eye_col)

        # 1. 8 Jointed legs with dual strokes via coords()
        for i in range(8):
            jox, joy = joint_offsets[i]
            jx = bx + (jox * cos_a - joy * sin_a)
            jy = by + (jox * sin_a + joy * cos_a)
            fx, fy = self.feet_pos[i]

            mx = (jx + fx) / 2.0
            my = (jy + fy) / 2.0
            dx = fx - jx
            dy = fy - jy
            dist = max(1.0, math.hypot(dx, dy))
            sign = -1.0 if i < 4 else 1.0
            nx = -dy / dist * sign
            ny =  dx / dist * sign
            arch = 9.0
            kx = mx + nx * arch
            ky = my + ny * arch

            leg = self.leg_items[i]
            self.canvas.coords(leg["u_dark"], jx, jy, kx, ky)
            self.canvas.coords(leg["l_dark"], kx, ky, fx, fy)
            self.canvas.coords(leg["u_glow"], jx, jy, kx, ky)
            self.canvas.coords(leg["l_glow"], kx, ky, fx, fy)

        # 2. Abdomen
        ab_x = bx + (0.0 * cos_a - 4.0 * sin_a)
        ab_y = by + (0.0 * sin_a + 4.0 * cos_a)
        self.canvas.coords(self.item_abdomen, ab_x - 8, ab_y - 11, ab_x + 8, ab_y + 11)

        # 3. Cephalothorax
        self.canvas.coords(self.item_thorax, bx - 6, by - 6, bx + 6, by + 6)

        # 4. Head
        hx = bx + (0.0 * cos_a - (-8.0) * sin_a)
        hy = by + (0.0 * sin_a + (-8.0) * cos_a)
        self.canvas.coords(self.item_head, hx - 4, hy - 4, hx + 4, hy + 4)

        # 5. Dual Eyes
        for idx, eye_x in enumerate((-1.8, 1.8)):
            ex = hx + (eye_x * cos_a - (-2.0) * sin_a)
            ey = hy + (eye_x * sin_a + (-2.0) * cos_a)
            self.canvas.coords(self.item_eyes[idx], ex - 1.0, ey - 1.0, ex + 1.0, ey + 1.0)

    def draw_fx(self):
        """Updates dynamic visual effects using persistent canvas shapes."""
        if not self.win or not self.canvas:
            return

        if self.mode == "pounce":
            self.fx_data["radius"] += 2.8
            r = self.fx_data["radius"]
            ox = self.fx_data["origin_x"]
            oy = self.fx_data["origin_y"]
            self.canvas.coords(self.item_shockwave, ox - r, oy - r, ox + r, oy + r)
            self.canvas.itemconfigure(self.item_shockwave, state="normal")
        else:
            self.canvas.itemconfigure(self.item_shockwave, state="hidden")

        if self.mode == "celebrate":
            sparkles = self.fx_data.get("sparkles", [])
            for idx in range(min(14, len(sparkles))):
                sp = sparkles[idx]
                sx, sy = sp["x"], sp["y"]
                item = self.item_sparkles[idx]
                self.canvas.coords(item, sx - 2.5, sy - 2.5, sx + 2.5, sy + 2.5)
                self.canvas.itemconfigure(item, state="normal")
            for idx in range(len(sparkles), 14):
                self.canvas.itemconfigure(self.item_sparkles[idx], state="hidden")
        else:
            for item in self.item_sparkles:
                self.canvas.itemconfigure(item, state="hidden")
