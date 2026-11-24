"""
Visual Debugger Image Overlay Renderer for Task Bar Hero.
Renders real-time visual annotations for inventory items, corner detectors, badges, and chests.
"""
import cv2
import numpy as np
from typing import Optional, Dict, Tuple, Any
from .screen import ScreenCapture
from .chest_detector import ChestDetector
from .gear_detector import GearDetector


class OverlayRenderer:
    def __init__(
        self,
        chest_detector: ChestDetector,
        gear_detector: GearDetector,
        material_detector: Optional[Any] = None,
        corrosion_detector: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.chest_detector = chest_detector
        self.gear_detector = gear_detector
        self.material_detector = material_detector
        self.corrosion_detector = corrosion_detector
        self.config = config or {}

    def update_config(self, config_data: Dict[str, Any]):
        self.config = config_data

    def render_debug_overlay(
        self,
        inv_roi: Optional[Dict[str, int]] = None,
        chest_roi: Optional[Dict[str, int]] = None,
        mode: str = "full",
        show_gears: bool = True,
        show_materials: bool = True,
        show_corrosion: bool = True,
        show_lvl50: bool = True,
        **kwargs
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Renders live annotated visualization image with colored boxes:
        Green = Uncommon, Blue = Rare, Orange = Legendary, Gray = Common.
        Modes: 'full', 'inventory', 'materials', 'corrosion', 'chest'.
        """
        iroi = inv_roi or self.gear_detector.get_inventory_roi()
        croi = chest_roi or self.config.get("rois", {}).get("chest_region", {"x": 300, "y": 450, "width": 120, "height": 120})

        full_screen = ScreenCapture.capture_screen()
        h_screen, w_screen = full_screen.shape[:2]

        ix, iy, iw, ih = iroi["x"], iroi["y"], iroi["width"], iroi["height"]
        inv_crop = full_screen[max(0, iy):min(h_screen, iy + ih), max(0, ix):min(w_screen, ix + iw)].copy()

        # 1. Gear Detection
        items = []
        if (show_gears and mode != "chest" and mode != "materials" and mode != "corrosion") or mode == "inventory":
            items = self.gear_detector.scan_visible_inventory(iroi, roi_img=inv_crop)

        # 2. Materials Detection
        materials = []
        if (show_materials or mode == "materials") and self.material_detector and hasattr(self.material_detector, "scan_visible_materials"):
            try:
                materials = self.material_detector.scan_visible_materials(iroi, roi_img=inv_crop)
            except Exception:
                materials = []

        # 3. Corrosion Materials Detection
        corrosion_items = []
        if (show_corrosion or mode == "corrosion") and self.corrosion_detector and hasattr(self.corrosion_detector, "scan_visible_corrosion_materials"):
            try:
                corrosion_items = self.corrosion_detector.scan_visible_corrosion_materials(iroi, roi_img=inv_crop)
            except Exception:
                corrosion_items = []

        # 4. Low Level (Lv. 50) Items Detection
        lvl50_items = []
        if (show_lvl50 or mode == "lvl50"):
            try:
                lvl50_items = self.gear_detector.scan_visible_inventory(iroi, roi_img=inv_crop, level_filter="50")
            except Exception:
                lvl50_items = []

        chest_state = self.chest_detector.detect_chest_state(croi)

        rarity_colors = {
            "Common": (170, 170, 170),
            "Uncommon": (50, 205, 50),     # Green
            "Rare": (255, 144, 30),        # Blue
            "Legendary": (0, 165, 255),    # Orange/Gold
            "Immortal": (0, 0, 230)        # Crimson/Red
        }

        stats = {
            "total_items": len(items),
            "tier_50": sum(1 for itm in items if itm.get("bracket") == "50"),
            "tier_65": sum(1 for itm in items if itm.get("bracket") == "65"),
            "tier_80_90": sum(1 for itm in items if itm.get("bracket") == "80_90"),
            "rarity_counts": {
                r: sum(1 for itm in items if itm.get("rarity") == r)
                for r in ["Common", "Uncommon", "Rare", "Legendary"]
            },
            "chest_found": chest_state["chest_found"],
            "empty_found": chest_state["empty_found"],
            "inv_full_found": chest_state.get("inv_full_found", False),
            "chest_type": chest_state.get("chest_type"),
            "chest_status": chest_state.get(
                "status_str",
                "CHEST FOUND" if chest_state["chest_found"] else (
                    "EMPTY FLOOR CONFIRMED" if chest_state["empty_found"] else "UNVERIFIED"
                )
            ),
            "ref_stats": self.gear_detector.get_reference_library_stats(),
            "items": items,
            "materials": materials,
            "corrosion_items": corrosion_items,
            "lvl50_items": lvl50_items
        }

        # ---------------------------------------------------------
        # MODE: Inventory / Materials / Corrosion / Lv. 50 (Zoomed 2x Crop)
        # ---------------------------------------------------------
        if mode in ("inventory", "materials", "corrosion", "lvl50"):
            ch_h, ch_w = inv_crop.shape[:2]
            if iw > 0 and ih > 0:
                crop = cv2.resize(inv_crop, (ch_w * 2, ch_h * 2), interpolation=cv2.INTER_LINEAR)
            else:
                crop = inv_crop.copy()
            c2_h, c2_w = crop.shape[:2]

            # A. Draw Gears
            if show_gears and mode not in ("materials", "corrosion", "lvl50"):
                for itm in items:
                    sx, sy, sw, sh = [int(v * 2) for v in itm["slot_box"]]
                    col = rarity_colors.get(itm.get("rarity"), (170, 170, 170))
                    x1 = max(0, min(c2_w - 1, sx))
                    y1 = max(0, min(c2_h - 1, sy))
                    x2 = max(0, min(c2_w - 1, sx + sw))
                    y2 = max(0, min(c2_h - 1, sy + sh))
                    cv2.rectangle(crop, (x1, y1), (x2, y2), col, 2)

                    # Draw badge indicator box (scaled 2x)
                    bx, by, bw, bh = [int(v * 2) for v in itm.get("badge_pos", (0, 0, 0, 0))]
                    if bw > 0 and bh > 0:
                        cv2.rectangle(crop, (bx, by), (bx + bw, by + bh), (0, 255, 255), 1)

                    # Draw 3 corner detectors
                    if self.config.get("multi_corner_rarity_enabled", False):
                        c_size = max(4, int(self.config.get("corner_detector_size", 10))) * 2
                        c_boxes = [
                            (sx + 2, sy + 2, c_size, c_size),
                            (max(0, sx + sw - c_size - 2), sy + 2, c_size, c_size),
                            (sx + 2, max(0, sy + sh - c_size - 2), c_size, c_size)
                        ]
                        for cbx, cby, cbw, cbh in c_boxes:
                            cv2.rectangle(crop, (cbx, cby), (cbx + cbw, cby + cbh), (255, 0, 255), 1)

                    gear_name = itm.get("gear_name")
                    lv_val = itm.get("level", itm.get("bracket", ""))
                    score_pct = int(itm.get("score", 1.0) * 100)
                    g_short = (gear_name or itm.get("rarity", "item"))[:4].lower()
                    lbl = f"{lv_val}-{g_short} {score_pct}%"

                    tx = max(4, sx + 2)
                    ty = max(18, sy - 6)
                    cv2.putText(crop, lbl, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 0), 2, cv2.LINE_AA)
                    cv2.putText(crop, lbl, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1, cv2.LINE_AA)
                    cv2.drawMarker(crop, (sx + sw // 2, sy + sh // 2), col, cv2.MARKER_CROSS, 10, 1)

            # B. Draw Materials (SS_materials)
            if show_materials or mode == "materials":
                for mat in materials:
                    mx = int(mat.get("slot_x", 0) * 2)
                    my = int(mat.get("slot_y", 0) * 2)
                    mw = int(mat.get("slot_w", 30) * 2)
                    mh = int(mat.get("slot_h", 30) * 2)
                    m_rarity = mat.get("rarity", "Common")
                    m_col = rarity_colors.get(m_rarity, (0, 230, 255))

                    cv2.rectangle(crop, (mx, my), (mx + mw, my + mh), m_col, 2)
                    cv2.drawMarker(crop, (mx + mw // 2, my + mh // 2), m_col, cv2.MARKER_CROSS, 12, 2)

                    m_lbl = f"MAT: {mat.get('name', 'Material')} {int(mat.get('score', 1.0)*100)}%"
                    label_w = len(m_lbl) * 7 + 4
                    cv2.rectangle(crop, (mx, max(0, my - 16)), (mx + label_w, my), (15, 18, 28), -1)
                    cv2.putText(crop, m_lbl, (mx + 2, max(12, my - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, m_col, 1, cv2.LINE_AA)

            # C. Draw Corrosion Materials (SS_corrosion)
            if show_corrosion or mode == "corrosion":
                for cmat in corrosion_items:
                    cx = int(cmat.get("slot_x", 0) * 2)
                    cy = int(cmat.get("slot_y", 0) * 2)
                    cw = int(cmat.get("slot_w", 30) * 2)
                    ch = int(cmat.get("slot_h", 30) * 2)
                    corr_col = (255, 0, 255)  # Bright Magenta / Neon Purple

                    cv2.rectangle(crop, (cx, cy), (cx + cw, cy + ch), corr_col, 2)
                    cv2.drawMarker(crop, (cx + cw // 2, cy + ch // 2), (0, 255, 255), cv2.MARKER_CROSS, 14, 2)

                    c_col_pct = int(cmat.get("color_score", 1.0) * 100)
                    c_lbl = f"CORR: {cmat.get('name', 'Corrosion')} {int(cmat.get('score', 1.0)*100)}% (C:{c_col_pct}%)"
                    label_w = len(c_lbl) * 7 + 6
                    cv2.rectangle(crop, (cx, max(0, cy - 16)), (cx + label_w, cy), (20, 10, 30), -1)
                    cv2.putText(crop, c_lbl, (cx + 2, max(12, cy - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 120, 255), 1, cv2.LINE_AA)

            # D. Draw Lv. 50 Items (SS/)
            if show_lvl50 or mode == "lvl50":
                for litm in lvl50_items:
                    lx = int(litm.get("slot_x", 0) * 2)
                    ly = int(litm.get("slot_y", 0) * 2)
                    lw = int(litm.get("slot_w", 30) * 2)
                    lh = int(litm.get("slot_h", 30) * 2)
                    l_rarity = litm.get("rarity", "Common")
                    l_col = rarity_colors.get(l_rarity, (0, 200, 255))

                    cv2.rectangle(crop, (lx, ly), (lx + lw, ly + lh), l_col, 2)
                    cv2.drawMarker(crop, (lx + lw // 2, ly + lh // 2), (255, 255, 0), cv2.MARKER_TILTED_CROSS, 14, 2)

                    l_lbl = f"LV50: {litm.get('name', 'Gear')} ({l_rarity}) {int(litm.get('score', 1.0)*100)}%"
                    label_w = len(l_lbl) * 7 + 6
                    cv2.rectangle(crop, (lx, max(0, ly - 16)), (lx + label_w, ly), (25, 20, 15), -1)
                    cv2.putText(crop, l_lbl, (lx + 2, max(12, ly - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, l_col, 1, cv2.LINE_AA)

            return crop, stats

        if mode == "chest":
            cx, cy, cw, ch = croi["x"], croi["y"], croi["width"], croi["height"]
            crop = full_screen[max(0, cy):min(h_screen, cy + ch), max(0, cx):min(w_screen, cx + cw)].copy()
            if chest_state.get("inv_full_found"):
                c_col = (0, 0, 255)  # Red for Inven Full
            elif chest_state["chest_found"]:
                c_col = (0, 255, 255)  # Yellow for Available Chest
            elif chest_state["empty_found"]:
                c_col = (50, 205, 50)  # Green for Empty Floor
            else:
                c_col = (0, 100, 255)
            cv2.rectangle(crop, (2, 2), (cw - 3, ch - 3), c_col, 2)
            cv2.putText(crop, stats["chest_status"], (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42, c_col, 1)
            if chest_state["chest_pos"]:
                local_x = chest_state["chest_pos"][0] - cx
                local_y = chest_state["chest_pos"][1] - cy
                cv2.drawMarker(crop, (local_x, local_y), (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
            if cw > 0 and ch > 0:
                crop = cv2.resize(crop, (cw * 3, ch * 3), interpolation=cv2.INTER_LINEAR)
            return crop, stats

        # Default 'full' mode
        annotated = full_screen.copy()

        # Draw inventory ROI
        cv2.rectangle(annotated, (ix, iy), (ix + iw, iy + ih), (255, 255, 0), 2)
        cv2.putText(annotated, "INVENTORY GRID", (ix, max(16, iy - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        # Draw detected gear items (if show_gears enabled)
        if show_gears:
            for itm in items:
                col = rarity_colors.get(itm.get("rarity"), (170, 170, 170))
                gx = itm["click_x"] - 21
                gy = itm["click_y"] - 21
                cv2.rectangle(annotated, (gx, gy), (gx + 42, gy + 42), col, 2)

                bx, by, bw, bh = itm.get("badge_pos", (0, 0, 0, 0))
                if bw > 0 and bh > 0:
                    cv2.rectangle(annotated, (ix + bx, iy + by), (ix + bx + bw, iy + by + bh), (0, 255, 255), 1)

                if self.config.get("multi_corner_rarity_enabled", False):
                    c_size = max(4, int(self.config.get("corner_detector_size", 10)))
                    c_boxes = [
                        (gx + 1, gy + 1, c_size, c_size),
                        (gx + 42 - c_size - 1, gy + 1, c_size, c_size),
                        (gx + 1, gy + 42 - c_size - 1, c_size, c_size)
                    ]
                    for cbx, cby, cbw, cbh in c_boxes:
                        cv2.rectangle(annotated, (cbx, cby), (cbx + cbw, cby + cbh), (255, 0, 255), 1)

                gear_name = itm.get("gear_name")
                lv_val = itm.get("level", itm.get("bracket", ""))
                score_pct = int(itm.get("score", 1.0) * 100)
                g_short = (gear_name or itm.get("rarity", "item"))[:4].lower()
                lbl = f"{lv_val}-{g_short} {score_pct}%"

                tx = max(2, gx)
                ty = max(12, gy - 4)
                cv2.putText(annotated, lbl, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 2, cv2.LINE_AA)
                cv2.putText(annotated, lbl, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.drawMarker(annotated, (itm["click_x"], itm["click_y"]), col, cv2.MARKER_CROSS, 8, 1)

        # Draw detected materials (if show_materials enabled)
        if show_materials:
            for mat in materials:
                gx = mat["click_x"] - 16
                gy = mat["click_y"] - 16
                m_col = rarity_colors.get(mat.get("rarity"), (0, 230, 255))
                cv2.rectangle(annotated, (gx, gy), (gx + 32, gy + 32), m_col, 2)
                cv2.drawMarker(annotated, (mat["click_x"], mat["click_y"]), m_col, cv2.MARKER_CROSS, 10, 2)
                m_lbl = f"MAT: {mat.get('name')} {int(mat.get('score', 1.0)*100)}%"
                cv2.putText(annotated, m_lbl, (gx, max(12, gy - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.34, m_col, 1, cv2.LINE_AA)

        # Draw detected corrosion materials (if show_corrosion enabled)
        if show_corrosion:
            for cmat in corrosion_items:
                gx = cmat["click_x"] - 16
                gy = cmat["click_y"] - 16
                corr_col = (255, 0, 255)
                cv2.rectangle(annotated, (gx, gy), (gx + 32, gy + 32), corr_col, 2)
                cv2.drawMarker(annotated, (cmat["click_x"], cmat["click_y"]), (0, 255, 255), cv2.MARKER_CROSS, 12, 2)
                c_lbl = f"CORR: {cmat.get('name')} {int(cmat.get('score', 1.0)*100)}%"
                cv2.putText(annotated, c_lbl, (gx, max(12, gy - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.34, corr_col, 1, cv2.LINE_AA)

        # Draw chest ROI
        cx, cy, cw, ch = croi["x"], croi["y"], croi["width"], croi["height"]
        if chest_state.get("inv_full_found"):
            c_col = (0, 0, 255)
        elif chest_state["chest_found"]:
            c_col = (0, 255, 255)
        elif chest_state["empty_found"]:
            c_col = (50, 205, 50)
        else:
            c_col = (0, 100, 255)
        cv2.rectangle(annotated, (cx, cy), (cx + cw, cy + ch), c_col, 2)
        cv2.putText(annotated, f"CHEST: {stats['chest_status']}", (cx, max(16, cy - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, c_col, 1)
        if chest_state["chest_pos"]:
            cv2.drawMarker(annotated, chest_state["chest_pos"], (0, 0, 255), cv2.MARKER_CROSS, 16, 2)

        # Draw calibrated Synthesis Button (Area or Point)
        synth_roi = self.config.get("rois", {}).get("synth_btn") or self.config.get("rois", {}).get("cube_synth_btn")
        synth_pt = self.config.get("button_coords", {}).get("cube_synth_btn") or self.config.get("button_coords", {}).get("synth_btn")
        magenta = (255, 0, 255)

        if synth_roi and synth_roi.get("width", 0) > 10 and synth_roi.get("height", 0) > 10:
            rx, ry = int(synth_roi["x"]), int(synth_roi["y"])
            rw, rh = int(synth_roi["width"]), int(synth_roi["height"])
            cv2.rectangle(annotated, (rx, ry), (rx + rw, ry + rh), magenta, 2)
            cv2.putText(annotated, f"SYNTH AREA ({rw}x{rh})", (rx, max(16, ry - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, magenta, 1)
            cv2.drawMarker(annotated, (rx + rw // 2, ry + rh // 2), magenta, cv2.MARKER_CROSS, 10, 1)
        elif synth_pt and "x" in synth_pt and "y" in synth_pt and int(synth_pt["x"]) > 0:
            px, py = int(synth_pt["x"]), int(synth_pt["y"])
            cv2.drawMarker(annotated, (px, py), magenta, cv2.MARKER_CROSS, 16, 2)
            cv2.putText(annotated, f"SYNTH PT ({px},{py})", (px + 10, py + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.42, magenta, 1)

        # Draw calibrated Stash Slot (Area or Point)
        stash_roi = self.config.get("rois", {}).get("stash_slot")
        stash_pt = self.config.get("button_coords", {}).get("stash_slot")
        cyan = (255, 255, 0)  # BGR Cyan

        if stash_roi and stash_roi.get("width", 0) > 10 and stash_roi.get("height", 0) > 10:
            sx, sy = int(stash_roi["x"]), int(stash_roi["y"])
            sw, sh = int(stash_roi["width"]), int(stash_roi["height"])
            cv2.rectangle(annotated, (sx, sy), (sx + sw, sy + sh), cyan, 2)
            cv2.putText(annotated, f"STASH SLOT ({sw}x{sh})", (sx, max(16, sy - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, cyan, 1)
            cv2.drawMarker(annotated, (sx + sw // 2, sy + sh // 2), cyan, cv2.MARKER_CROSS, 10, 1)
        elif stash_pt and "x" in stash_pt and "y" in stash_pt and int(stash_pt["x"]) > 0:
            px, py = int(stash_pt["x"]), int(stash_pt["y"])
            cv2.drawMarker(annotated, (px, py), cyan, cv2.MARKER_CROSS, 16, 2)
            cv2.putText(annotated, f"STASH ({px},{py})", (px + 10, py + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.42, cyan, 1)

        # Draw calibrated Cube Dropdown & Tier Points
        orange = (0, 165, 255)
        green = (0, 255, 128)
        drop_pt = self.config.get("button_coords", {}).get("cube_dropdown")
        if drop_pt and "x" in drop_pt and "y" in drop_pt and int(drop_pt["x"]) > 0:
            dx, dy = int(drop_pt["x"]), int(drop_pt["y"])
            cv2.drawMarker(annotated, (dx, dy), orange, cv2.MARKER_TRIANGLE_DOWN, 14, 2)
            cv2.putText(annotated, f"DROPDOWN ({dx},{dy})", (dx + 10, dy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.40, orange, 1)

        t80_pt = self.config.get("button_coords", {}).get("tier_80_90")
        if t80_pt and "x" in t80_pt and "y" in t80_pt and int(t80_pt["x"]) > 0:
            tx, ty = int(t80_pt["x"]), int(t80_pt["y"])
            cv2.drawMarker(annotated, (tx, ty), green, cv2.MARKER_CROSS, 12, 1)
            cv2.putText(annotated, f"Lv.80~90 ({tx},{ty})", (tx + 10, ty + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, green, 1)

        t65_pt = self.config.get("button_coords", {}).get("tier_65_80")
        if t65_pt and "x" in t65_pt and "y" in t65_pt and int(t65_pt["x"]) > 0:
            tx, ty = int(t65_pt["x"]), int(t65_pt["y"])
            cv2.drawMarker(annotated, (tx, ty), green, cv2.MARKER_CROSS, 12, 1)
            cv2.putText(annotated, f"Lv.65~80 ({tx},{ty})", (tx + 10, ty + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, green, 1)

        t50_pt = self.config.get("button_coords", {}).get("tier_50")
        if t50_pt and "x" in t50_pt and "y" in t50_pt and int(t50_pt["x"]) > 0:
            tx, ty = int(t50_pt["x"]), int(t50_pt["y"])
            cv2.drawMarker(annotated, (tx, ty), green, cv2.MARKER_CROSS, 12, 1)
            cv2.putText(annotated, f"Lv.50 ({tx},{ty})", (tx + 10, ty + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, green, 1)

        return annotated, stats
