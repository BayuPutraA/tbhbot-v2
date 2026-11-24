"""
Hardware Input and Window Interaction Module for Task Bar Hero.
Dispatches jittered mouse clicks, hardware hover events, Space key chest interactions,
inventory sort button clicks, double-click scroll focus activations, and Win32 mouse wheel scrolling.
"""
import time
import random
import ctypes
from typing import Optional, Dict, Tuple
import cv2
import numpy as np
import pyautogui
import pydirectinput

# Win32 user32 handle for native mouse wheel & cursor dispatch
user32 = ctypes.windll.user32

# Configure pyautogui safety
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.04


class InputActions:
    def __init__(self, engine):
        self.engine = engine

    @property
    def abort_requested(self) -> bool:
        return self.engine.abort_requested

    @property
    def vision(self):
        return self.engine.vision

    @property
    def config(self) -> dict:
        return self.engine.config

    def log(self, msg: str, level: str = "info"):
        self.engine.log(msg, level)

    def click_point(self, x: int, y: int, jitter: int = 2, delay_after: float = 0.15, button: str = 'left'):
        """Clicks coordinate with minor random human jitter and specified mouse button ('left' or 'right')."""
        if self.abort_requested:
            return

        self.engine.bot_is_controlling_mouse = True
        try:
            jx = x + random.randint(-jitter, jitter)
            jy = y + random.randint(-jitter, jitter)
            pyautogui.moveTo(jx, jy, duration=random.uniform(0.06, 0.14))
            pyautogui.click(button=button)
            time.sleep(delay_after + random.uniform(0.02, 0.05))
        finally:
            self.engine.bot_is_controlling_mouse = False

    def ctrl_right_click(self, x: int, y: int, jitter: int = 2, delay_after: float = 0.2):
        """
        Executes Ctrl + Right-Click at (x, y) to transfer an item directly to the open Stash.
        """
        if self.abort_requested:
            return

        prev_controlling = self.engine.bot_is_controlling_mouse
        self.engine.bot_is_controlling_mouse = True
        try:
            jx = x + random.randint(-jitter, jitter)
            jy = y + random.randint(-jitter, jitter)
            pyautogui.moveTo(jx, jy, duration=random.uniform(0.06, 0.12))
            time.sleep(0.04)

            # Hold Ctrl, right-click, release Ctrl
            pyautogui.keyDown('ctrl')
            time.sleep(0.04)
            pyautogui.mouseDown(button='right')
            time.sleep(0.05)
            pyautogui.mouseUp(button='right')
            time.sleep(0.04)
            pyautogui.keyUp('ctrl')
            time.sleep(delay_after + random.uniform(0.02, 0.05))
        except Exception as e:
            self.log(f"Warning during ctrl_right_click at ({x}, {y}): {e}", "warning")
        finally:
            try:
                pyautogui.keyUp('ctrl')
            except Exception:
                pass
            self.engine.bot_is_controlling_mouse = prev_controlling

    def alt_right_click(self, x: int, y: int, jitter: int = 2, delay_after: float = 0.22):
        """
        Executes Alt + Right-Click at (x, y) to send an item directly into the Cube.
        """
        if self.abort_requested:
            return

        prev_controlling = self.engine.bot_is_controlling_mouse
        self.engine.bot_is_controlling_mouse = True
        try:
            jx = x + random.randint(-jitter, jitter)
            jy = y + random.randint(-jitter, jitter)
            pyautogui.moveTo(jx, jy, duration=random.uniform(0.06, 0.12))
            time.sleep(0.04)

            # Hold Alt, right-click, release Alt
            pyautogui.keyDown('alt')
            time.sleep(0.04)
            pyautogui.mouseDown(button='right')
            time.sleep(0.05)
            pyautogui.mouseUp(button='right')
            time.sleep(0.04)
            pyautogui.keyUp('alt')
            time.sleep(delay_after + random.uniform(0.02, 0.05))
        except Exception as e:
            self.log(f"Warning during alt_right_click at ({x}, {y}): {e}", "warning")
        finally:
            try:
                pyautogui.keyUp('alt')
            except Exception:
                pass
            self.engine.bot_is_controlling_mouse = prev_controlling

    def drag_and_drop(self, from_x: int, from_y: int, to_x: int, to_y: int) -> bool:
        """
        Transfers an item from (from_x, from_y) to (to_x, to_y) using TBH's click-to-pick-up mechanics:
        1. Move to source -> Click to pick up item onto cursor.
        2. Move smoothly to destination -> Click to drop item into target slot.
        """
        if self.abort_requested:
            return False

        prev_controlling = self.engine.bot_is_controlling_mouse
        self.engine.bot_is_controlling_mouse = True
        try:
            self.log(f"Transferring item: pick up at ({from_x}, {from_y}) -> drop at ({to_x}, {to_y})...", "info")
            # Step 1: Move to source
            pyautogui.moveTo(from_x, from_y, duration=random.uniform(0.08, 0.14))
            time.sleep(0.08)

            # Step 2: Left-click to pick up item
            pyautogui.mouseDown(button='left')
            time.sleep(0.05)
            pyautogui.mouseUp(button='left')
            time.sleep(0.15)

            if self.abort_requested:
                pyautogui.click(button='left')
                return False

            # Step 3: Move to destination
            pyautogui.moveTo(to_x, to_y, duration=random.uniform(0.14, 0.22))
            time.sleep(0.10)

            # Step 4: Left-click to drop item
            pyautogui.mouseDown(button='left')
            time.sleep(0.05)
            pyautogui.mouseUp(button='left')
            time.sleep(0.20)

            self.log(f"Successfully transferred item to ({to_x}, {to_y}).", "info")
            return True
        except Exception as e:
            self.log(f"Error during item transfer: {e}", "warning")
            return False
        finally:
            self.engine.bot_is_controlling_mouse = prev_controlling

    def press_space(self, delay_after: float = 0.22):
        """
        Dispatches a Space key press to interact with and open chests.
        Uses pydirectinput with Win32 keybd_event fallback.
        """
        if self.abort_requested:
            return

        try:
            pydirectinput.keyDown('space')
            time.sleep(0.04)
            pydirectinput.keyUp('space')
        except Exception:
            user32.keybd_event(0x20, 0x39, 0, 0)       # VK_SPACE down
            time.sleep(0.04)
            user32.keybd_event(0x20, 0x39, 0x0002, 0)  # VK_SPACE up
        time.sleep(delay_after)

    def activate_game_hover(self, x: int, y: int):
        """
        Guarantees that Unity's EventSystem registers real mouse hover on the inventory:
        Sends genuine hardware WM_MOUSEMOVE inputs via pyautogui to trigger OnPointerEnter.
        Does NOT touch window focus or call SetForegroundWindow, so the bot window is never minimized or demoted.
        """
        try:
            pyautogui.moveTo(int(x) - 4, int(y), duration=0.03)
            pyautogui.moveTo(int(x), int(y), duration=0.03)
        except Exception:
            user32.SetCursorPos(int(x), int(y))
        time.sleep(0.04)

    def click_inventory_sort_button(self) -> bool:
        """
        Locates and clicks the inventory sort button (located on the right side of the Inventory tab).
        Organizes all inventory items before the scroll sequence begins.
        """
        if self.abort_requested:
            return False

        prev_controlling = self.engine.bot_is_controlling_mouse
        self.engine.bot_is_controlling_mouse = True
        try:
            inv_roi = self.vision.get_inventory_roi()
            screen = self.vision.capture_screen()

            sort_x = None
            sort_y = None

            # Strategy 1: Match dedicated inv_sort_btn.png template directly on screen
            if self.vision.template_exists("inv_sort_btn.png"):
                match = self.vision.find_template(screen, "inv_sort_btn.png", threshold=0.70)
                if match:
                    sort_x = match[0] + match[2] // 2
                    sort_y = match[1] + match[3] // 2

            # Strategy 2: Check configured button coords
            if sort_x is None:
                sort_cfg = self.config.get("button_coords", {}).get("inv_sort_btn")
                if sort_cfg and "x" in sort_cfg and "y" in sort_cfg and int(sort_cfg["x"]) > 0:
                    sort_x = int(sort_cfg["x"])
                    sort_y = int(sort_cfg["y"])

            # Strategy 3: Match inv_tab_btn.png and offset to sort icon (x+107, y+18)
            if sort_x is None and self.vision.template_exists("inv_tab_btn.png"):
                tab_match = self.vision.find_template(screen, "inv_tab_btn.png", threshold=0.70)
                if tab_match:
                    sort_x = tab_match[0] + 107
                    sort_y = tab_match[1] + 18

            # Strategy 4: Geometric fallback directly above inventory ROI
            if sort_x is None:
                sort_x = int(inv_roi["x"] + 107)
                sort_y = int(inv_roi["y"] - 18)

            self.log(f"Sorting inventory: clicking Sort button at ({sort_x}, {sort_y})...", "info")
            pyautogui.moveTo(sort_x, sort_y, duration=0.10)
            time.sleep(0.08)
            pyautogui.mouseDown(button='left')
            time.sleep(0.08)
            pyautogui.mouseUp(button='left')
            time.sleep(0.40)  # Wait for inventory sorting animation
            self.log("Inventory sorted successfully.", "info")
            return True
        except Exception as e:
            self.log(f"Warning during sort button click: {e}", "warning")
            return False
        finally:
            self.engine.bot_is_controlling_mouse = prev_controlling

    def activate_scroll_with_double_click(self, inv_roi: Optional[Dict[str, int]] = None):
        """
        Activates Unity ScrollRect focus by performing a 2x left-click on an inventory slot.
        1st left-click: picks up item and grants Unity EventSystem focus to the inventory scroll view.
        2nd left-click: drops the item back down in the exact same slot without altering inventory.
        Does NOT call SetForegroundWindow, keeping the bot window unaffected.
        """
        if self.abort_requested:
            return

        if inv_roi is None:
            inv_roi = self.vision.get_inventory_roi()

        # Slot (0, 0) top-left item center (approx +22px from ROI top-left)
        slot_x = int(inv_roi["x"] + 22)
        slot_y = int(inv_roi["y"] + 22)

        prev_controlling = self.engine.bot_is_controlling_mouse
        self.engine.bot_is_controlling_mouse = True
        try:
            self.log(f"Activating scroll focus: 2x left-click on slot at ({slot_x}, {slot_y})...", "info")
            pyautogui.moveTo(slot_x, slot_y, duration=0.08)
            time.sleep(0.06)

            # 1st left-click: pick up item
            pyautogui.mouseDown(button='left')
            time.sleep(0.04)
            pyautogui.mouseUp(button='left')
            time.sleep(0.12)

            # 2nd left-click: drop item back into same slot
            pyautogui.mouseDown(button='left')
            time.sleep(0.04)
            pyautogui.mouseUp(button='left')
            time.sleep(0.15)
        except Exception as e:
            self.log(f"Warning during scroll activation click: {e}", "warning")
        finally:
            self.engine.bot_is_controlling_mouse = prev_controlling

    def wheel_scroll(self, ticks: int, x: Optional[int] = None, y: Optional[int] = None, delay_per_notch: float = 0.04):
        """
        Dispatches real hardware mouse wheel events notch-by-notch with hover activation.
        Positive ticks = scroll UP (toward top).
        Negative ticks = scroll DOWN (toward bottom).
        """
        if x is not None and y is not None:
            self.activate_game_hover(x, y)

        notch_count = abs(ticks)
        direction_notch = 120 if ticks > 0 else -120
        for _ in range(notch_count):
            if self.abort_requested:
                break
            pyautogui.scroll(direction_notch)
            if delay_per_notch > 0:
                time.sleep(delay_per_notch)
        time.sleep(0.15)

    def scroll_to_top(self, ticks: int = 35, activate_first: bool = False):
        """
        Resets inventory to the top row.
        If activate_first is True, performs 2x left-click activation first.
        Scrolls upward to guarantee reaching the very top row.
        """
        inv_roi = self.vision.get_inventory_roi()
        cx = inv_roi["x"] + inv_roi["width"] // 2
        cy = inv_roi["y"] + inv_roi["height"] // 2

        self.engine.bot_is_controlling_mouse = True
        try:
            if activate_first:
                self.activate_scroll_with_double_click(inv_roi)

            self.log("Scrolling up to top of inventory...", "info")
            if "Drag" in getattr(self.engine, "scroll_mode", ""):
                for _ in range(min(ticks, 10)):
                    if self.abort_requested:
                        break
                    pyautogui.moveTo(cx, cy - 35)
                    time.sleep(0.03)
                    pyautogui.mouseDown(button='left')
                    time.sleep(0.03)
                    pyautogui.moveTo(cx, cy + 35, duration=0.12)
                    time.sleep(0.03)
                    pyautogui.mouseUp(button='left')
                    time.sleep(0.08)
            else:
                pyautogui.moveTo(cx, cy, duration=0.05)
                time.sleep(0.04)
                for _ in range(ticks):
                    if self.abort_requested:
                        break
                    pyautogui.scroll(120)
                    time.sleep(0.02)

            time.sleep(0.4)  # Settle delay
        finally:
            self.engine.bot_is_controlling_mouse = False

    def scroll_to_bottom(self, ticks: int = 35, activate_first: bool = False):
        """
        Scrolls inventory all the way down to the bottom row.
        If activate_first is True, performs 2x left-click activation first.
        Scrolls downward to guarantee reaching the very bottom of the inventory.
        """
        inv_roi = self.vision.get_inventory_roi()
        cx = inv_roi["x"] + inv_roi["width"] // 2
        cy = inv_roi["y"] + inv_roi["height"] // 2

        self.engine.bot_is_controlling_mouse = True
        try:
            if activate_first:
                self.activate_scroll_with_double_click(inv_roi)

            self.log("Scrolling down to bottom of inventory...", "info")
            if "Drag" in getattr(self.engine, "scroll_mode", ""):
                for _ in range(min(ticks, 10)):
                    if self.abort_requested:
                        break
                    pyautogui.moveTo(cx, cy + 35)
                    time.sleep(0.03)
                    pyautogui.mouseDown(button='left')
                    time.sleep(0.03)
                    pyautogui.moveTo(cx, cy - 35, duration=0.12)
                    time.sleep(0.03)
                    pyautogui.mouseUp(button='left')
                    time.sleep(0.08)
            else:
                self.activate_game_hover(cx, cy)
                pyautogui.moveTo(cx, cy, duration=0.05)
                time.sleep(0.04)
                for _ in range(ticks):
                    if self.abort_requested:
                        break
                    pyautogui.scroll(-120)
                    time.sleep(0.02)

            time.sleep(0.4)  # Settle delay
        finally:
            self.engine.bot_is_controlling_mouse = False

    def scroll_inventory_down(self, ticks: int = 1) -> Tuple[bool, bool, float]:
        """
        Slowly scrolls inventory DOWN by 1 row step with hardware hover activation & motion measurement.
        Supports both 'Hardware Wheel' and 'Mouse Drag Scroll' techniques.
        Returns (moved: bool, at_bottom: bool, diff: float).
        """
        inv_roi = self.vision.get_inventory_roi()
        cx = inv_roi["x"] + inv_roi["width"] // 2
        cy = inv_roi["y"] + inv_roi["height"] // 2

        self.engine.bot_is_controlling_mouse = True
        try:
            before_bgr = self.vision.capture_screen(inv_roi)
            before_gray = cv2.cvtColor(before_bgr, cv2.COLOR_BGR2GRAY)

            self.activate_game_hover(cx, cy)

            grid_cfg = self.config.get("grid_settings", {})
            scroll_depth = max(10, int(grid_cfg.get("scroll_depth_px", 40)))

            if "Drag" in getattr(self.engine, "scroll_mode", ""):
                drag_dist = scroll_depth * ticks
                pyautogui.moveTo(cx, cy + drag_dist // 2)
                time.sleep(0.04)
                pyautogui.mouseDown(button='left')
                time.sleep(0.04)
                pyautogui.moveTo(cx, cy - drag_dist // 2, duration=0.18)
                time.sleep(0.04)
                pyautogui.mouseUp(button='left')
                time.sleep(0.35)
            else:
                base_wheel = int(grid_cfg.get("scroll_amount", -120))
                if base_wheel < -240:
                    base_wheel = -120

                if scroll_depth != 40 and base_wheel == -120:
                    wheel_delta = -int(round(120.0 * (scroll_depth / 40.0)))
                else:
                    wheel_delta = base_wheel

                for _ in range(ticks):
                    if self.abort_requested:
                        break
                    pyautogui.scroll(wheel_delta)
                    time.sleep(0.05)
                time.sleep(0.35)

            after_bgr = self.vision.capture_screen(inv_roi)
            after_gray = cv2.cvtColor(after_bgr, cv2.COLOR_BGR2GRAY)
            final_diff = float(np.mean(cv2.absdiff(before_gray, after_gray)))

            at_bottom = final_diff < 1.5
            moved = final_diff >= 1.5
            return moved, at_bottom, final_diff
        finally:
            self.engine.bot_is_controlling_mouse = False

