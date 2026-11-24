"""
Chest Detection Module for Task Bar Hero.
Handles detection of chest types (Blue, Brown, Legacy), inventory full warnings, and empty floor states.
"""
from typing import Optional, Dict, Any, Tuple
import cv2
import numpy as np
from .template_matcher import TemplateMatcher
from .screen import ScreenCapture


class ChestDetector:
    def __init__(self, matcher: TemplateMatcher, config: Optional[Dict[str, Any]] = None):
        self.matcher = matcher
        self.config = config or {}

    def update_config(self, config_data: Dict[str, Any]):
        self.config = config_data

    def detect_chest_state(self, chest_roi: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """
        Checks chest region for:
        1. Inven Full states: inv_full_blue.png, inv_full_brown.png, inv_full_text.png, inv_full.png
        2. Available chests: chest_blue.png, chest_brown.png, chest_pile.png
        3. Empty floor: empty_floor.png
        Returns dict with confidence scores, chest types, and detection booleans.
        """
        roi = chest_roi or self.config.get("rois", {}).get("chest_region", {"x": 300, "y": 450, "width": 120, "height": 120})
        screen_roi = ScreenCapture.capture_screen(roi)
        gray_roi = cv2.cvtColor(screen_roi, cv2.COLOR_BGR2GRAY) if len(screen_roi.shape) == 3 else screen_roi

        # 1. Check for INVEN FULL over chest
        inv_full_candidates = [
            ("inv_full_blue.png", "Blue Chest (Inven Full)", 0.70),
            ("inv_full_brown.png", "Brown Chest (Inven Full)", 0.70),
            ("inv_full_text.png", "Inven Full Text", 0.70),
            ("inv_full.png", "Inven Full Warning", 0.75)
        ]
        inv_full_found = False
        inv_full_type = None
        inv_full_conf = 0.0

        for tmpl_name, type_label, thresh in inv_full_candidates:
            if self.matcher.template_exists(tmpl_name):
                m = self.matcher.find_template(gray_roi, tmpl_name, threshold=thresh)
                if m and m[4] > inv_full_conf:
                    inv_full_conf = m[4]
                    inv_full_found = True
                    inv_full_type = type_label

        # 2. Check for available chests (Blue, Brown, Legacy Pile)
        chest_candidates = [
            ("chest_blue.png", "Blue Chest", 0.70),
            ("chest_brown.png", "Brown Chest", 0.70),
            ("chest_pile.png", "Chest Pile", 0.70)
        ]
        best_chest_match = None
        best_chest_type = None
        best_chest_conf = 0.0

        for tmpl_name, type_label, thresh in chest_candidates:
            if self.matcher.template_exists(tmpl_name):
                m = self.matcher.find_template(gray_roi, tmpl_name, threshold=thresh)
                if m and m[4] > best_chest_conf:
                    best_chest_conf = m[4]
                    best_chest_type = type_label
                    best_chest_match = m

        # 3. Check for empty floor (only relevant if no chest was found)
        empty_match = self.matcher.find_template(gray_roi, "empty_floor.png", threshold=0.75) if not best_chest_match else None
        empty_conf = empty_match[4] if empty_match else 0.0

        chest_pos = None
        if best_chest_match:
            chest_pos = (roi["x"] + best_chest_match[0] + best_chest_match[2] // 2,
                         roi["y"] + best_chest_match[1] + best_chest_match[3] // 2)

        # Determine human-readable status string
        if inv_full_found:
            status_str = f"INVEN FULL ({inv_full_type})"
        elif best_chest_match and not inv_full_found:
            status_str = f"{best_chest_type.upper()} AVAILABLE ({int(best_chest_conf * 100)}%)"
        elif empty_match and empty_conf >= 0.80:
            status_str = f"EMPTY FLOOR CONFIRMED ({int(empty_conf * 100)}%)"
        else:
            status_str = "NO CHEST DETECTED"

        return {
            "chest_found": (best_chest_match is not None and not inv_full_found),
            "chest_type": best_chest_type,
            "chest_pos": chest_pos,
            "chest_conf": best_chest_conf,
            "inv_full_found": inv_full_found,
            "inv_full_conf": inv_full_conf,
            "inv_full_type": inv_full_type,
            "empty_found": empty_match is not None,
            "empty_conf": empty_conf,
            "status_str": status_str
        }

    def is_chest_present(
        self,
        chest_roi: Optional[Dict[str, int]] = None,
        check_empty: bool = True
    ) -> Tuple[bool, Optional[Tuple[int, int]]]:
        """
        Returns (is_present, (click_x, click_y)).
        If empty_floor.png matches strongly (>= 0.82) and chest is not detected, returns (False, None).
        If inventory is full, returns (False, None).
        """
        state = self.detect_chest_state(chest_roi)
        if state.get("inv_full_found"):
            return False, None

        if check_empty and state["empty_found"] and state["empty_conf"] >= 0.82 and not state["chest_found"]:
            return False, None

        if state["chest_found"]:
            return True, state["chest_pos"]

        # If user hasn't snipped chest templates yet, default to center of ROI
        roi = chest_roi or self.config.get("rois", {}).get("chest_region")
        if roi and not (self.matcher.template_exists("chest_blue.png") or self.matcher.template_exists("chest_brown.png") or self.matcher.template_exists("chest_pile.png")):
            cx = roi["x"] + roi["width"] // 2
            cy = roi["y"] + roi["height"] // 2
            return True, (cx, cy)

        return False, None

    def is_empty_ground_confirmed(self, chest_roi: Optional[Dict[str, int]] = None, threshold: float = 0.82) -> bool:
        """Confirms whether 0 chests remain using empty_floor.png."""
        state = self.detect_chest_state(chest_roi)
        return state["empty_conf"] >= threshold and state["chest_conf"] < 0.70 and not state.get("inv_full_found", False)

    def is_inventory_full(self, chest_roi: Optional[Dict[str, int]] = None) -> bool:
        """
        Check if inventory is full.
        Checks chest ROI first for inv_full_blue.png, inv_full_brown.png, inv_full_text.png,
        then full screen for inv_full.png or inv_full_text.png.
        """
        roi = chest_roi or self.config.get("rois", {}).get("chest_region")
        if roi:
            chest_crop = ScreenCapture.capture_screen(roi)
            gray_crop = cv2.cvtColor(chest_crop, cv2.COLOR_BGR2GRAY) if len(chest_crop.shape) == 3 else chest_crop
            for inv_tmpl in ["inv_full_blue.png", "inv_full_brown.png", "inv_full_text.png"]:
                if self.matcher.template_exists(inv_tmpl):
                    m = self.matcher.find_template(gray_crop, inv_tmpl, threshold=0.70)
                    if m:
                        return True

        # Fallback to full screen
        screen = ScreenCapture.capture_screen()
        gray_screen = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY) if len(screen.shape) == 3 else screen
        for inv_tmpl in ["inv_full.png", "inv_full_blue.png", "inv_full_brown.png", "inv_full_text.png"]:
            if self.matcher.template_exists(inv_tmpl):
                m = self.matcher.find_template(gray_screen, inv_tmpl, threshold=0.75)
                if m:
                    return True
        return False
