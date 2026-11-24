"""
Cube Synthesis Automation Module for Task Bar Hero.
Handles deterministic manual recipe selection, dropdown tier selection,
Alt+Right-Click item loading, synthesize button execution, and return button retrieval.
"""
from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Any, List


class SynthesisManager:
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

    def set_status(self, status: str):
        self.engine.set_status(status)

    def ensure_cube_and_inventory_open(self):
        """
        Assumes synthesis view is always open on screen as per user configuration.
        Does not click cube_btn.png to avoid toggling or closing the window.
        """
        return

    def find_highest_priority_recipe(self, counts: Dict[Tuple[str, str], int]) -> Optional[Tuple[str, str]]:
        """
        Finds the highest priority recipe with >= 9 items.
        Priority:
        1. Lv. 80~90 ('80_90') - in order: Legendary, Rare, Uncommon, Common
        2. Lv. 65~80 ('65')    - in order: Legendary, Rare, Uncommon, Common
        """
        for bracket in ["80_90", "65"]:
            for rarity in ["Legendary", "Rare", "Uncommon", "Common"]:
                if counts.get((bracket, rarity), 0) >= 9:
                    return (bracket, rarity)
        return None

    def select_cube_tier(self, bracket: str):
        """
        Deterministic Cube Tier Selection (Option A: Calibrated Points):
        1. Checks if auto-selection is enabled ('auto_select_cube_tier', default True).
           If False, assumes player already set the desired tier on Cube UI and bypasses dropdown completely.
        2. Retrieves calibrated coordinates for dropdown and target tier option (Lv.80~90 or Lv.65~80).
        3. Clicks the dropdown button to expand the tier options list.
        4. Clicks the calibrated tier option point (or relative vertical offset below dropdown).
           Does NOT use brittle template matching on identical-looking text.
        """
        if bracket == "50":
            tier_label = "Lv.50"
            coord_key = "tier_50"
        elif bracket == "80_90":
            tier_label = "Lv.80~90"
            coord_key = "tier_80_90"
        else:
            tier_label = "Lv.65~80"
            coord_key = "tier_65_80"

        # Check if user disabled auto tier selection
        auto_select = self.config.get("auto_select_cube_tier", True)
        tier_mode = self.config.get("cube_tier_selection_mode", "calibrated")
        if not auto_select or tier_mode == "disabled":
            self.log(f"Cube tier auto-selection is disabled (user maintains tier in game). Skipping dropdown.", "info")
            return

        btn_coords = self.config.get("button_coords", {})
        drop_cfg = btn_coords.get("cube_dropdown")
        tier_cfg = btn_coords.get(coord_key)

        dx, dy = None, None
        if drop_cfg and "x" in drop_cfg and "y" in drop_cfg:
            dx, dy = int(drop_cfg["x"]), int(drop_cfg["y"])

        tx, ty = None, None
        if tier_cfg and "x" in tier_cfg and "y" in tier_cfg:
            tx, ty = int(tier_cfg["x"]), int(tier_cfg["y"])

        # If dropdown coords are missing or off-screen, warn user
        if dx is None or dy is None:
            self.log("Cube dropdown coordinates not calibrated! Please calibrate 'Cube Dropdown' in Calibrator tab. Skipping tier selection.", "warning")
            return

        self.log(f"Step 1/2: Opening Cube tier dropdown at ({dx}, {dy})...", "info")
        self.engine.click_point(dx, dy, delay_after=0.35)
        time.sleep(0.35)

        # Step 2: Click the target tier option
        if tx is not None and ty is not None:
            self.log(f"Step 2/2: Selecting Cube tier {tier_label} at calibrated point ({tx}, {ty})...", "info")
            self.engine.click_point(tx, ty, delay_after=0.35)
        else:
            # Fallback to relative vertical offset below dropdown:
            # Option Lv.50 is ~5px or above, Option 1 (Lv.65~80) is ~28px below, Option 2 (Lv.80~90) is ~55px below
            offset_y = 5 if bracket == "50" else (28 if bracket == "65" else 55)
            tx = dx
            ty = dy + offset_y
            self.log(f"Step 2/2: Selecting Cube tier {tier_label} via relative dropdown offset at ({tx}, {ty})...", "info")
            self.engine.click_point(tx, ty, delay_after=0.35)

        time.sleep(0.35)

    def test_cube_tier_selection(self, bracket: str = "80_90") -> bool:
        """
        Tests opening the Cube dropdown and selecting the given tier (e.g. '80_90' or '65').
        """
        self.engine.reset_abort_state()
        tier_label = "Lv.80~90" if bracket == "80_90" else "Lv.65~80"
        self.log(f"--- Testing Cube Dropdown Selection for {tier_label} ---", "info")
        btn_coords = self.config.get("button_coords", {})
        drop_cfg = btn_coords.get("cube_dropdown")
        if not drop_cfg or "x" not in drop_cfg or "y" not in drop_cfg:
            self.log("Cannot test dropdown: 'cube_dropdown' coordinate is not calibrated! Please calibrate it first.", "warning")
            return False

        dx, dy = int(drop_cfg["x"]), int(drop_cfg["y"])
        coord_key = "tier_80_90" if bracket == "80_90" else "tier_65_80"
        tier_cfg = btn_coords.get(coord_key)

        self.log(f"Step 1: Clicking dropdown at ({dx}, {dy})...", "info")
        self.engine.click_point(dx, dy, delay_after=0.35)
        time.sleep(0.35)

        if tier_cfg and "x" in tier_cfg and "y" in tier_cfg:
            tx, ty = int(tier_cfg["x"]), int(tier_cfg["y"])
            self.log(f"Step 2: Clicking calibrated {tier_label} option at ({tx}, {ty})...", "info")
            self.engine.click_point(tx, ty, delay_after=0.35)
        else:
            offset_y = 28 if bracket == "65" else 55
            tx, ty = dx, dy + offset_y
            self.log(f"Step 2: Clicking {tier_label} via relative offset at ({tx}, {ty})...", "info")
            self.engine.click_point(tx, ty, delay_after=0.35)

        time.sleep(0.3)
        self.log(f"Cube tier selection test for {tier_label} completed successfully.", "info")
        return True

    def switch_cube_mode(self, target_mode: str = "synthesis") -> bool:
        """
        Changes the Cube mode option between 'synthesis' and 'corrosion'.
        Uses calibrated 'cube_mode_dropdown' (or 'cube_dropdown') and
        'cube_option_corrosion' / 'cube_option_synthesis' coordinates.
        """
        target_mode = target_mode.lower().strip()
        mode_label = "Corrosion" if target_mode == "corrosion" else "Synthesis"
        coord_key = "cube_option_corrosion" if target_mode == "corrosion" else "cube_option_synthesis"

        btn_coords = self.config.get("button_coords", {})
        drop_cfg = btn_coords.get("cube_mode_dropdown") or btn_coords.get("cube_dropdown")
        option_cfg = btn_coords.get(coord_key)

        dx, dy = None, None
        if drop_cfg and "x" in drop_cfg and "y" in drop_cfg:
            dx, dy = int(drop_cfg["x"]), int(drop_cfg["y"])

        tx, ty = None, None
        if option_cfg and "x" in option_cfg and "y" in option_cfg:
            tx, ty = int(option_cfg["x"]), int(option_cfg["y"])

        # If direct option button is calibrated without dropdown (e.g. direct tab button)
        if dx is None and (tx is not None and ty is not None):
            self.log(f"[Cube Mode] Clicking direct {mode_label} option button at ({tx}, {ty})...", "info")
            self.engine.click_point(tx, ty, delay_after=0.35)
            time.sleep(0.3)
            return True

        if dx is None or dy is None:
            self.log(f"[Cube Mode] Neither 'cube_mode_dropdown' nor '{coord_key}' is calibrated! Please calibrate in Calibrator or Corrosion tab.", "warning")
            return False

        # Step 1: Open Mode Dropdown
        self.log(f"[Cube Mode] Step 1/2: Opening Cube mode dropdown at ({dx}, {dy})...", "info")
        self.engine.click_point(dx, dy, delay_after=0.35)
        time.sleep(0.35)

        # Step 2: Select target mode option
        if tx is not None and ty is not None:
            self.log(f"[Cube Mode] Step 2/2: Selecting '{mode_label}' at calibrated point ({tx}, {ty})...", "info")
            self.engine.click_point(tx, ty, delay_after=0.35)
        else:
            # Fallback relative vertical offset:
            # Synthesis = ~28px below dropdown, Corrosion = ~55px below dropdown
            offset_y = 55 if target_mode == "corrosion" else 28
            tx, ty = dx, dy + offset_y
            self.log(f"[Cube Mode] Step 2/2: Selecting '{mode_label}' via relative dropdown offset at ({tx}, {ty})...", "info")
            self.engine.click_point(tx, ty, delay_after=0.35)

        time.sleep(0.35)
        self.log(f"[Cube Mode] Mode option changed to '{mode_label}'.", "info")
        return True

    def test_switch_cube_mode(self, target_mode: str = "corrosion") -> bool:
        """Tests switching Cube mode option from GUI test button."""
        self.engine.reset_abort_state()
        mode_label = "Corrosion" if target_mode == "corrosion" else "Synthesis"
        self.log(f"--- Testing Cube Mode Switch to {mode_label} ---", "info")
        return self.switch_cube_mode(target_mode)

    def execute_corrosion_flow(self, inv_roi: Optional[Dict[str, int]] = None) -> int:
        """
        Executes the Corrosion flow:
        1. Changes Cube option from Synthesis into Corrosion.
        2. Regains inventory focus (2x left-click on slot 0,0).
        3. Resets inventory to top row.
        4. Scans inventory for materials matching the Corrosion List and includes them via ALT+RIGHT-CLICK.
        5. Scrolls through inventory until all visible corrosion materials are included.
        6. Moves Cube dropdown back into Synthesis.
        7. Regains inventory focus and resets to top row for subsequent material scanning.
        """
        roi = inv_roi or self.vision.get_inventory_roi()
        if not self.vision.has_corrosion_library():
            self.log("[Corrosion] No enabled corrosion templates found in SS_corrosion/. Skipping flow.", "warning")
            return 0

        self.set_status("Corrosion Flow (Loading Mats)")
        self.log("=== STARTING CUBE CORROSION FLOW ===", "info")

        # 1. Change Cube option from Synthesis into Corrosion
        self.switch_cube_mode("corrosion")
        time.sleep(0.4)

        if self.engine.abort_requested:
            self.switch_cube_mode("synthesis")
            return 0

        # 2. Regain inventory focus (2x left-click on slot 0,0)
        self.log("Focusing inventory for Corrosion loading: 2x left-click on slot (0,0)...", "info")
        self.engine.activate_scroll_with_double_click(roi)
        time.sleep(0.3)

        # 3. Reset to top row
        self.log("Resetting inventory to top row before loading corrosion materials...", "info")
        self.engine.scroll_to_top(activate_first=False)
        time.sleep(0.35)

        # 4. Scan and include corrosion materials (Strictly max 9 items)
        loaded = 0
        grid_cfg = self.config.get("grid_settings", {})
        max_steps = int(grid_cfg.get("max_scroll_steps", 20))
        scroll_ticks = int(grid_cfg.get("scroll_ticks_per_step", 1))

        for step in range(max_steps):
            if self.engine.abort_requested or loaded >= 9:
                break

            visible_mats = self.vision.scan_visible_corrosion_materials(roi)
            while visible_mats and loaded < 9 and not self.engine.abort_requested:
                first_mat = visible_mats[0]
                cx = first_mat["click_x"]
                cy = first_mat["click_y"]
                m_name = first_mat.get("name", first_mat.get("filename", "material"))

                self.engine.alt_right_click(cx, cy, jitter=2, delay_after=0.25)
                loaded += 1
                self.log(f"[Corrosion] Selected corrosion item #{loaded}/9: {m_name} into Cube via ALT+RIGHT-CLICK at ({cx}, {cy})", "info")
                time.sleep(0.2)

                if loaded >= 9:
                    self.log("[Corrosion] Reached exact limit of 9 corrosion items in Cube.", "info")
                    break

                visible_mats = self.vision.scan_visible_corrosion_materials(roi)

            if loaded >= 9:
                break

            if step < max_steps - 1 and not self.engine.abort_requested:
                moved, at_bottom, diff = self.engine.scroll_inventory_down(scroll_ticks)
                time.sleep(0.35)
                if at_bottom:
                    # Final check at the very bottom
                    visible_mats = self.vision.scan_visible_corrosion_materials(roi)
                    while visible_mats and loaded < 9 and not self.engine.abort_requested:
                        first_mat = visible_mats[0]
                        cx = first_mat["click_x"]
                        cy = first_mat["click_y"]
                        m_name = first_mat.get("name", first_mat.get("filename", "material"))

                        self.engine.alt_right_click(cx, cy, jitter=2, delay_after=0.25)
                        loaded += 1
                        self.log(f"[Corrosion] Selected corrosion item #{loaded}/9 at bottom: {m_name} via ALT+RIGHT-CLICK at ({cx}, {cy})", "info")
                        time.sleep(0.2)

                        if loaded >= 9:
                            self.log("[Corrosion] Reached exact limit of 9 corrosion items in Cube.", "info")
                            break

                        visible_mats = self.vision.scan_visible_corrosion_materials(roi)
                    break

        self.log(f"[Corrosion] Selection complete: Selected {loaded}/9 corrosion material(s) into Cube.", "info")

        # 5. Click the button at the same location as Synth Button to execute Corrosion!
        if loaded > 0:
            self.log(f"[Corrosion] Clicking button at Synth Button location to execute Corrosion on {loaded} items...", "info")
            time.sleep(0.4)
            self.click_synth_button()
            self.log("[Corrosion] Clicked Corrosion execute button. Waiting 1.0s for execution animation...", "info")
            time.sleep(1.0)
        else:
            self.log("[Corrosion] No corrosion materials found in inventory (0/9 selected). Skipping execution click.", "info")

        # 6. Move Cube dropdown back into Synthesis
        self.switch_cube_mode("synthesis")
        time.sleep(0.4)

        # 7. Regain inventory focus and reset to top
        self.engine.activate_scroll_with_double_click(roi)
        time.sleep(0.3)
        self.engine.scroll_to_top(activate_first=False)
        time.sleep(0.35)

        self.log(f"=== CORROSION FLOW COMPLETE (Restored Cube to Synthesis) ===", "success")
        return loaded

    def click_synth_button(self):
        """
        Clicks the Synthesize button.
        Supports:
        1. Calibrated Area (ROI): searches within that region or clicks center of area.
        2. Calibrated Point: clicks the user-specified (X, Y) point directly.
        3. Template Matching fallback: searches screen for synth_btn.png / cube_synth_btn.png.
        """
        sx = None
        sy = None

        synth_roi = self.config.get("rois", {}).get("synth_btn") or self.config.get("rois", {}).get("cube_synth_btn")
        synth_pt = self.config.get("button_coords", {}).get("cube_synth_btn") or self.config.get("button_coords", {}).get("synth_btn")

        # 1. If an Area / ROI was calibrated for the synthesis button
        if synth_roi and synth_roi.get("width", 0) > 10 and synth_roi.get("height", 0) > 10:
            rx, ry = int(synth_roi["x"]), int(synth_roi["y"])
            rw, rh = int(synth_roi["width"]), int(synth_roi["height"])

            # Check if template matches within the calibrated area
            area_crop = self.vision.capture_screen(synth_roi)
            match = None
            for tmpl_name in ["synth_btn.png", "cube_synth_btn.png"]:
                if self.vision.template_exists(tmpl_name):
                    match = self.vision.find_template(area_crop, tmpl_name, threshold=0.65)
                    if match:
                        break

            if match:
                sx = rx + match[0] + match[2] // 2
                sy = ry + match[1] + match[3] // 2
                self.log(f"Found Synthesize button within calibrated area at ({sx}, {sy})...", "info")
            else:
                sx = rx + rw // 2
                sy = ry + rh // 2
                self.log(f"Clicking center of calibrated Synthesize area at ({sx}, {sy})...", "info")

        # 2. If a Point was calibrated for the synthesis button
        elif synth_pt and "x" in synth_pt and "y" in synth_pt and int(synth_pt["x"]) > 0:
            sx = int(synth_pt["x"])
            sy = int(synth_pt["y"])
            self.log(f"Clicking calibrated Synthesize button point at ({sx}, {sy})...", "info")

        # 3. Fallback: Full screen template search
        if sx is None or sy is None:
            screen = self.vision.capture_screen()
            match = self.vision.find_template(screen, "synth_btn.png", threshold=0.70)
            if not match:
                match = self.vision.find_template(screen, "cube_synth_btn.png", threshold=0.70)
            if match:
                sx = match[0] + match[2] // 2
                sy = match[1] + match[3] // 2
                self.log(f"Found Synthesize button on screen at ({sx}, {sy})...", "info")

        if sx is not None and sy is not None:
            self.engine.click_point(sx, sy, delay_after=0.4)
        else:
            self.log("Synthesize button could not be located on screen. Please calibrate using 'Select Point / Area'.", "warning")

        # Check for confirmation prompt (synth_confirm.png)
        time.sleep(0.3)
        screen_confirm = self.vision.capture_screen()
        c_match = self.vision.find_template(screen_confirm, "synth_confirm.png", threshold=0.70)
        if c_match:
            cx = c_match[0] + c_match[2] // 2
            cy = c_match[1] + c_match[3] // 2
            self.log(f"Found synthesis confirmation prompt: clicking at ({cx}, {cy})...", "info")
            self.engine.click_point(cx, cy, delay_after=0.3)

    def click_synth_return_button(self) -> bool:
        """
        Clicks the return/retrieve button (with curved arrow) located above Auto Input in the synthesis section.
        Retrieves or returns synthesized gear to inventory.
        """
        if self.abort_requested:
            return False

        screen = self.vision.capture_screen()
        match = self.vision.find_template(screen, "synth_return_btn.png", threshold=0.70)
        if not match:
            match = self.vision.find_template(screen, "synth_return_full.png", threshold=0.68)

        if match:
            rx = match[0] + match[2] // 2
            ry = match[1] + match[3] // 2
            self.log(f"Clicking button above Auto Input (Synthesis Return) at ({rx}, {ry})...", "info")
            self.engine.click_point(rx, ry, delay_after=0.35)
            return True
        else:
            btn_cfg = self.config.get("button_coords", {}).get("synth_return_btn")
            if btn_cfg and "x" in btn_cfg and "y" in btn_cfg:
                rx, ry = int(btn_cfg["x"]), int(btn_cfg["y"])
                self.log(f"Clicking button above Auto Input via configured coords at ({rx}, {ry})...", "info")
                self.engine.click_point(rx, ry, delay_after=0.35)
                return True
            else:
                synth_cfg = self.config.get("button_coords", {}).get("cube_synth_btn", {"x": 520, "y": 510})
                rx = int(synth_cfg["x"]) - 95
                ry = int(synth_cfg["y"]) - 50
                self.log(f"Clicking button above Auto Input via geometric fallback at ({rx}, {ry})...", "info")
                self.engine.click_point(rx, ry, delay_after=0.35)
                return True

    def execute_synthesis_flow(
        self,
        target_bracket: str,
        target_rarity: str,
        inv_roi: Dict[str, int],
        is_full_inv: bool = False
    ) -> bool:
        """
        Executes synthesis flow for a specific target recipe (bracket + rarity):
        1. Selects Cube Dropdown Tier (Lv.65~80 or Lv.80~90)
        2. Regains inventory focus via 2x left-click on slot (0,0)
        3. Scrolls to top of inventory
        4. Loads 9 matching items via ALT+RIGHT-CLICK (re-scanning after each click)
        5. If is_full_inv and full_inventory_anticipation: transfers slot (0,0) to Stash to free 1 slot
        6. Clicks Synthesize button (synth_btn.png)
        7. Waits 1.5s for synthesis animation
        8. Clicks Return button above Auto Input (synth_return_btn.png)
        9. If stashed: returns item from Stash back to slot (0,0)
        Returns True if 9 items were loaded and synthesized successfully.
        """
        tier_label = "Lv.80~90" if target_bracket == "80_90" else "Lv.65~80"
        self.set_status(f"Synthesizing {tier_label} ({target_rarity})")
        self.log(f"Starting Cube Synthesis: Tier {tier_label} | Rarity: {target_rarity}", "info")

        # 1. Select Cube Level Tier Dropdown
        self.select_cube_tier(target_bracket)
        time.sleep(0.4)

        # 2. Regain focus on inventory via 2x left-click on slot (0,0)
        self.log("Regaining inventory focus after tier selection: 2x left-click on slot (0,0)...", "info")
        self.engine.activate_scroll_with_double_click(inv_roi)
        time.sleep(0.3)

        # 3. Scroll to top of inventory
        self.log("Resetting inventory to top before loading items...", "info")
        self.engine.scroll_to_top(activate_first=False)
        time.sleep(0.4)

        # 4. Load 9 items via ALT+RIGHT-CLICK
        loaded = 0
        grid_cfg = self.config.get("grid_settings", {})
        max_steps = int(grid_cfg.get("max_scroll_steps", 20))
        scroll_ticks = int(grid_cfg.get("scroll_ticks_per_step", 1))

        for step in range(max_steps):
            if loaded >= 9 or self.abort_requested:
                break

            visible_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
            matching = [
                itm for itm in visible_items
                if itm["bracket"] == target_bracket and itm["rarity"] == target_rarity
            ]

            while matching and loaded < 9 and not self.abort_requested:
                first_match = matching[0]
                cx = first_match["click_x"]
                cy = first_match["click_y"]

                self.engine.alt_right_click(cx, cy, jitter=2, delay_after=0.25)
                loaded += 1
                g_info = f"Lv.{first_match.get('level', first_match['bracket'])} {first_match.get('gear_name', 'item')}"
                self.log(f"Loaded item #{loaded}/9 ({g_info}, {first_match['rarity']}) into Cube via ALT+RIGHT-CLICK at ({cx}, {cy})", "info")

                time.sleep(0.18)
                visible_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
                matching = [
                    itm for itm in visible_items
                    if itm["bracket"] == target_bracket and itm["rarity"] == target_rarity
                ]

            if loaded < 9 and not self.abort_requested:
                self.log(f"Loaded {loaded}/9 items. Scrolling down (step {step + 1}/{max_steps})...", "info")
                moved, at_bottom, diff = self.engine.scroll_inventory_down(scroll_ticks)
                time.sleep(0.4)
                if at_bottom:
                    visible_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
                    matching = [
                        itm for itm in visible_items
                        if itm["bracket"] == target_bracket and itm["rarity"] == target_rarity
                    ]
                    while matching and loaded < 9 and not self.abort_requested:
                        first_match = matching[0]
                        cx = first_match["click_x"]
                        cy = first_match["click_y"]
                        self.engine.alt_right_click(cx, cy, jitter=2, delay_after=0.25)
                        loaded += 1
                        g_info = f"Lv.{first_match.get('level', first_match['bracket'])} {first_match.get('gear_name', 'item')}"
                        self.log(f"Loaded item #{loaded}/9 at bottom ({g_info}, {first_match['rarity']}) into Cube via ALT+RIGHT-CLICK at ({cx}, {cy})", "info")
                        time.sleep(0.18)
                        visible_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
                        matching = [
                            itm for itm in visible_items
                            if itm["bracket"] == target_bracket and itm["rarity"] == target_rarity
                        ]
                    break

        auto_press = self.config.get("auto_press_synth_btn", True)
        if loaded >= 9 and not self.abort_requested:
            if auto_press:
                # -------------------------------------------------------------
                # Stash Slot Transfer for Full Inventory (Optional Anticipation):
                # If enabled and inventory was full, transfers slot (0,0) -> Stash Slot
                # before clicking Synthesize to ensure the game allows synthesis.
                # If disabled, synthesizes directly on full inventory.
                # -------------------------------------------------------------
                stashed_item = False
                stash_pt = self.config.get("button_coords", {}).get("stash_slot")
                anticipate_full = self.config.get("full_inventory_anticipation", False)

                if is_full_inv and anticipate_full:
                    if stash_pt and "x" in stash_pt and "y" in stash_pt:
                        stash_x = int(stash_pt["x"])
                        stash_y = int(stash_pt["y"])
                        slot_0_x = int(inv_roi["x"] + 22)
                        slot_0_y = int(inv_roi["y"] + 22)

                        # Ensure inventory is scrolled to top so slot (0,0) is visible
                        self.log("Inventory was full (anticipation enabled): scrolling to top to access slot (0,0)...", "info")
                        self.engine.scroll_to_top(activate_first=False)
                        time.sleep(0.3)

                        self.log(f"Transferring slot (0,0) -> Stash at ({stash_x}, {stash_y}) to free 1 slot...", "info")
                        stashed_item = self.engine.drag_and_drop(slot_0_x, slot_0_y, stash_x, stash_y)
                        time.sleep(0.35)
                    else:
                        self.log("Warning: Inventory is FULL and anticipation is enabled, but Stash Slot is not calibrated!", "warning")
                elif is_full_inv and not anticipate_full:
                    self.log("Inventory was full: Full inventory anticipation is disabled, proceeding to synthesize directly.", "info")

                self.log("All 9 items loaded. Clicking Synthesize button...", "info")
                self.click_synth_button()
                time.sleep(1.5)  # Wait 1500ms for animation

                # Click button above Auto Input (Synthesis Return)
                self.log("Clicking button above Auto Input (Synthesis Return)...", "info")
                self.click_synth_return_button()
                time.sleep(0.35)

                if hasattr(self.engine, "telegram"):
                    self.engine.telegram.notify_synthesis(
                        rarity=target_rarity,
                        count=loaded,
                        tier="80~90" if target_bracket == "80_90" else "65~80"
                    )

                # Return the stashed item back from stash to inventory:
                # 1. Sort inventory (frees up empty space at the bottom of inventory)
                # 2. Scroll to bottom so the real empty slots are visible
                # 3. Pick item from Stash and drop into the LAST slot of inventory (col 5, row 3)
                # 4. Sort inventory again to place the returned item in its proper sorted position
                if stashed_item and stash_pt:
                    self.log("Step 1/4: Sorting inventory after synthesis to pack items and free bottom slots...", "info")
                    self.engine.click_inventory_sort_button()
                    time.sleep(0.4)

                    self.log("Regaining inventory focus after sort: 2x left-click on slot (0,0)...", "info")
                    self.engine.activate_scroll_with_double_click(inv_roi)
                    time.sleep(0.3)

                    self.log("Step 2/4: Scrolling inventory to bottom to reach empty slots...", "info")
                    self.engine.scroll_to_bottom(activate_first=False)
                    time.sleep(0.35)

                    # The 7th column (col 6) is the '+' DLC purchase button.
                    # The real last inventory slot is the 6th column (col 5, bottom row):
                    col_w = inv_roi["width"] / 7.0
                    row_h = inv_roi["height"] / 4.0
                    last_slot_x = int(inv_roi["x"] + col_w * 5.5)
                    last_slot_y = int(inv_roi["y"] + row_h * 3.5)
                    self.log(f"Step 3/4: Returning temporary item from Stash ({stash_x}, {stash_y}) -> Last inventory slot (col 5, row 3, left of DLC button) at ({last_slot_x}, {last_slot_y})...", "info")
                    self.engine.drag_and_drop(stash_x, stash_y, last_slot_x, last_slot_y)
                    time.sleep(0.4)

                    self.log("Step 4/4: Sorting inventory again to organize the returned item...", "info")
                    self.engine.click_inventory_sort_button()
                    time.sleep(0.4)
                    self.log("Stash item returned and inventory organized successfully.", "info")

                # Deduct 9 items from bucket
                cur = self.engine.live_buckets.get(target_bracket, {}).get(target_rarity, 9)
                self.engine.live_buckets[target_bracket][target_rarity] = max(0, cur - 9)
                self.engine._sync_and_publish_counts({(target_bracket, target_rarity): max(0, cur - 9)})
                self.log("Synthesis & return complete! 8 inventory slots freed.", "info")
                return True
            else:
                self.log("All 9 items loaded into Cube via ALT+RIGHT-CLICK. Pausing without clicking Synthesize button (auto_press_synth_btn=False).", "info")
                self.set_status("Loaded 9 Gears - Review Ready")
                return False
        else:
            self.log(f"Warning: Only loaded {loaded}/9 items. Aborting synthesis.", "warning")
            return False

    def test_stash_transfer(self) -> bool:
        """
        Tests the temporary stash transfer:
        1. Drags item from inventory slot (0,0) to Stash Slot.
        2. Waits 0.5s.
        3. Drags item from Stash Slot back to inventory slot (0,0).
        """
        self.engine.reset_abort_state()
        inv_roi = self.vision.get_inventory_roi()
        stash_pt = self.config.get("button_coords", {}).get("stash_slot")
        if not stash_pt or "x" not in stash_pt or "y" not in stash_pt:
            self.log("Cannot test stash transfer: Stash Slot not calibrated! Please calibrate Stash Slot first.", "warning")
            return False

        stash_x = int(stash_pt["x"])
        stash_y = int(stash_pt["y"])
        slot_0_x = int(inv_roi["x"] + 22)
        slot_0_y = int(inv_roi["y"] + 22)

        self.log("--- Starting Stash Transfer Test ---", "info")
        self.log("Step 1: Scrolling to top of inventory...", "info")
        self.engine.scroll_to_top(activate_first=False)
        time.sleep(0.3)

        self.log(f"Step 2: Moving item from slot (0,0) at ({slot_0_x}, {slot_0_y}) -> Stash at ({stash_x}, {stash_y})...", "info")
        ok1 = self.engine.drag_and_drop(slot_0_x, slot_0_y, stash_x, stash_y)
        if not ok1:
            self.log("Step 2 failed: Could not transfer item to Stash.", "warning")
            return False

        time.sleep(0.6)

        self.log("Step 3/5: Sorting inventory to free bottom slots...", "info")
        self.engine.click_inventory_sort_button()
        time.sleep(0.4)

        self.log("Regaining inventory focus after sort: 2x left-click on slot (0,0)...", "info")
        self.engine.activate_scroll_with_double_click(inv_roi)
        time.sleep(0.3)

        self.log("Step 4/5: Scrolling inventory to bottom to reach empty slots...", "info")
        self.engine.scroll_to_bottom(activate_first=False)
        time.sleep(0.35)

        # The 7th column (col 6) is the '+' DLC purchase button.
        # The real last inventory slot is the 6th column (col 5, bottom row):
        col_w = inv_roi["width"] / 7.0
        row_h = inv_roi["height"] / 4.0
        last_slot_x = int(inv_roi["x"] + col_w * 5.5)
        last_slot_y = int(inv_roi["y"] + row_h * 3.5)
        self.log(f"Step 5/5: Returning item from Stash at ({stash_x}, {stash_y}) -> Last inventory slot (col 5, row 3, left of DLC button) at ({last_slot_x}, {last_slot_y})...", "info")
        ok2 = self.engine.drag_and_drop(stash_x, stash_y, last_slot_x, last_slot_y)
        if ok2:
            time.sleep(0.4)
            self.log("Final Sort: Sorting inventory again to organize item...", "info")
            self.engine.click_inventory_sort_button()
            time.sleep(0.4)
            self.log("Stash transfer test completed successfully! Item moved to Stash, scrolled to bottom, returned to last slot, and re-sorted cleanly.", "info")
            return True
        else:
            self.log("Step 5 failed: Could not return item from Stash.", "warning")
            return False

    def test_synthesis_loading(self) -> Tuple[int, str, str]:
        """
        Tests functional synthesis loading and execution.
        """
        self.engine.reset_abort_state()
        self.log("--- Starting Synthesis Test ---", "info")
        inv_roi = self.vision.get_inventory_roi()
        self.engine.reload_config()
        self.vision.clear_cache()

        # Step 1: Ensure Cube & Inventory are open
        self.ensure_cube_and_inventory_open()
        time.sleep(0.3)

        # Step 2: Determine target bucket
        counts: Dict[Tuple[str, str], int] = {}
        for b in ["80_90", "65"]:
            for r in ["Common", "Uncommon", "Rare", "Legendary"]:
                counts[(b, r)] = self.engine.live_buckets.get(b, {}).get(r, 0)

        eligible = [(b, r, cnt) for (b, r), cnt in counts.items() if cnt >= 9]
        if not eligible:
            self.log("Live bucket data does not have 9+ items yet. Performing full inventory count scan (Pass 2A)...", "info")
            counts = self.engine.pass2a_count_inventory(inv_roi)
            eligible = [(b, r, cnt) for (b, r), cnt in counts.items() if cnt >= 9]

        if eligible:
            eligible.sort(key=lambda x: (1 if x[0] == "80_90" else 0, x[2]), reverse=True)
            target_bracket, target_rarity, best_count = eligible[0]
            tier_label = "Lv.80~90" if target_bracket == "80_90" else "Lv.65~80"
            self.log(f"System selected recipe: Tier {tier_label} | Rarity: {target_rarity} ({best_count} items available)", "info")
        else:
            best_pair, best_count = max(counts.items(), key=lambda x: x[1]) if counts else (("80_90", "Common"), 0)
            target_bracket, target_rarity = best_pair
            tier_label = "Lv.80~90" if target_bracket == "80_90" else "Lv.65~80"
            self.log(f"Notice: No recipe has 9+ items yet. Highest count is Tier {tier_label} ({target_rarity}) with {best_count} items. Proceeding with test...", "warning")

        self.set_status(f"Loading {tier_label} ({target_rarity})")

        # Step 3: Select Cube Level Tier Dropdown
        self.select_cube_tier(target_bracket)
        time.sleep(0.4)

        # Regain inventory focus after tier selection via 2x left-click on slot (0,0)
        self.log("Regaining inventory focus after tier selection: 2x left-click on slot (0,0)...", "info")
        self.engine.activate_scroll_with_double_click(inv_roi)
        time.sleep(0.3)

        # Step 4: Click Sort button -> 2x left-click -> scroll to top row
        self.log("Step 4: Clicking Sort button -> 2x left-click on slot (0,0) -> scroll to top...", "info")
        self.engine.click_inventory_sort_button()
        time.sleep(0.35)
        self.engine.activate_scroll_with_double_click(inv_roi)
        time.sleep(0.3)
        self.engine.scroll_to_top(activate_first=False)
        time.sleep(0.4)

        # Step 5: Load items using ALT+RIGHT-CLICK
        loaded = 0
        grid_cfg = self.config.get("grid_settings", {})
        max_steps = int(grid_cfg.get("max_scroll_steps", 20))
        scroll_ticks = int(grid_cfg.get("scroll_ticks_per_step", 1))

        for step in range(max_steps):
            if loaded >= 9 or self.abort_requested:
                break

            visible_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
            matching = [
                itm for itm in visible_items
                if itm["bracket"] == target_bracket and itm["rarity"] == target_rarity
            ]

            while matching and loaded < 9 and not self.abort_requested:
                first_match = matching[0]
                cx = first_match["click_x"]
                cy = first_match["click_y"]

                self.engine.alt_right_click(cx, cy, jitter=2, delay_after=0.25)
                loaded += 1
                g_info = f"Lv.{first_match.get('level', first_match['bracket'])} {first_match.get('gear_name', 'item')}"
                self.log(f"Loaded item #{loaded}/9 ({g_info}, {first_match['rarity']}) into Cube via ALT+RIGHT-CLICK at ({cx}, {cy})", "info")

                time.sleep(0.18)
                visible_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
                matching = [
                    itm for itm in visible_items
                    if itm["bracket"] == target_bracket and itm["rarity"] == target_rarity
                ]

            if loaded < 9 and not self.abort_requested:
                self.log(f"Loaded {loaded}/9 items. Scrolling down (step {step + 1}/{max_steps})...", "info")
                moved, at_bottom, diff = self.engine.scroll_inventory_down(scroll_ticks)
                time.sleep(0.4)
                if at_bottom:
                    visible_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
                    matching = [
                        itm for itm in visible_items
                        if itm["bracket"] == target_bracket and itm["rarity"] == target_rarity
                    ]
                    while matching and loaded < 9 and not self.abort_requested:
                        first_match = matching[0]
                        cx = first_match["click_x"]
                        cy = first_match["click_y"]
                        self.engine.alt_right_click(cx, cy, jitter=2, delay_after=0.25)
                        loaded += 1
                        g_info = f"Lv.{first_match.get('level', first_match['bracket'])} {first_match.get('gear_name', 'item')}"
                        self.log(f"Loaded item #{loaded}/9 at bottom ({g_info}, {first_match['rarity']}) into Cube via ALT+RIGHT-CLICK at ({cx}, {cy})", "info")
                        time.sleep(0.18)
                        visible_items = self.vision.scan_visible_inventory(inv_roi, min_y_offset=0)
                        matching = [
                            itm for itm in visible_items
                            if itm["bracket"] == target_bracket and itm["rarity"] == target_rarity
                        ]
                    break

        # Step 6: Synthesize button click
        auto_press = self.config.get("auto_press_synth_btn", True)
        if loaded >= 9:
            self.log(f"SUCCESS: Loaded all {loaded}/9 items into Cube via ALT+RIGHT-CLICK!", "info")
            if auto_press:
                self.log("Clicking Synthesize button (synth_btn.png)...", "info")
                self.click_synth_button()
                time.sleep(1.5)

                self.log("Clicking button above Auto Input (Synthesis Return)...", "info")
                self.click_synth_return_button()
                time.sleep(0.35)

                self.log("Synthesis & return button clicked successfully!", "info")
                self.set_status("Synthesis Complete")
            else:
                self.log("PAUSED: Stopping before pressing Synthesize button as auto_press_synth_btn is False.", "info")
                self.set_status("Loaded 9 Gears - Review Ready")
        else:
            self.log(f"Test Synthesis: Loaded {loaded}/9 items via ALT+RIGHT-CLICK.", "warning")
            self.set_status(f"Loaded {loaded}/9 Gears")

        return loaded, target_bracket, target_rarity

    # ---------------------------------------------------------
    # Stash Lv. 50 Synthesis Flow (from Stash 1)
    # ---------------------------------------------------------
    def execute_stash_lvl50_synthesis(self, rarity: str, items: List[Dict[str, Any]]) -> bool:
        """
        Executes synthesis of 9 Lv. 50 items directly from Stash 1:
        1. Selects Lv. 50 tier in Cube dropdown.
        2. Ensures Stash 1 tab is clicked / open.
        3. Loads 9 items into the Cube via Alt+Right Click on stash coordinates.
        4. Clicks Synthesize button.
        5. Clicks Synthesis Return button.
        """
        self.engine.reset_abort_state()
        if len(items) < 9:
            self.log(f"Cannot synthesize: only {len(items)}/9 Lv. 50 {rarity} items available in Stash 1.", "warning")
            return False

        self.log(f"--- Starting Stash Lv. 50 Synthesis ({rarity}) ---", "info")
        self.set_status(f"Synthesizing Lv.50 {rarity}")

        # Step 1: Select Lv. 50 tier on Cube
        self.log("Step 1/5: Selecting Lv.50 in Cube tier dropdown...", "info")
        self.select_cube_tier("50")
        time.sleep(0.35)

        # Step 2: Ensure Stash 1 is clicked / active
        btn_coords = self.config.get("button_coords", {})
        stash_1 = btn_coords.get("stash_tab_1")
        if stash_1 and "x" in stash_1 and "y" in stash_1:
            self.log(f"Step 2/5: Clicking Stash 1 tab at ({stash_1['x']}, {stash_1['y']})...", "info")
            self.engine.click_point(stash_1["x"], stash_1["y"], delay_after=0.3)
            time.sleep(0.35)

        # Step 3: Load exactly 9 items into Cube from Stash 1
        self.log(f"Step 3/5: Loading 9 Lv.50 {rarity} items into Cube from Stash 1 (Alt+Right Click)...", "info")
        loaded = 0
        for itm in items[:9]:
            if self.engine.abort_requested:
                break
            cx, cy = itm["click_x"], itm["click_y"]
            self.engine.alt_right_click(cx, cy, delay_after=0.22)
            loaded += 1
            time.sleep(0.18)

        if loaded < 9:
            self.log(f"Warning: Only loaded {loaded}/9 items into Cube. Aborting.", "warning")
            return False

        # Step 4: Click Synthesize button
        auto_synth = self.config.get("auto_press_synth_btn", True)
        if auto_synth:
            self.log("Step 4/5: All 9 Lv.50 items loaded. Clicking Synthesize button...", "info")
            self.click_synth_button()
            time.sleep(1.5)

            # Step 5: Click Synthesis Return button
            self.log("Step 5/5: Clicking button above Auto Input (Synthesis Return)...", "info")
            self.click_synth_return_button()
            time.sleep(0.35)
            self.log(f"Stash Lv.50 {rarity} Synthesis successfully completed!", "success")
            return True
        else:
            self.log("All 9 Lv.50 items loaded. Pausing without clicking Synthesize (auto_press_synth_btn=False).", "info")
            return False

    # ---------------------------------------------------------
    # Native Auto-Fill Synthesis Flow (Lv. 80~90)
    # ---------------------------------------------------------
    def click_auto_fill_button(self) -> bool:
        """
        Clicks the in-game 'Auto Fill' (Auto Input) button in the synthesis panel.
        Supports:
        1. Calibrated coordinates: button_coords['cube_auto_fill_btn'] or ['auto_fill_btn'].
        2. Template matching fallback: auto_fill_btn.png / auto_fill.png / auto_input_btn.png.
        3. Geometric fallback:
           - Directly below synth_return_btn: (rx, ry + 48).
           - To the left of cube_synth_btn: (sx - 95, sy).
        """
        if self.abort_requested:
            return False

        # 1. Calibrated coordinates
        btn_coords = self.config.get("button_coords", {})
        af_cfg = btn_coords.get("cube_auto_fill_btn") or btn_coords.get("auto_fill_btn")
        if af_cfg and "x" in af_cfg and "y" in af_cfg:
            ax, ay = int(af_cfg["x"]), int(af_cfg["y"])
            self.log(f"Clicking calibrated Auto Fill button at ({ax}, {ay})...", "info")
            self.engine.click_point(ax, ay, delay_after=0.35)
            return True

        # 2. Template search fallback
        screen = self.vision.capture_screen()
        for tname in ["auto_fill_btn.png", "auto_fill.png", "auto_input_btn.png"]:
            if self.vision.template_exists(tname):
                match = self.vision.find_template(screen, tname, threshold=0.70)
                if match:
                    ax = match[0] + match[2] // 2
                    ay = match[1] + match[3] // 2
                    self.log(f"Found Auto Fill button via template '{tname}' at ({ax}, {ay})...", "info")
                    self.engine.click_point(ax, ay, delay_after=0.35)
                    return True

        # 3. Geometric fallback relative to return button or synth button
        ret_match = self.vision.find_template(screen, "synth_return_btn.png", threshold=0.70)
        if not ret_match:
            ret_match = self.vision.find_template(screen, "synth_return_full.png", threshold=0.68)

        if ret_match:
            rx = ret_match[0] + ret_match[2] // 2
            ry = ret_match[1] + ret_match[3] // 2
            ax = rx
            ay = ry + 48
            self.log(f"Clicking Auto Fill button via return button offset at ({ax}, {ay})...", "info")
            self.engine.click_point(ax, ay, delay_after=0.35)
            return True

        # Fallback to cube_synth_btn offset
        synth_cfg = btn_coords.get("cube_synth_btn") or btn_coords.get("synth_btn", {"x": 1777, "y": 724})
        ax = int(synth_cfg.get("x", 1777)) - 95
        ay = int(synth_cfg.get("y", 724))
        self.log(f"Clicking Auto Fill button via geometric synth button offset at ({ax}, {ay})...", "info")
        self.engine.click_point(ax, ay, delay_after=0.35)
        return True

    def execute_autofill_synthesis_flow(self) -> bool:
        """
        Executes native Auto-Fill Synthesis flow for Lv. 80~90:
        Flow:
        1. Open synthesis with Lv. 80~90 (ensure synthesis mode + select tier).
        2. Click Auto Fill button.
        3. Press Synthesize button.
        4. Press button above auto to return the item (synth_return_btn).
        """
        self.engine.reset_abort_state()
        self.log("=== STARTING NATIVE AUTO-FILL SYNTHESIS FLOW (Lv.80~90) ===", "info")
        self.set_status("Auto-Fill Synthesis (Lv.80~90)")

        try:
            # Step 1: Ensure Cube is in Synthesis mode
            self.log("Step 1/5: Ensuring Cube is in Synthesis mode...", "info")
            self.switch_cube_mode("synthesis")
            time.sleep(0.3)

            if self.abort_requested:
                return False

            # Step 2: Select Lv.80~90 tier
            self.log("Step 2/5: Selecting Lv.80~90 tier...", "info")
            self.select_cube_tier("80_90")
            time.sleep(0.35)

            if self.abort_requested:
                return False

            # Step 3: Click Auto Fill button
            self.log("Step 3/5: Clicking Auto Fill button...", "info")
            self.click_auto_fill_button()
            time.sleep(0.5)

            if self.abort_requested:
                return False

            # Step 4: Click Synthesize button
            self.log("Step 4/5: Clicking Synthesize button...", "info")
            self.click_synth_button()
            time.sleep(1.5)

            if self.abort_requested:
                return False

            # Step 5: Click button above Auto Fill (Synthesis Return)
            self.log("Step 5/5: Clicking button above Auto Fill (Synthesis Return)...", "info")
            self.click_synth_return_button()
            time.sleep(0.35)

            self.log("=== AUTO-FILL SYNTHESIS COMPLETED SUCCESSFULLY ===", "success")
            self.set_status("Auto-Fill Synth Complete")

            if hasattr(self.engine, "telegram") and self.engine.telegram:
                self.engine.telegram.notify_synthesis("AutoFill", 9, tier="80~90")

            return True
        except Exception as e:
            self.log(f"Error during Auto-Fill Synthesis: {e}", "error")
            return False
