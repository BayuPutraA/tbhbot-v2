"""
Core Automation Engine for Task Bar Hero.
Orchestrates the scheduler, state machine execution loop, F8 emergency stop listener,
mouse safety idle monitor, inventory scanning, and synthesis workflows.
"""
import os
import time
import json
import threading
import ctypes
from typing import Optional, Callable, Dict, Any, List, Tuple
from datetime import datetime

import cv2
import numpy as np
from pynput import keyboard

from vision import VisionEngine
from .actions import InputActions
from .scheduler import CycleScheduler
from .synthesis import SynthesisManager
from .telegram_watchdog import TelegramWatchdog


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_system_idle_seconds() -> float:
    """Returns elapsed seconds since last physical user input (mouse move/click or key press) using Win32 API.
    Zero-hook, zero-overhead kernel check that does not intercept or lag mouse movement."""
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    except Exception:
        pass
    return 999.0


class BotEngine:
    def __init__(
        self,
        config_path: str = "config.json",
        assets_dir: str = "assets",
        on_status: Optional[Callable[[str], None]] = None,
        on_log: Optional[Callable[[str, str], None]] = None,
        on_countdown: Optional[Callable[[str, int], None]] = None,
        on_buckets_update: Optional[Callable[[Dict[str, Dict[str, int]]], None]] = None,
        on_items_detected: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ):
        self.config_path = config_path
        self.assets_dir = assets_dir
        self.on_status = on_status
        self.on_log = on_log
        self.on_countdown = on_countdown
        self.on_buckets_update = on_buckets_update
        self.on_items_detected = on_items_detected

        # Configuration and Vision
        self.config = self.load_config()
        self.vision = VisionEngine(self.config, self.assets_dir)

        # Threading and control flags
        self.abort_requested = False
        self.cycle_running = False
        self.auto_loop_enabled = False

        # Timing
        self.interval_seconds = int(self.config.get("timer_interval_minutes", 120)) * 60
        self.seconds_remaining = self.interval_seconds

        # Mouse idle safety tracking
        self.last_user_mouse_move = time.time()
        self.bot_is_controlling_mouse = False

        # Scroll mode
        self.scroll_mode = self.config.get("scroll_mode", "Win32 Wheel Only")

        # Inventory grid fullness direct tracking
        self.is_inventory_grid_full = False

        # Unstopped loop tracking (for Auto-Fill Synthesis after 5 unstopped loops)
        self.unstopped_loops = 0

        # Live item buckets data structure
        self.live_buckets = self._init_empty_bucket_counts()

        # Modular Sub-controllers
        self.actions = InputActions(self)
        self.scheduler = CycleScheduler(self)
        self.synthesis = SynthesisManager(self)

        # Delegated action methods for backwards compatibility
        self.click_point = self.actions.click_point
        self.ctrl_right_click = self.actions.ctrl_right_click
        self.alt_right_click = self.actions.alt_right_click
        self.drag_and_drop = self.actions.drag_and_drop
        self.press_space = self.actions.press_space
        self.activate_game_hover = self.actions.activate_game_hover
        self.click_inventory_sort_button = self.actions.click_inventory_sort_button
        self.activate_scroll_with_double_click = self.actions.activate_scroll_with_double_click
        self.wheel_scroll = self.actions.wheel_scroll
        self.scroll_to_top = self.actions.scroll_to_top
        self.scroll_to_bottom = self.actions.scroll_to_bottom
        self.scroll_inventory_down = self.actions.scroll_inventory_down

        # Delegated scheduler methods
        self.toggle_auto_loop = self.scheduler.toggle_auto_loop
        self.set_timer_interval = self.scheduler.set_timer_interval
        self.reset_timer = self.scheduler.reset_timer

        # Delegated synthesis methods
        self.ensure_cube_and_inventory_open = self.synthesis.ensure_cube_and_inventory_open
        self.find_highest_priority_recipe = self.synthesis.find_highest_priority_recipe
        self.select_cube_tier = self.synthesis.select_cube_tier
        self.click_synth_button = self.synthesis.click_synth_button
        self.click_synth_return_button = self.synthesis.click_synth_return_button
        self.click_auto_fill_button = self.synthesis.click_auto_fill_button
        self.execute_synthesis_flow = self.synthesis.execute_synthesis_flow
        self.execute_autofill_synthesis_flow = self.synthesis.execute_autofill_synthesis_flow
        self.test_synthesis_loading = self.synthesis.test_synthesis_loading
        self.test_stash_transfer = self.synthesis.test_stash_transfer
        self.test_cube_tier_selection = self.synthesis.test_cube_tier_selection

        # Telegram Watchdog & Remote Service
        self.telegram = TelegramWatchdog(self, self.config)
        if self.telegram.enabled and self.telegram.client.is_configured:
            self.telegram.start()

        # Background listener threads
        self._start_global_listeners()

    def start_scheduler(self):
        """Starts the scheduler thread after GUI main loop is active."""
        self.scheduler.start_scheduler_thread()

    def _init_empty_bucket_counts(self) -> Dict[str, Dict[str, int]]:
        return {
            "65": {"Common": 0, "Uncommon": 0, "Rare": 0, "Legendary": 0},
            "80_90": {"Common": 0, "Uncommon": 0, "Rare": 0, "Legendary": 0},
            "tier_65_80": {"Common": 0, "Uncommon": 0, "Rare": 0, "Legendary": 0},
            "tier_80_90": {"Common": 0, "Uncommon": 0, "Rare": 0, "Legendary": 0}
        }

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            example_cfg = os.path.join(os.path.dirname(self.config_path), "config.example.json")
            if os.path.exists(example_cfg):
                import shutil
                try:
                    shutil.copyfile(example_cfg, self.config_path)
                except Exception:
                    pass
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.log(f"Config load error: {e}", "warning")
        return {}

    def reload_config(self):
        self.config = self.load_config()
        self.vision.update_config(self.config)
        if hasattr(self, "telegram"):
            self.telegram.reload_config(self.config)
        self.interval_seconds = int(self.config.get("timer_interval_minutes", 120)) * 60
        self.scroll_mode = self.config.get("scroll_mode", "Win32 Wheel Only")

    def log(self, message: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{ts}] {message}"
        if self.on_log:
            self.on_log(formatted, level)
        else:
            try:
                print(formatted)
            except UnicodeEncodeError:
                print(formatted.encode("ascii", "replace").decode("ascii"))

    def set_status(self, status: str):
        if self.on_status:
            self.on_status(status)
        if hasattr(self, "telegram"):
            self.telegram.record_progress(status)

    # ---------------------------------------------------------
    # Global Listeners (F8 Emergency Stop)
    # ---------------------------------------------------------
    def _start_global_listeners(self):
        # Keyboard listener only for F8 Emergency Stop (event-driven, no polling overhead)
        def on_press(key):
            try:
                if key == keyboard.Key.f8:
                    self.trigger_emergency_stop()
            except Exception:
                pass

        self.key_listener = keyboard.Listener(on_press=on_press)
        self.key_listener.daemon = True
        self.key_listener.start()

    def reset_abort_state(self):
        """Clears abort flag and mouse control state before starting any test or cycle."""
        self.abort_requested = False
        self.bot_is_controlling_mouse = False

    def execute_unstick_routine(self) -> bool:
        """
        Unstick rescue procedure:
        1. Presses Escape twice to dismiss any open modal / dropdown / popup / menu.
        2. If stash_tab_material is calibrated, clicks it to restore standard stash view.
        3. Double-clicks inventory slot (0,0) to regain inventory mouse focus.
        4. Clears vision cache and resets abort flags.
        """
        self.log("[Unstick] Executing emergency unstick procedure...", "warning")
        self.set_status("Unsticking Game State...")

        try:
            from pynput.keyboard import Controller as KeyController, Key
            kb = KeyController()
            kb.press(Key.esc)
            time.sleep(0.08)
            kb.release(Key.esc)
            time.sleep(0.2)
            kb.press(Key.esc)
            time.sleep(0.08)
            kb.release(Key.esc)
            time.sleep(0.3)
        except Exception as e:
            self.log(f"[Unstick] Key press error: {e}", "warning")

        # Return to Stash Material if calibrated
        sm = self.config.get("button_coords", {}).get("stash_tab_material")
        if sm and "x" in sm and "y" in sm:
            self.click_point(sm["x"], sm["y"], delay_after=0.25)
            time.sleep(0.25)

        # Double-click inventory slot (0,0)
        inv_roi = self.vision.get_inventory_roi()
        self.activate_scroll_with_double_click(inv_roi)
        time.sleep(0.2)

        # Clear vision caches
        self.vision.clear_cache()
        self.log("[Unstick] Unstick procedure complete. Game state reset.", "success")
        return True

    def trigger_emergency_stop(self):
        """Immediately abort active automation loop."""
        self.abort_requested = True
        self.cycle_running = False
        self.bot_is_controlling_mouse = False
        self.unstopped_loops = 0
        self.log("EMERGENCY STOP (F8) TRIGGERED! Cycle aborted (unstopped loops reset to 0).", "error")
        self.set_status("Emergency Stopped (F8)")

    # ---------------------------------------------------------
    # Pre-Cycle Safety Check
    # ---------------------------------------------------------
    def _perform_pre_cycle_safety_check(self) -> bool:
        """Waits until user mouse/keyboard has been idle for configured seconds using zero-hook Win32 kernel API."""
        safety_cfg = self.config.get("mouse_safety", {})
        idle_threshold = float(safety_cfg.get("idle_threshold_seconds", 5.0))

        while not self.abort_requested:
            idle_time = get_system_idle_seconds()
            if idle_time >= idle_threshold:
                return True

            remaining_wait = int(max(1, idle_threshold - idle_time))
            self.set_status(f"Waiting for mouse idle ({remaining_wait}s)")
            self.log(f"User mouse movement detected. Waiting for {remaining_wait}s stillness...", "warning")
            time.sleep(1)

        return False

    # ---------------------------------------------------------
    # Master Automation Loop (State Machine)
    # ---------------------------------------------------------
    def start_cycle_async(self):
        """Triggers cycle in a background daemon thread."""
        if self.cycle_running:
            self.log("Cycle already in progress. Ignoring duplicate trigger.", "warning")
            return

        thread = threading.Thread(target=self._run_cycle, daemon=True)
        thread.start()

    def _run_cycle(self):
        self.cycle_running = True
        self.abort_requested = False
        self.reload_config()
        self.vision.clear_cache()

        self.log("=== STARTING AUTOMATION CYCLE ===", "info")

        try:
            # Pre-Cycle Safety Check
            if not self._perform_pre_cycle_safety_check():
                self.log("Cycle cancelled during safety check.", "warning")
                return

            loop_pass = 1
            # Material stash is required on the very first loop pass or after opening a chest
            should_stash_mats = True

            while not self.abort_requested:
                self.reload_config()
                self.log(f"--- Cycle Pass #{loop_pass} ---", "info")
                inv_roi = self.vision.get_inventory_roi()
                chest_roi = self.config.get("rois", {}).get("chest_region")

                # Step 1: 2x left-click on slot (0,0) (initial window & inventory focus)
                self.set_status("Focusing Inventory (2x click)")
                self.log("Step 1: 2x left-click on slot (0,0) for initial inventory focus...", "info")
                self.activate_scroll_with_double_click(inv_roi)
                time.sleep(0.3)

                if self.abort_requested:
                    break

                # Step 2: CHECK CHEST (Visual scan only, NO clicking!)
                self.set_status("Checking Chest Area")
                self.log("Step 2: Visually inspecting chest area (no clicking)...", "info")
                chest_state = self.vision.detect_chest_state(chest_roi)
                inv_full = bool(
                    chest_state.get("inv_full_found") or
                    self.vision.is_inventory_full(chest_roi) or
                    getattr(self, "is_inventory_grid_full", False)
                )

                if inv_full:
                    # =========================================================
                    # CONDITION A: Inventory is FULL
                    # =========================================================
                    self.log(f"Condition: Inventory is FULL ({chest_state.get('inv_full_type', 'inven_full')}, conf: {chest_state.get('inv_full_conf', 1.0):.2f})", "warning")
                    self.set_status("Inventory Full - Preparing Scan")

                    # 1. Click sort button
                    self.log("Full Inv Step 1: Clicking Inventory Sort button...", "info")
                    self.click_inventory_sort_button()
                    time.sleep(0.35)

                    if self.abort_requested:
                        break

                    # 2. 2x left-click on slot (0,0)
                    self.log("Full Inv Step 2: 2x left-click on slot (0,0)...", "info")
                    self.activate_scroll_with_double_click(inv_roi)
                    time.sleep(0.3)

                    # Material Stash (Only at first loop if enabled)
                    if should_stash_mats and self.config.get("auto_stash_materials", True) and self.vision.has_material_library():
                        self.log("Material Scan & Stash triggered (first loop)...", "info")
                        self.scan_and_stash_materials(inv_roi)
                        should_stash_mats = False
                        if self.abort_requested:
                            break
                    else:
                        self.log("Skipping Material Stash (already done and no new chests were opened).", "info")

                    # Low-Level Stashing (frees up slots if full)
                    if self.config.get("low_level_stashing_enabled", False):
                        self.log("Full Inv Step 2b: Checking for Lv. 50 gear to stash...", "info")
                        stashed_l50 = self.execute_low_level_stashing(inv_roi)
                        if stashed_l50.get("low_tier", 0) + stashed_l50.get("high_tier", 0) > 0:
                            self.log("Freed slots via Lv. 50 stashing, sorting inventory...", "info")
                            self.click_inventory_sort_button()
                            time.sleep(0.35)
                            self.activate_scroll_with_double_click(inv_roi)
                            time.sleep(0.3)

                    # 3. Always start on top of inventory before scanning
                    self.log("Full Inv Step 3: Scrolling up to top row...", "info")
                    self.scroll_to_top(activate_first=False)
                    time.sleep(0.4)

                    if self.abort_requested:
                        break

                    # 4. Scan inventory & count
                    self.set_status("Scanning Gear")
                    counts = self.scan_inventory_counts(inv_roi)

                    # 5. Check if any recipe >= 9 (prioritizing 80~90 over 65)
                    target_recipe = self.find_highest_priority_recipe(counts)

                    if not target_recipe:
                        # 4a. If no gear meets requirements, check if auto-fill synth can purge miss-scans
                        af_enabled = self.config.get("autofill_synth_enabled", True)
                        target_loops = int(self.config.get("autofill_synth_every_loops", 5))
                        if af_enabled and (self.unstopped_loops + 1) >= target_loops:
                            self.log(f"[Auto-Fill Synth] Full inventory with no recipe on unstopped loop #{self.unstopped_loops + 1}. Running Auto-Fill Synthesis to purge miss-scanned gears...", "info")
                            af_ok = self.execute_autofill_synthesis_flow()
                            self.unstopped_loops = 0
                            self.click_inventory_sort_button()
                            time.sleep(0.35)
                            self.activate_scroll_with_double_click(inv_roi)
                            time.sleep(0.3)
                            if af_ok:
                                loop_pass += 1
                                continue

                        self.log("Full Inv Step 4a: Inventory is FULL and no 9-item set meets requirements. STOPPING CYCLE.", "warning")
                        self.set_status("Paused - Inventory Full")
                        break
                    else:
                        # 4b. If gear >= 9, run synthesize flow
                        target_bracket, target_rarity = target_recipe
                        tier_label = "Lv.80~90" if target_bracket == "80_90" else "Lv.65~80"
                        self.log(f"Full Inv Step 4b: Found >= 9 gears ready ({tier_label} {target_rarity})! Running synthesis flow...", "info")
                        success = self.execute_synthesis_flow(target_bracket, target_rarity, inv_roi, is_full_inv=True)
                        if success:
                            self.log("Synthesis complete (freed 8 slots)! Looping back to start of cycle...", "info")
                            loop_pass += 1
                            time.sleep(0.5)
                            continue
                        else:
                            self.log("Synthesis aborted or incomplete.", "warning")
                            break

                else:
                    # =========================================================
                    # CONDITION B: Inventory is NOT FULL
                    # =========================================================
                    self.log("Condition: Inventory is NOT full. Opening chests...", "info")
                    self.set_status("Opening Chests (Space)")

                    # 1. Stay focused on inventory, press space to open all chests
                    all_chests_cleared = self.open_all_chests_inventory_focus(chest_roi)
                    became_full = not all_chests_cleared
                    chests_opened = getattr(self, "last_chests_opened", False)
                    if chests_opened:
                        should_stash_mats = True

                    if self.abort_requested:
                        break

                    # 2. Click sort button
                    self.log("Not Full Step 2: Clicking Inventory Sort button...", "info")
                    self.click_inventory_sort_button()
                    time.sleep(0.35)

                    if self.abort_requested:
                        break

                    # 3. 2x left-click on slot (0,0)
                    self.log("Not Full Step 3: 2x left-click on slot (0,0)...", "info")
                    self.activate_scroll_with_double_click(inv_roi)
                    time.sleep(0.3)

                    # Flow 1: Material Scan & Stash (DO MATERIAL FIRST after opening chests)
                    if should_stash_mats and self.config.get("auto_stash_materials", True) and self.vision.has_material_library():
                        self.log("Post-Chest Step 1: Starting Material Scan & Stash (Material First)...", "info")
                        self.scan_and_stash_materials(inv_roi)
                        should_stash_mats = False
                        if self.abort_requested:
                            break
                    else:
                        self.log("Skipping Material Stash (already done and no new chests were opened).", "info")

                    if self.abort_requested:
                        break

                    # Flow 2: Cube Corrosion Flow (DO CORROSION SECOND, ONLY AFTER CHESTS, STARTING ON LOOP 3+)
                    min_corr_loop = int(self.config.get("corrosion_start_loop", 3))
                    if self.config.get("auto_corrosion_enabled", True) and self.vision.has_corrosion_library():
                        if loop_pass < min_corr_loop:
                            self.log(f"[Corrosion] Post-Chest Step 2: Skipping Cube Corrosion on loop pass #{loop_pass} (configured to run after 2 complete loops, starting on pass #{min_corr_loop}+).", "info")
                        elif chests_opened:
                            self.log(f"[Corrosion] Post-Chest Step 2: Starting Cube Corrosion flow on pass #{loop_pass} (after material stash)...", "info")
                            loaded_corr = self.synthesis.execute_corrosion_flow(inv_roi)
                            self.log(f"[Corrosion] Post-Chest Corrosion flow complete. Selected and executed {loaded_corr}/9 material(s).", "info")

                    if self.abort_requested:
                        break

                    # Flow 3: Low Level Stashing Flow (Lv. 50) - Full top-to-bottom scan & stashing
                    if self.config.get("low_level_stashing_enabled", False):
                        self.log("[LowLevel] Post-Chest Step 3: Starting Low-Level (Lv. 50) full inventory scan & stashing...", "info")
                        self.execute_low_level_stashing(inv_roi)

                    self.last_chests_opened = False

                    # 4. Always start on top of inventory before scanning
                    self.log("Not Full Step 4: Scrolling up to top row...", "info")
                    self.scroll_to_top(activate_first=False)
                    time.sleep(0.4)

                    if self.abort_requested:
                        break

                    # 5. Scan inventory & count
                    self.set_status("Scanning Gear")
                    counts = self.scan_inventory_counts(inv_roi)

                    # 6. Check if any recipe >= 9 (prioritizing 80~90 over 65)
                    target_recipe = self.find_highest_priority_recipe(counts)

                    if not target_recipe:
                        af_enabled = self.config.get("autofill_synth_enabled", True)
                        target_loops = int(self.config.get("autofill_synth_every_loops", 5))

                        if getattr(self, "is_inventory_grid_full", False):
                            if af_enabled and (self.unstopped_loops + 1) >= target_loops:
                                self.log(f"[Auto-Fill Synth] Verified full grid with no recipe on unstopped loop #{self.unstopped_loops + 1}. Running Auto-Fill Synthesis...", "info")
                                af_ok = self.execute_autofill_synthesis_flow()
                                self.unstopped_loops = 0
                                self.click_inventory_sort_button()
                                time.sleep(0.35)
                                if af_ok:
                                    loop_pass += 1
                                    continue
                            self.log("Not Full Step 5a: Inventory is verified FULL (via grid check) and no 9-item recipe is ready. Stopping cycle.", "warning")
                            self.set_status("Paused - Inventory Full")
                        else:
                            # 5a. If no gear meets requirements, STOP and WAIT FOR COUNTDOWN TIMER
                            self.unstopped_loops += 1
                            self.log(f"Cycle completed successfully without interruption (Unstopped Loops: {self.unstopped_loops}/{target_loops}).", "info")

                            if af_enabled and self.unstopped_loops >= target_loops:
                                self.log(f"[Auto-Fill Synth] Reached {self.unstopped_loops} unstopped loops! Running Auto-Fill Synthesis (Lv. 80~90) to purge miss-scanned gears...", "info")
                                self.execute_autofill_synthesis_flow()
                                self.unstopped_loops = 0
                                self.click_inventory_sort_button()
                                time.sleep(0.35)

                            self.log("Not Full Step 5a: No 9-item set meets requirements. Cycle complete — resetting countdown timer.", "info")
                            self.reset_timer()
                            self.set_status("Idle - Waiting for Timer" if self.auto_loop_enabled else "Paused")
                        break
                    else:
                        # 5b. If gear >= 9, run synthesize flow
                        target_bracket, target_rarity = target_recipe
                        tier_label = "Lv.80~90" if target_bracket == "80_90" else "Lv.65~80"
                        self.log(f"Not Full Step 5b: Found >= 9 gears ready ({tier_label} {target_rarity})! Running synthesis flow...", "info")
                        is_full = bool(became_full or getattr(self, "is_inventory_grid_full", False))
                        success = self.execute_synthesis_flow(target_bracket, target_rarity, inv_roi, is_full_inv=is_full)
                        if success:
                            self.log("Synthesis complete (freed 8 slots)! Looping back to start of cycle...", "info")
                            loop_pass += 1
                            time.sleep(0.5)
                            continue
                        else:
                            self.log("Synthesis aborted or incomplete.", "warning")
                            break

        except Exception as e:
            self.log(f"Error during cycle execution: {e}", "error")
        finally:
            self.cycle_running = False
            if hasattr(self, "telegram") and not self.abort_requested:
                self.telegram.record_cycle_completed()
            if self.abort_requested:
                self.unstopped_loops = 0
                self.set_status("Emergency Stopped (F8)")

    # ---------------------------------------------------------
    # Open All Chests (Maintaining Inventory Focus)
    # ---------------------------------------------------------
    def open_all_chests_inventory_focus(self, chest_roi: Optional[Dict[str, int]] = None) -> bool:
        """
        Opens chests using Space key while maintaining focus on inventory (NEVER clicks chest area).
        Checks chest ROI visually:
        - Stops if inventory is full (inv_full_blue / inv_full_brown / inv_full_text / inv_full).
        - Stops when all chests are opened: empty_floor confirmed OR no blue/brown chest detected.
        Presses Space with 0.25s delay.
        Returns True if all chests cleared, False if stopped due to inventory full or abort.
        """
        roi = chest_roi or self.config.get("rois", {}).get("chest_region")

        # Initial visual check before pressing Space
        state = self.vision.detect_chest_state(roi)
        if state.get("inv_full_found") or self.vision.is_inventory_full(roi):
            self.log(f"Chest check at start: Inventory is full ({state.get('inv_full_type', 'inven_full')}).", "warning")
            self.last_chests_opened = False
            return False

        # If a chest is detected (e.g. Blue/Brown Chest), proceed to press Space.
        # Only exit if NO chest is detected and floor is empty.
        if not state.get("chest_found"):
            time.sleep(0.2)
            check2 = self.vision.detect_chest_state(roi)
            if not check2.get("chest_found"):
                self.log(f"Chest check at start: Floor verified empty / no chests detected ({check2.get('status_str')}). No chests to open.", "info")
                self.last_chests_opened = False
                return True

        presses = 0
        max_presses = 200
        all_cleared = False
        c_type = state.get("chest_type") or "chest"
        self.log(f"Opening chests ({state.get('status_str', 'Chest detected')}) — pressing Space (0.25s interval, maintaining inventory focus)...", "info")

        while presses < max_presses and not self.abort_requested:
            # Check if inventory became full
            if self.vision.is_inventory_full(roi):
                self.log(f"Inventory full warning detected after {presses} Space presses. Stopping chest opening.", "warning")
                self.last_chests_opened = (presses > 0)
                return False

            state = self.vision.detect_chest_state(roi)
            if state.get("inv_full_found"):
                self.log(f"Inventory full over chest ({state.get('inv_full_type')}) after {presses} Space presses. Stopping chest opening.", "warning")
                self.last_chests_opened = (presses > 0)
                return False

            # Check if all chests cleared (NO chest detected anymore)
            if not state.get("chest_found"):
                time.sleep(0.25)
                check2 = self.vision.detect_chest_state(roi)
                if not check2.get("chest_found"):
                    self.log(f"All chests cleared verified! (Status: {check2.get('status_str')}, Space presses: {presses})", "info")
                    all_cleared = True
                    break

            # Press Space with 0.25s delay
            self.press_space(delay_after=0.25)
            presses += 1
            if presses % 10 == 0:
                self.log(f"Unopened {c_type} present: pressed Space {presses} times...", "info")

        if presses >= max_presses:
            self.log("Reached safety limit of 200 consecutive Space presses.", "warning")

        self.last_chests_opened = (presses > 0)
        return all_cleared

    def open_all_chests(self) -> bool:
        """Opens all chests while maintaining inventory focus (no clicking on chest)."""
        chest_roi = self.config.get("rois", {}).get("chest_region")
        return self.open_all_chests_inventory_focus(chest_roi)

    def _sync_and_publish_counts(self, counts: Dict[Tuple[str, str], int]):
        """Syncs counts to live_buckets and publishes to GUI."""
        self.live_buckets["65"] = {r: counts.get(("65", r), 0) for r in ["Common", "Uncommon", "Rare", "Legendary"]}
        self.live_buckets["80_90"] = {r: counts.get(("80_90", r), 0) for r in ["Common", "Uncommon", "Rare", "Legendary"]}
        self.live_buckets["tier_65_80"] = dict(self.live_buckets["65"])
        self.live_buckets["tier_80_90"] = dict(self.live_buckets["80_90"])
        if self.on_buckets_update:
            self.on_buckets_update(self.live_buckets)

    def scan_inventory_counts(self, inv_roi: Dict[str, int]) -> Dict[Tuple[str, str], int]:
        """
        Scans all visible inventory items from top to bottom step-by-step.
        Assumes the inventory view has already been scrolled to the top row.
        Deduplicates items across scroll steps using global coordinates and updates GUI bucket labels.
        """
        counts: Dict[Tuple[str, str], int] = {
            (b, r): 0
            for b in ["65", "80_90"]
            for r in ["Common", "Uncommon", "Rare", "Legendary"]
        }

        grid_cfg = self.config.get("grid_settings", {})
        max_steps = int(grid_cfg.get("max_scroll_steps", 20))
        scroll_ticks = int(grid_cfg.get("scroll_ticks_per_step", 1))

        prev_roi_img = None
        cumulative_y = 0
        seen_items = []

        self.log(f"Scanning inventory items top to bottom (mode: {self.scroll_mode}, max {max_steps} steps)...", "info")

        for step in range(max_steps):
            if self.abort_requested:
                break

            curr_roi_img = self.vision.capture_screen(inv_roi)

            # Measure scroll shift dy from previous view
            if prev_roi_img is not None:
                dy = self.vision.detect_vertical_scroll_shift(prev_roi_img, curr_roi_img)
                if dy > 0:
                    cumulative_y += dy
                else:
                    fallback_depth = max(10, int(grid_cfg.get("scroll_depth_px", 40)))
                    cumulative_y += fallback_depth

            # Detect all visible items in current view (reuse captured image to avoid duplicate screenshot)
            items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0, roi_img=curr_roi_img)

            # Spatial deduplication across cumulative scrolls
            newly_detected = []
            for itm in items:
                sw = itm.get("slot_w", itm.get("slot_box", (0, 0, 38, 38))[2])
                sh = itm.get("slot_h", itm.get("slot_box", (0, 0, 38, 38))[3])
                sx = itm.get("slot_x", itm.get("slot_box", (0, 0, 38, 38))[0])
                sy = itm.get("slot_y", itm.get("slot_box", (0, 0, 38, 38))[1])
                col = max(0, min(6, int(round((sx + sw / 2.0 - 20) / 41.2))))
                global_y = cumulative_y + (sy + sh / 2.0)

                is_dup = False
                for seen in seen_items:
                    if seen["col"] == col and abs(seen["global_y"] - global_y) < 22:
                        is_dup = True
                        break

                if not is_dup:
                    seen_items.append({
                        "col": col,
                        "global_y": global_y,
                        "ref_file": itm.get("ref_file"),
                        "gear_name": itm.get("gear_name"),
                        "level": itm.get("level"),
                        "rarity": itm["rarity"],
                        "bracket": itm["bracket"]
                    })
                    b = itm["bracket"]
                    r = itm["rarity"]
                    if (b, r) in counts:
                        counts[(b, r)] += 1
                    newly_detected.append(itm)

            # Update checklist and live bucket counters with latest counts
            if self.on_items_detected and newly_detected:
                self.on_items_detected(newly_detected)

            self._sync_and_publish_counts(counts)
            prev_roi_img = curr_roi_img.copy()

            if step < max_steps - 1 and not self.abort_requested:
                self.log(f"Slowly scrolling down (step {step + 1}/{max_steps})...", "info")
                moved, at_bottom, diff = self.scroll_inventory_down(scroll_ticks)
                time.sleep(0.4)
                if at_bottom:
                    self.log(f"Inventory bottom reached at step {step + 1} (diff: {diff:.2f}).", "info")
                    break

        # Direct Inventory Fullness Check (Solution 2):
        # Inspect whether the real last slot (col 5, row 3, directly left of the '+' DLC button) is occupied.
        # Since inventory was sorted before scanning, an occupied last slot means zero empty slots exist.
        if len(seen_items) >= 28:
            bottom_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
            col_w = inv_roi["width"] / 7.0
            row_h = inv_roi["height"] / 4.0
            has_last_slot_item = any(
                (col_w * 4.8) <= (itm["slot_x"] + itm["slot_w"] / 2.0) <= (col_w * 6.2) and
                (itm["slot_y"] + itm["slot_h"] / 2.0) >= (row_h * 2.8)
                for itm in bottom_items
            )
            self.is_inventory_grid_full = bool(has_last_slot_item)
            if self.is_inventory_grid_full:
                self.log("Direct Inventory Grid Check: Real last slot (col 5, row 3, left of DLC button) is OCCUPIED. Inventory is 100% FULL.", "warning")
            else:
                self.log("Direct Inventory Grid Check: Free slot(s) detected at bottom (col 5 is empty). Inventory is NOT full.", "info")
        else:
            self.is_inventory_grid_full = False

        self.log(f"Inventory scan complete. Deduplicated counts: {counts}", "info")
        return counts

    def scan_and_stash_materials(self, inv_roi: Optional[Dict[str, int]] = None) -> int:
        """
        Pass 1: Dedicated Material Scan and Stash.
        Scans inventory view step-by-step from top to bottom.
        For every detected material in SS_materials/, executes Ctrl+Right Click to move it to Stash.
        Protects any corrosion materials so they remain available for Cube Corrosion.
        Returns total number of materials stashed.
        """
        if not self.config.get("auto_stash_materials", True):
            return 0

        if not self.vision.has_material_library():
            return 0

        roi = inv_roi or self.vision.get_inventory_roi()
        self.set_status("Stashing Materials")
        self.log("Starting Material Scan & Stash pass (Ctrl+Right Click)...", "info")

        # Set of enabled corrosion filenames to prevent stashing them
        corrosion_filenames = set()
        if self.vision.has_corrosion_library():
            for c_itm in getattr(self.vision.corrosion_detector, "_corrosion_library", []):
                corrosion_filenames.add(c_itm.get("filename", "").lower())

        grid_cfg = self.config.get("grid_settings", {})
        max_steps = int(grid_cfg.get("max_scroll_steps", 20))
        scroll_ticks = int(grid_cfg.get("scroll_ticks_per_step", 1))

        # Reset inventory to top row before scanning
        self.log("Resetting inventory to top row for material pass...", "info")
        self.scroll_to_top(activate_first=False)
        time.sleep(0.35)

        total_stashed = 0

        for step in range(max_steps):
            if self.abort_requested:
                break

            # Scan visible inventory for materials
            raw_materials = self.vision.scan_visible_materials(roi)
            materials = [m for m in raw_materials if m.get("filename", "").lower() not in corrosion_filenames]

            while materials and not self.abort_requested:
                # Stash first detected material
                mat = materials[0]
                cx, cy = mat["click_x"], mat["click_y"]
                m_info = f"{mat['rarity']} {mat['name']}"
                self.log(f"Detected material ({m_info}) at ({cx}, {cy}). Moving to Stash via Ctrl+Right Click...", "info")

                self.ctrl_right_click(cx, cy, delay_after=0.22)
                total_stashed += 1
                time.sleep(0.18)

                # Re-scan to update remaining materials in current view
                raw_materials = self.vision.scan_visible_materials(roi)
                materials = [m for m in raw_materials if m.get("filename", "").lower() not in corrosion_filenames]

            if step < max_steps - 1 and not self.abort_requested:
                moved, at_bottom, diff = self.scroll_inventory_down(scroll_ticks)
                time.sleep(0.35)
                if at_bottom:
                    # Final check at the very bottom
                    raw_materials = self.vision.scan_visible_materials(roi)
                    materials = [m for m in raw_materials if m.get("filename", "").lower() not in corrosion_filenames]
                    while materials and not self.abort_requested:
                        mat = materials[0]
                        cx, cy = mat["click_x"], mat["click_y"]
                        m_info = f"{mat['rarity']} {mat['name']}"
                        self.log(f"Detected material at bottom ({m_info}) at ({cx}, {cy}). Moving to Stash...", "info")
                        self.ctrl_right_click(cx, cy, delay_after=0.22)
                        total_stashed += 1
                        time.sleep(0.18)
                        raw_materials = self.vision.scan_visible_materials(roi)
                        materials = [m for m in raw_materials if m.get("filename", "").lower() not in corrosion_filenames]
                    break

        if total_stashed > 0:
            self.log(f"Material Pass complete: Stashed {total_stashed} material(s) into Stash.", "info")
            # Sort inventory to pack items and close any gaps
            self.log("Sorting inventory after material stashing...", "info")
            self.click_inventory_sort_button()
            time.sleep(0.35)
            self.log("Regaining inventory focus: 2x left-click on slot (0,0)...", "info")
            self.activate_scroll_with_double_click(roi)
            time.sleep(0.3)
            self.scroll_to_top(activate_first=False)
            time.sleep(0.35)
        else:
            self.log("Material Pass complete: No materials detected to stash.", "info")
            self.scroll_to_top(activate_first=False)
            time.sleep(0.3)

        return total_stashed

    def test_material_stash(self) -> int:
        """
        Tests scanning and stashing visible materials in the current inventory view.
        """
        self.reset_abort_state()
        self.reload_config()
        self.vision.clear_cache()
        roi = self.vision.get_inventory_roi()

        if not self.vision.has_material_library():
            self.log("Cannot test material stash: No material templates found in SS_materials/!", "warning")
            return 0

        self.log("--- Starting Material Stash Test ---", "info")
        return self.scan_and_stash_materials(roi)

    def test_corrosion_flow(self) -> int:
        """
        Tests the complete Cube Corrosion flow:
        1. Switches Cube mode to Corrosion.
        2. Focuses inventory and resets to top.
        3. Scans and loads corrosion materials via Alt+Right Click.
        4. Switches Cube mode back to Synthesis.
        """
        self.reset_abort_state()
        self.reload_config()
        self.vision.clear_cache()
        roi = self.vision.get_inventory_roi()

        if not self.vision.has_corrosion_library():
            self.log("[Corrosion] Cannot test corrosion flow: No enabled corrosion templates in SS_corrosion/!", "warning")
            return 0

        self.log("--- Starting Test Corrosion Flow ---", "info")
        return self.synthesis.execute_corrosion_flow(roi)

    # ---------------------------------------------------------
    # Low Level (Lv. 50) Stashing & Synthesis Engine
    # ---------------------------------------------------------
    def execute_low_level_stashing(self, inv_roi: Optional[Dict[str, int]] = None) -> Dict[str, int]:
        """
        Executes Low Level (Lv. 50) Full-Scan Stashing Flow:
        1. Resets inventory to top row.
        2. Steps down row-by-row (scrolling step-by-step up to max_steps or bottom).
        3. At each view, detects visible Lv. 50 items:
           - Low-tier (Common, Uncommon, Rare): Stashes to Stash 1.
           - High-tier (Legendary, Immortal): Stashes to Stash 2.
           - Regains inventory scroll focus.
        4. When scan reaches bottom, resets inventory back to top row.
        5. If low-tier items were added to Stash 1:
           - Opens Stash 1.
           - Checks if any Lv. 50 rarity has >= 9 items; if so, synthesizes directly on Cube Lv. 50.
           - Returns to Stash Material and regains inventory focus.
        6. If any items were stashed, sorts inventory.
        Returns dict with counts of stashed items.
        """
        if not self.config.get("low_level_stashing_enabled", False):
            return {"low_tier": 0, "high_tier": 0}

        roi = inv_roi or self.vision.get_inventory_roi()
        self.set_status("Scanning Lv. 50 Gear (Top to Bottom)")
        self.log("[LowLevel] Starting full inventory scan for Lv. 50 gear (top to bottom)...", "info")

        btn_coords = self.config.get("button_coords", {})
        stash_1 = btn_coords.get("stash_tab_1")
        stash_2 = btn_coords.get("stash_tab_2")
        stash_mat = btn_coords.get("stash_tab_material")

        grid_cfg = self.config.get("grid_settings", {})
        max_steps = int(grid_cfg.get("max_scroll_steps", 20))
        scroll_ticks = int(grid_cfg.get("scroll_ticks_per_step", 1))

        # Reset inventory to top row before starting Lv. 50 scan
        self.log("[LowLevel] Resetting inventory to top row for scan...", "info")
        self.scroll_to_top(activate_first=False)
        time.sleep(0.35)

        stashed_counts = {"low_tier": 0, "high_tier": 0}

        for step in range(max_steps):
            if self.abort_requested:
                break

            # Scan visible inventory in current view
            detected = self.vision.scan_visible_lvl50_items(roi)

            while detected and not self.abort_requested:
                low_tier = [itm for itm in detected if itm.get("rarity") in ("Common", "Uncommon", "Rare")]
                high_tier = [itm for itm in detected if itm.get("rarity") in ("Legendary", "Immortal")]

                if not low_tier and not high_tier:
                    break

                # Transfer Low-Tier (Stash 1)
                if low_tier and stash_1 and "x" in stash_1 and "y" in stash_1:
                    self.click_point(stash_1["x"], stash_1["y"], delay_after=0.3)
                    time.sleep(0.25)
                    for itm in low_tier:
                        if self.abort_requested:
                            break
                        cx, cy = itm["click_x"], itm["click_y"]
                        self.log(f"[LowLevel] Stashing {itm['rarity']} {itm['name']} at ({cx}, {cy}) -> Stash 1...", "info")
                        self.ctrl_right_click(cx, cy, delay_after=0.22)
                        stashed_counts["low_tier"] += 1
                        time.sleep(0.18)

                    # Return to Stash Material
                    if stash_mat and "x" in stash_mat and "y" in stash_mat:
                        self.click_point(stash_mat["x"], stash_mat["y"], delay_after=0.25)
                        time.sleep(0.2)
                    self.activate_scroll_with_double_click(roi)
                    time.sleep(0.2)

                # Transfer High-Tier (Stash 2)
                if high_tier and stash_2 and "x" in stash_2 and "y" in stash_2:
                    self.click_point(stash_2["x"], stash_2["y"], delay_after=0.3)
                    time.sleep(0.25)
                    for itm in high_tier:
                        if self.abort_requested:
                            break
                        cx, cy = itm["click_x"], itm["click_y"]
                        self.log(f"[LowLevel] Stashing {itm['rarity']} {itm['name']} at ({cx}, {cy}) -> Stash 2...", "info")
                        self.ctrl_right_click(cx, cy, delay_after=0.22)
                        stashed_counts["high_tier"] += 1
                        time.sleep(0.18)

                    # Return to Stash Material
                    if stash_mat and "x" in stash_mat and "y" in stash_mat:
                        self.click_point(stash_mat["x"], stash_mat["y"], delay_after=0.25)
                        time.sleep(0.2)
                    self.activate_scroll_with_double_click(roi)
                    time.sleep(0.2)

                # Re-scan current view to check if more Lv. 50 items remain
                detected = self.vision.scan_visible_lvl50_items(roi)

            # Scroll down to next view
            if step < max_steps - 1 and not self.abort_requested:
                moved, at_bottom, diff = self.scroll_inventory_down(scroll_ticks)
                time.sleep(0.35)
                if at_bottom:
                    self.log(f"[LowLevel] Inventory bottom reached at step {step + 1}.", "info")
                    break

        # Reset inventory back to top row
        self.log("[LowLevel] Resetting inventory back to top row...", "info")
        self.scroll_to_top(activate_first=False)
        time.sleep(0.35)

        total_stashed = stashed_counts["low_tier"] + stashed_counts["high_tier"]
        if hasattr(self, "telegram") and total_stashed > 0:
            self.telegram.record_stashed(total_stashed)

        # After scan, if any low-tier items were added to Stash 1, check synthesis readiness!
        if stashed_counts["low_tier"] > 0 and not self.abort_requested:
            if stash_1 and "x" in stash_1 and "y" in stash_1:
                self.click_point(stash_1["x"], stash_1["y"], delay_after=0.3)
                time.sleep(0.3)
                self.log("[LowLevel] Scanning Stash 1 to check if any Lv. 50 rarity has reached 9 items...", "info")
                self.check_and_synthesize_stash_lvl50()
                if stash_mat and "x" in stash_mat and "y" in stash_mat:
                    self.click_point(stash_mat["x"], stash_mat["y"], delay_after=0.25)
                    time.sleep(0.2)
                self.activate_scroll_with_double_click(roi)
                time.sleep(0.2)

        total_stashed = stashed_counts["low_tier"] + stashed_counts["high_tier"]
        if total_stashed > 0:
            self.log(f"[LowLevel] Full scan complete: {total_stashed} Lv. 50 item(s) stashed ({stashed_counts['low_tier']} to Stash 1, {stashed_counts['high_tier']} to Stash 2). Sorting...", "success")
            self.click_inventory_sort_button()
            time.sleep(0.3)
            self.activate_scroll_with_double_click(roi)
            time.sleep(0.3)
        else:
            self.log("[LowLevel] Full scan complete: No Lv. 50 items detected across full inventory.", "info")

        return stashed_counts

    def check_and_synthesize_stash_lvl50(self) -> bool:
        """
        Scans Stash 1 for Lv. 50 items. If any rarity reaches 9 items,
        executes the Stash Lv. 50 Synthesis flow.
        """
        stash_roi = self.config.get("rois", {}).get("stash_grid")
        stash_res = self.vision.scan_stash_for_lvl50(stash_roi)
        c_cnt = len(stash_res["by_rarity"]["Common"])
        u_cnt = len(stash_res["by_rarity"]["Uncommon"])
        r_cnt = len(stash_res["by_rarity"]["Rare"])
        self.log(f"[LowLevel] Stash 1 items: Common={c_cnt}, Uncommon={u_cnt}, Rare={r_cnt}", "info")

        if stash_res.get("is_ready") and stash_res.get("ready_rarity"):
            ready_r = stash_res["ready_rarity"]
            ready_items = stash_res["by_rarity"][ready_r]
            self.log(f"[LowLevel] Stash 1 has {len(ready_items)} {ready_r} Lv.50 items (>= 9)! Executing Cube Synthesis...", "info")
            ok = self.synthesis.execute_stash_lvl50_synthesis(ready_r, ready_items)
            if ok and hasattr(self, "telegram"):
                self.telegram.notify_synthesis(ready_r, len(ready_items[:9]), tier="50")
            return ok

        return False

    def test_low_level_stash_transfer(self) -> Dict[str, int]:
        """Manual test trigger for low-level stashing."""
        self.reset_abort_state()
        self.reload_config()
        self.vision.clear_cache()
        roi = self.vision.get_inventory_roi()
        self.log("--- Starting Manual Test: Low Level Stashing ---", "info")
        return self.execute_low_level_stashing(roi)

    def test_stash_lvl50_synthesis(self) -> bool:
        """Manual test trigger for scanning Stash 1 and synthesizing 9 Lv. 50 items."""
        self.reset_abort_state()
        self.reload_config()
        self.vision.clear_cache()
        self.log("--- Starting Manual Test: Stash Lv. 50 Synthesis ---", "info")
        return self.check_and_synthesize_stash_lvl50()

    def scan_full_inventory_items(self, inv_roi: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
        """
        Non-destructive full inventory scan from top to bottom.
        1. Activates scroll focus on inventory slot (0,0)
        2. Scrolls to top
        3. Scans all visible items page-by-page down to bottom
        4. Deduplicates items using column and cumulative Y offset
        5. Restores inventory scroll position back to top row
        Returns list of all deduplicated gear items with level, rarity, gear_name, etc.
        """
        roi = inv_roi or self.vision.get_inventory_roi()
        if not self.cycle_running:
            self.reset_abort_state()

        self.activate_scroll_with_double_click(roi)
        time.sleep(0.25)
        self.scroll_to_top(activate_first=False)
        time.sleep(0.35)

        grid_cfg = self.config.get("grid_settings", {})
        max_steps = int(grid_cfg.get("max_scroll_steps", 20))
        scroll_ticks = int(grid_cfg.get("scroll_ticks_per_step", 1))

        prev_roi_img = None
        cumulative_y = 0
        seen_items = []

        for step in range(max_steps):
            if self.abort_requested:
                break

            curr_roi_img = self.vision.capture_screen(roi)
            if prev_roi_img is not None:
                dy = self.vision.detect_vertical_scroll_shift(prev_roi_img, curr_roi_img)
                if dy > 0:
                    cumulative_y += dy
                else:
                    cumulative_y += max(10, int(grid_cfg.get("scroll_depth_px", 40)))

            items = self.vision.scan_visible_inventory(roi, min_y_offset=0, roi_img=curr_roi_img)
            for itm in items:
                sw = itm.get("slot_w", itm.get("slot_box", (0, 0, 38, 38))[2])
                sh = itm.get("slot_h", itm.get("slot_box", (0, 0, 38, 38))[3])
                sx = itm.get("slot_x", itm.get("slot_box", (0, 0, 38, 38))[0])
                sy = itm.get("slot_y", itm.get("slot_box", (0, 0, 38, 38))[1])
                col = max(0, min(6, int(round((sx + sw / 2.0 - 20) / 41.2))))
                global_y = cumulative_y + (sy + sh / 2.0)

                is_dup = False
                for seen in seen_items:
                    if seen["col"] == col and abs(seen["global_y"] - global_y) < 22:
                        is_dup = True
                        break

                if not is_dup:
                    seen_items.append({
                        "col": col,
                        "global_y": global_y,
                        "ref_file": itm.get("ref_file"),
                        "gear_name": itm.get("gear_name", "item"),
                        "level": str(itm.get("level", "")),
                        "rarity": itm.get("rarity", "Common"),
                        "bracket": itm.get("bracket", "")
                    })

            prev_roi_img = curr_roi_img.copy()

            if step < max_steps - 1 and not self.abort_requested:
                moved, at_bottom, diff = self.scroll_inventory_down(scroll_ticks)
                time.sleep(0.35)
                if at_bottom:
                    break

        # Reset inventory back to top row
        self.scroll_to_top(activate_first=False)
        time.sleep(0.3)
        return seen_items

    def pass2a_count_inventory(self, inv_roi: Dict[str, int]) -> Dict[Tuple[str, str], int]:
        """
        Legacy/Test Wrapper: Full Inventory Count Scan.
        1. Clicks Sort button
        2. 2x left-click on slot (0,0)
        3. Scrolls to top
        4. Scans inventory items top to bottom
        """
        if not self.cycle_running:
            self.reset_abort_state()

        self.click_inventory_sort_button()
        time.sleep(0.35)
        self.activate_scroll_with_double_click(inv_roi)
        time.sleep(0.3)
        self.scroll_to_top(activate_first=False)
        time.sleep(0.4)
        return self.scan_inventory_counts(inv_roi)

    def scan_and_synthesize(self) -> int:
        """
        Legacy/Test Wrapper: Runs count and executes highest priority synthesis if >= 9.
        """
        inv_roi = self.vision.get_inventory_roi()
        counts = self.pass2a_count_inventory(inv_roi)
        target = self.find_highest_priority_recipe(counts)
        if target:
            success = self.execute_synthesis_flow(target[0], target[1], inv_roi)
            return 1 if success else 0
        return 0

    # ---------------------------------------------------------
    # Instant Diagnostic Test Functions
    # ---------------------------------------------------------
    def test_single_step_scroll(self) -> Tuple[bool, bool, float]:
        """
        Executes the responsive 5-step scroll test sequence:
        1. 2x left-click on slot (0,0) for initial inventory focus
        2. Click Inventory Sort Button to organize all items
        3. 2x left-click on slot (0,0) to re-engage scroll focus
        4. Scroll up to top row (row 0)
        5. Scroll 1 step down by configured scroll height/depth
        """
        self.reset_abort_state()
        self.log(f"--- Testing 1-Step Scroll ({self.scroll_mode}) ---", "info")
        inv_roi = self.vision.get_inventory_roi()

        # Step 1: 2x left-click focus activation on inventory slot
        self.log("Step 1/5: Activating inventory focus via 2x left-click...", "info")
        self.activate_scroll_with_double_click(inv_roi)
        time.sleep(0.3)

        # Step 2: Click Inventory Sort Button
        self.log("Step 2/5: Clicking Inventory Sort button...", "info")
        self.click_inventory_sort_button()
        time.sleep(0.35)

        # Step 3: 2x left-click on slot (0,0)
        self.log("Step 3/5: 2x left-click on slot (0,0)...", "info")
        self.activate_scroll_with_double_click(inv_roi)
        time.sleep(0.3)

        # Step 4: Scroll up to top row
        self.log("Step 4/5: Scrolling up to top row...", "info")
        self.scroll_to_top(activate_first=False)
        time.sleep(0.4)

        # Step 5: Scroll 1 step down
        self.log("Step 5/5: Scrolling 1 step down...", "info")
        before_bgr = self.vision.capture_screen(inv_roi)

        moved, at_bottom, diff = self.scroll_inventory_down(1)

        after_bgr = self.vision.capture_screen(inv_roi)
        measured_dy = self.vision.detect_vertical_scroll_shift(before_bgr, after_bgr)

        grid_cfg = self.config.get("grid_settings", {})
        target_depth = int(grid_cfg.get("scroll_depth_px", 40))

        shift_str = f"{measured_dy} px" if measured_dy > 0 else "Indeterminate"
        self.log(f"Result: moved={moved}, measured shift={shift_str} (target depth: {target_depth} px, pixel diff: {diff:.2f})", "info")
        if moved:
            if measured_dy > 0:
                self.log(f"SUCCESS: Inventory moved down by {measured_dy} px (target depth: {target_depth} px)!", "info")
            else:
                self.log(f"SUCCESS: Game detected scroll hover and inventory moved (pixel diff: {diff:.2f}, target depth: {target_depth} px)!", "info")
        else:
            self.log("WARNING: Movement not detected. Game may need a click to focus.", "warning")
        return moved, at_bottom, diff

    def test_visual_scan(self) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Test 1: Captures visible inventory, classifies items, logs counts."""
        self.reset_abort_state()
        inv_roi = self.vision.get_inventory_roi()
        self.reload_config()
        self.vision.clear_cache()

        items = self.vision.scan_visible_inventory(inv_roi)
        if self.on_items_detected and items:
            self.on_items_detected(items)

        # Update live bucket counters from visible items
        counts: Dict[Tuple[str, str], int] = {
            (b, r): 0
            for b in ["65", "80_90"]
            for r in ["Common", "Uncommon", "Rare", "Legendary"]
        }
        for itm in items:
            b = itm["bracket"]
            r = itm["rarity"]
            if (b, r) in counts:
                counts[(b, r)] += 1
        self._sync_and_publish_counts(counts)

        annotated, stats = self.vision.render_debug_overlay(inv_roi=inv_roi, mode="inventory")

        self.log("--- Test Visual Scan Results ---", "info")
        ref_stats = stats.get("ref_stats", {})
        if ref_stats.get("loaded"):
            self.log(f"SS Reference Library: {ref_stats.get('total', 0)} templates active ({self.vision.ss_dir}/)", "info")
        self.log(f"Total matching items detected: {stats['total_items']}", "info")
        self.log(f"  Tier 65: {stats['tier_65']} | Tier 80-90: {stats['tier_80_90']}", "info")
        rc = stats["rarity_counts"]
        self.log(f"  Rarities — Common: {rc['Common']}, Uncommon: {rc['Uncommon']}, Rare: {rc['Rare']}, Legendary: {rc['Legendary']}", "info")
        for itm in items:
            g_str = f"Lv.{itm.get('level', itm['bracket'])} {itm.get('gear_name', 'gear')} ({itm['rarity']})"
            f_str = f" [file: {itm.get('ref_file')}, conf: {itm.get('score', 0):.2f}]" if itm.get('ref_file') else ""
            self.log(f"   • {g_str}{f_str} at ({itm['click_x']}, {itm['click_y']})", "info")
        self.log("--------------------------------", "info")
        return annotated, stats

    def test_scroll_top_to_bottom(self):
        """Test 2: Scrolls inventory top-to-bottom and logs deduplicated totals."""
        def _worker():
            self.reset_abort_state()
            self.log(f"--- Starting Full Scroll Test (Mode: {self.scroll_mode}) ---", "info")
            inv_roi = self.vision.get_inventory_roi()
            self.reload_config()
            self.vision.clear_cache()

            counts = self.pass2a_count_inventory(inv_roi)
            self.log("--- Full Scroll Test Results ---", "info")
            for (b, r), cnt in counts.items():
                label = "Lv.65 (Tier 65-80)" if b == "65" else "Lv.80-90 (Tier 80-90)"
                self.log(f"  {label} - {r}: {cnt} items", "info")
            self.log("--- Scroll Test Complete ---", "info")

            self.log("Resetting inventory back to top row...", "info")
            self.scroll_to_top()

        threading.Thread(target=_worker, daemon=True).start()

    def test_chest_detection(self) -> Dict[str, Any]:
        """Test Chest Detection: Checks screen for Blue/Brown chests, Inven Full states, and Empty Floor."""
        self.reset_abort_state()
        chest_roi = self.config.get("rois", {}).get("chest_region")
        self.reload_config()
        self.vision.clear_cache()

        state = self.vision.detect_chest_state(chest_roi)
        self.log("--- Test Chest Detection Results ---", "info")
        self.log(f"  Status Summary: {state['status_str']}", "info")
        self.log(f"  Available Chest Found: {state['chest_found']} (type: {state['chest_type']}, conf: {state['chest_conf']:.2f})", "info")
        self.log(f"  Inven Full Detected: {state['inv_full_found']} (type: {state['inv_full_type']}, conf: {state['inv_full_conf']:.2f})", "info")
        self.log(f"  Empty Floor Detected: {state['empty_found']} (conf: {state['empty_conf']:.2f})", "info")

        if state.get("inv_full_found"):
            self.log(f"  Bot Action: INVENTORY FULL ({state['inv_full_type']}). Chest opening stopped. Bot will proceed to sort & synthesize.", "warning")
        elif state["chest_found"]:
            self.log(f"  Bot Action: {state['chest_type']} available! Bot will press Space key to open all chests.", "info")
        elif state["empty_found"] and state["empty_conf"] >= 0.80:
            self.log("  Bot Action: Floor verified empty (0 chests remaining). Proceeding to next step.", "info")
        else:
            self.log("  Bot Action: No chest or full state detected in ROI.", "info")
        self.log("------------------------------------", "info")
        return state
