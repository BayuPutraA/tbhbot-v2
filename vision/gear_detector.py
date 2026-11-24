"""
Gear & Inventory Item Detection Module for Task Bar Hero.
Provides:
- SS/ Reference Gear Library management and matching
- 3-Corner rarity border classification with Immortal Guard
- Precision level digit detection with tens-digit verification
- 3-Stage decoupled inventory scanning
- Scroll shift and inventory-at-bottom detection
"""
import os
import cv2
import numpy as np
from typing import Optional, List, Dict, Tuple, Any
from .template_matcher import TemplateMatcher
from .screen import ScreenCapture


class GearDetector:
    def __init__(
        self,
        matcher: TemplateMatcher,
        config: Optional[Dict[str, Any]] = None,
        assets_dir: str = "assets",
        ss_dir: str = "SS"
    ):
        self.matcher = matcher
        self.config = config or {}
        self.assets_dir = assets_dir
        self.ss_dir = ss_dir

        self._cached_digit_tmpls: Dict[str, np.ndarray] = {}
        self._ref_gear_library: List[Dict[str, Any]] = []
        self._ref_gear_by_level: Dict[str, List[Dict[str, Any]]] = {"50": [], "65": [], "80": [], "90": []}
        self._ref_gear_mtimes: Dict[str, float] = {}

        self.load_reference_gear_library()

    def update_config(self, config_data: Dict[str, Any]):
        """Update live configuration data."""
        self.config = config_data

    # ---------------------------------------------------------
    # SS/ Reference Gear Library Management
    # ---------------------------------------------------------
    def load_reference_gear_library(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        Loads all reference gear templates from ss_dir (default 'SS/').
        Standard filename format: <rarity_code>-<level>-<gear_name>.png
          rarity_code: 'c' (Common), 'u' (Uncommon), 'r' (Rare), 'l' (Legendary)
          level: '65' (bracket '65'), '80'/'90' (bracket '80_90')
          gear_name: descriptive name, e.g. 'armor', 'sword', 'helmet', 'gloves', etc.
        Pre-scales templates to 0.8x (optimal for standard 100% DPI game window where 50px matches 40px slot),
        and stores 1.0x as fallback.
        """
        if not os.path.isdir(self.ss_dir):
            return self._ref_gear_library

        rarity_map = {
            "c": "Common",
            "u": "Uncommon",
            "r": "Rare",
            "l": "Legendary"
        }

        # Check directory files & mtimes
        current_files = [f for f in os.listdir(self.ss_dir) if f.lower().endswith(".png")]
        dir_changed = force or len(current_files) != len(self._ref_gear_library)

        if not dir_changed:
            for f in current_files:
                fp = os.path.join(self.ss_dir, f)
                if os.path.getmtime(fp) != self._ref_gear_mtimes.get(f, 0.0):
                    dir_changed = True
                    break

        if not dir_changed and self._ref_gear_library:
            return self._ref_gear_library

        loaded_lib = []
        by_level: Dict[str, List[Dict[str, Any]]] = {"50": [], "65": [], "80": [], "90": []}
        new_mtimes = {}

        for f in current_files:
            fp = os.path.join(self.ss_dir, f)
            mtime = os.path.getmtime(fp)
            new_mtimes[f] = mtime

            clean_name = f[:-4]
            parts = clean_name.split("-")
            if len(parts) < 3:
                continue

            r_code = parts[0].lower()
            lv_str = parts[1]
            gear_name = "-".join(parts[2:])

            rarity = rarity_map.get(r_code, "Common")
            bracket = "50" if lv_str == "50" else ("65" if lv_str == "65" else "80_90")
            level_num = int(lv_str) if lv_str.isdigit() else lv_str

            img_raw = cv2.imread(fp, cv2.IMREAD_COLOR)
            if img_raw is None:
                continue

            th, tw = img_raw.shape[:2]
            # Adaptive scaling:
            # If snipped at standard ~46-53px, downscale by 0.8x to ~38-40px.
            # If already snipped at 1:1 scale (<= 43px), normalize to (38, 38).
            if tw >= 44 or th >= 44:
                res_w = max(4, int(round(tw * 0.8)))
                res_h = max(4, int(round(th * 0.8)))
                img_08 = cv2.resize(img_raw, (res_w, res_h), interpolation=cv2.INTER_AREA)
            else:
                img_08 = cv2.resize(img_raw, (38, 38), interpolation=cv2.INTER_AREA)

            img_08_gray = cv2.cvtColor(img_08, cv2.COLOR_BGR2GRAY)
            img_raw_gray = cv2.cvtColor(img_raw, cv2.COLOR_BGR2GRAY)

            entry = {
                "filename": f,
                "rarity": rarity,
                "bracket": bracket,
                "level": level_num,
                "gear_name": gear_name,
                "tmpl_08": img_08,
                "tmpl_raw": img_raw,
                "tmpl_08_gray": img_08_gray,
                "tmpl_raw_gray": img_raw_gray
            }
            loaded_lib.append(entry)
            by_level.setdefault(str(lv_str), []).append(entry)

        self._ref_gear_library = loaded_lib
        self._ref_gear_by_level = by_level
        self._ref_gear_mtimes = new_mtimes
        return self._ref_gear_library

    def reload_reference_gear_library(self) -> Dict[str, Any]:
        """Forces full reload of SS/ reference gear library."""
        self.load_reference_gear_library(force=True)
        return self.get_reference_library_stats()

    def has_reference_gear_library(self) -> bool:
        """Checks if reference gear library has any loaded templates."""
        return len(self._ref_gear_library) > 0

    def get_reference_library_stats(self) -> Dict[str, Any]:
        """Returns summary statistics of the loaded reference gear library."""
        lib = self._ref_gear_library
        rarity_counts = {
            "Common": sum(1 for itm in lib if itm["rarity"] == "Common"),
            "Uncommon": sum(1 for itm in lib if itm["rarity"] == "Uncommon"),
            "Rare": sum(1 for itm in lib if itm["rarity"] == "Rare"),
            "Legendary": sum(1 for itm in lib if itm["rarity"] == "Legendary")
        }
        level_counts = {
            "50": sum(1 for itm in lib if str(itm["level"]) == "50"),
            "65": sum(1 for itm in lib if str(itm["level"]) == "65"),
            "80": sum(1 for itm in lib if str(itm["level"]) == "80"),
            "90": sum(1 for itm in lib if str(itm["level"]) == "90")
        }
        status_text = (
            f"✅ {len(lib)} Reference Gear Templates Loaded ({self.ss_dir}/)"
            if lib else
            f"❌ No Reference Templates in {self.ss_dir}/"
        )
        return {
            "total": len(lib),
            "loaded": len(lib) > 0,
            "status_text": status_text,
            "rarity_counts": rarity_counts,
            "level_counts": level_counts
        }

    def match_reference_gear(
        self,
        window_bgr: np.ndarray,
        level_hint: Optional[str] = None,
        threshold: float = 0.78,
        max_color_diff: float = 26.0
    ) -> Optional[Dict[str, Any]]:
        """
        Matches a local slot window against the reference gear library in SS/.
        """
        if not self._ref_gear_library or window_bgr is None or window_bgr.size == 0:
            return None

        win_h, win_w = window_bgr.shape[:2]
        if win_h < 20 or win_w < 20:
            return None

        best_score = -1.0
        best_diff = 999.0
        best_ref = None
        best_loc = (0, 0)
        best_shape = (38, 38)

        # 1. Determine search pool (hinted level first if available)
        primary_pool = (
            self._ref_gear_by_level.get(str(level_hint), self._ref_gear_library)
            if level_hint else self._ref_gear_library
        )

        win_gray = cv2.cvtColor(window_bgr, cv2.COLOR_BGR2GRAY) if len(window_bgr.shape) == 3 else window_bgr

        def check_pool(pool, tmpl_key):
            nonlocal best_score, best_diff, best_ref, best_loc, best_shape
            gray_key = tmpl_key + "_gray"
            for item in pool:
                tmpl = item[tmpl_key]
                tmpl_gray = item.get(gray_key)
                if tmpl_gray is None:
                    tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY) if len(tmpl.shape) == 3 else tmpl
                th, tw = tmpl.shape[:2]
                if th <= win_h and tw <= win_w:
                    res = cv2.matchTemplate(win_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
                    min_v, max_v, min_l, max_l = cv2.minMaxLoc(res)
                    if max_v >= threshold and max_v > best_score:
                        patch = window_bgr[max_l[1]:max_l[1] + th, max_l[0]:max_l[0] + tw]
                        diff = float(np.mean(cv2.absdiff(patch, tmpl)))
                        if diff <= max_color_diff:
                            best_score = max_v
                            best_diff = diff
                            best_ref = item
                            best_loc = max_l
                            best_shape = (th, tw)

        # Pass 1: 0.8x templates on primary pool
        check_pool(primary_pool, "tmpl_08")

        # Pass 2: If hinted search did not meet threshold, search the full library
        if best_score < threshold and primary_pool is not self._ref_gear_library:
            check_pool(self._ref_gear_library, "tmpl_08")

        # Pass 3: 1.0x raw templates fallback (in case display capture is at 125% DPI)
        if best_score < threshold:
            check_pool(self._ref_gear_library, "tmpl_raw")

        if best_score >= threshold and best_ref is not None:
            return {
                "matched": True,
                "rarity": best_ref["rarity"],
                "bracket": best_ref["bracket"],
                "level": best_ref["level"],
                "gear_name": best_ref["gear_name"],
                "filename": best_ref["filename"],
                "score": float(best_score),
                "diff": float(best_diff),
                "match_loc": best_loc,
                "tmpl_shape": best_shape
            }

        return None

    # ---------------------------------------------------------
    # Stage 1 & 2: Rarity Border Classification & Level Digit Recognition
    # ---------------------------------------------------------
    def _get_digit_templates(self) -> Dict[str, np.ndarray]:
        """Loads and caches binary digit templates (50, 65, 80, 90)."""
        if self._cached_digit_tmpls:
            return self._cached_digit_tmpls

        tmpls = {}
        for lv in ["50", "65", "80", "90"]:
            p = os.path.join(self.assets_dir, f"num_{lv}.png")
            if os.path.isfile(p):
                img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    tmpls[lv] = img

        self._cached_digit_tmpls = tmpls
        return self._cached_digit_tmpls

    def classify_slot_border_rarity(self, slot_bgr: np.ndarray) -> str:
        """
        Stage 1: Classifies slot rarity by sampling top and left outer borders.
        Strictly excludes the right edge and bottom-right corner where red badges sit.
        Includes Immortal Guard to immediately reject out-of-scope high-rarity items.
        Returns: 'Immortal', 'Common', 'Uncommon', 'Rare', 'Legendary', or 'Unknown'.
        """
        if slot_bgr is None or slot_bgr.size == 0:
            return "Unknown"

        h, w = slot_bgr.shape[:2]
        if h < 20 or w < 20:
            return "Unknown"

        top_p = slot_bgr[1:5, 1:w - 1]
        left_p = slot_bgr[1:h - 1, 1:5]
        border_pixels = np.vstack([top_p.reshape(-1, 3), left_p.reshape(-1, 3)])
        if border_pixels.size == 0:
            return "Unknown"

        hsv = cv2.cvtColor(border_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)

        # 1. Immortal Guard: Crimson / Pure Red / Deep Magenta along top or left border
        imm_count = np.sum(((hsv[:, 0] <= 10) | (hsv[:, 0] >= 165)) & (hsv[:, 1] >= 80) & (border_pixels[:, 2] >= 90))
        if imm_count >= 15:
            return "Immortal"

        # 2. Uncommon (Green)
        green_count = np.sum((hsv[:, 0] >= 35) & (hsv[:, 0] <= 85) & (hsv[:, 1] >= 60))
        if green_count >= 40:
            return "Uncommon"

        # 3. Rare (Blue)
        blue_count = np.sum((hsv[:, 0] >= 90) & (hsv[:, 0] <= 140) & (hsv[:, 1] >= 60))
        if blue_count >= 40:
            return "Rare"

        # 4. Legendary (Gold / Amber / Warm Orange)
        gold_count = np.sum((hsv[:, 0] >= 11) & (hsv[:, 0] <= 28) & (hsv[:, 1] >= 80))
        if gold_count >= 40:
            return "Legendary"

        # 5. Default Common (Slate Gray / Neutral)
        return "Common"

    def classify_multi_corner_rarity(self, slot_bgr: np.ndarray, corner_size: int = 10) -> Dict[str, Any]:
        """
        Switchable Feature: Rarity Identification via 3 Corner Detectors (TL, TR, BL).
        """
        if slot_bgr is None or slot_bgr.size == 0:
            return {"rarity": "Common", "confidence": 0.0, "corners": {}, "votes": {}}

        h, w = slot_bgr.shape[:2]
        cw = min(w // 3, max(4, int(corner_size)))
        ch = min(h // 3, max(4, int(corner_size)))

        corners_def = {
            "tl": (1, 1, cw, ch),
            "tr": (max(0, w - cw - 1), 1, cw, ch),
            "bl": (1, max(0, h - ch - 1), cw, ch)
        }

        corner_results = {}
        votes = {"Common": 0, "Uncommon": 0, "Rare": 0, "Legendary": 0, "Immortal": 0}

        for c_key, (cx, cy, cw_i, ch_i) in corners_def.items():
            patch = slot_bgr[cy:cy + ch_i, cx:cx + cw_i]
            if patch.size == 0:
                continue

            bgr_flat = patch.reshape(-1, 3)
            hsv_flat = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)

            imm_mask = ((hsv_flat[:, 0] <= 10) | (hsv_flat[:, 0] >= 165)) & (hsv_flat[:, 1] >= 80) & (bgr_flat[:, 2] >= 85)
            uncom_mask = (hsv_flat[:, 0] >= 35) & (hsv_flat[:, 0] <= 85) & (hsv_flat[:, 1] >= 50)
            rare_mask = (hsv_flat[:, 0] >= 90) & (hsv_flat[:, 0] <= 140) & (hsv_flat[:, 1] >= 50)
            leg_mask = (hsv_flat[:, 0] >= 11) & (hsv_flat[:, 0] <= 28) & (hsv_flat[:, 1] >= 70)

            n_total = len(bgr_flat)
            c_rarity = "Common"
            c_conf = 0.5
            if np.sum(imm_mask) / n_total >= 0.20:
                c_rarity = "Immortal"
                c_conf = float(np.sum(imm_mask) / n_total)
            elif np.sum(leg_mask) / n_total >= 0.25:
                c_rarity = "Legendary"
                c_conf = float(np.sum(leg_mask) / n_total)
            elif np.sum(rare_mask) / n_total >= 0.25:
                c_rarity = "Rare"
                c_conf = float(np.sum(rare_mask) / n_total)
            elif np.sum(uncom_mask) / n_total >= 0.25:
                c_rarity = "Uncommon"
                c_conf = float(np.sum(uncom_mask) / n_total)
            else:
                m_b, m_g, m_r = patch.mean(axis=(0, 1))
                if m_b > m_g + 15 and m_b > m_r + 20:
                    c_rarity = "Rare"
                    c_conf = 0.65
                elif m_g > m_b + 15 and m_g > m_r + 15:
                    c_rarity = "Uncommon"
                    c_conf = 0.65
                elif m_r > m_b + 25 and m_r > m_g + 10:
                    c_rarity = "Legendary"
                    c_conf = 0.65

            votes[c_rarity] += 1
            corner_results[c_key] = {
                "box": (cx, cy, cw_i, ch_i),
                "rarity": c_rarity,
                "conf": c_conf
            }

        dominant_rarity = max(votes, key=votes.get)
        total_votes = sum(votes.values())
        overall_conf = votes[dominant_rarity] / max(1, total_votes)

        return {
            "rarity": dominant_rarity,
            "confidence": overall_conf,
            "corners": corner_results,
            "votes": votes
        }

    def detect_slot_level(self, slot_bgr: np.ndarray, threshold: float = 0.65, expected_lv: Optional[str] = None) -> Tuple[Optional[str], float]:
        """
        Stage 2: Precision Level Digit Recognition on bottom-right corner.
        Matches against two-digit templates ('50', '65', '80', '90') AND performs an exact tens-digit
        verification at the match location to 100% block lower or mismatched level items.
        If expected_lv is provided, validates whether the candidate slot matches expected_lv before
        falling back to open-set classification.
        """
        if slot_bgr is None or slot_bgr.size == 0:
            return None, 0.0

        h, w = slot_bgr.shape[:2]
        if h < 20 or w < 20:
            return None, 0.0

        # Adaptive normalization for raw 1.0x scale slots (>= 44px) so digit templates match at standard scale
        if h >= 44 or w >= 44:
            slot_bgr = cv2.resize(slot_bgr, (int(round(w * 0.8)), int(round(h * 0.8))), interpolation=cv2.INTER_AREA)
            h, w = slot_bgr.shape[:2]

        crop = slot_bgr[h // 2:, max(0, w - 24):]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        is_white = (gray > 130)
        b, g, r = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
        is_yellow = (r > 160) & (g > 160)
        is_red = (r > 130) & (g < 100) & (b < 100) if expected_lv != "50" else False
        slot_bin = np.where(is_white | is_red | is_yellow, 255, 0).astype(np.uint8)

        digit_tmpls = self._get_digit_templates()
        scores = {}
        locs = {}
        for lv, tmpl in digit_tmpls.items():
            if tmpl.shape[0] > slot_bin.shape[0] or tmpl.shape[1] > slot_bin.shape[1]:
                continue
            res = cv2.matchTemplate(slot_bin, tmpl, cv2.TM_CCOEFF_NORMED)
            min_v, max_v, _, max_l = cv2.minMaxLoc(res)
            scores[lv] = float(max_v)
            locs[lv] = max_l

        if not scores:
            return None, 0.0

        # Targeted validation if expected_lv is specified and verified
        if expected_lv and expected_lv in scores and expected_lv in locs and expected_lv in digit_tmpls:
            exp_sc = scores[expected_lv]
            # Cross-level protection: If another level strongly beats expected_lv, do NOT short-circuit!
            other_scores = {lv: s for lv, s in scores.items() if lv != expected_lv}
            best_other = max(other_scores, key=other_scores.get) if other_scores else None
            if best_other and other_scores[best_other] >= 0.70 and other_scores[best_other] > exp_sc + 0.08:
                pass  # Do not short-circuit, let competitive resolution run
            elif exp_sc >= 0.60:
                tmpl_full = digit_tmpls[expected_lv]
                tens_width = 5 if expected_lv == "50" else 6
                tens_tmpl = tmpl_full[:, :tens_width]
                mx, my = locs[expected_lv]
                patch_tens = slot_bin[my:my + tens_tmpl.shape[0], mx:mx + tens_tmpl.shape[1]]
                if patch_tens.shape == tens_tmpl.shape:
                    t_sc = float(cv2.matchTemplate(patch_tens, tens_tmpl, cv2.TM_CCOEFF_NORMED)[0, 0])
                    min_tens = 0.58 if expected_lv == "50" else 0.40
                    if t_sc >= min_tens or (exp_sc >= 0.70 and expected_lv != "50"):
                        return expected_lv, exp_sc

        # Disambiguate 50 vs 90 when both share units digit 0
        s50 = scores.get("50", 0.0)
        s90 = scores.get("90", 0.0)
        if s50 >= 0.55 and s90 >= 0.55 and "50" in locs and "90" in locs and "50" in digit_tmpls and "90" in digit_tmpls:
            tens5 = digit_tmpls["50"][:, :6]
            tens9 = digit_tmpls["90"][:, :6]
            loc5 = locs["50"]
            loc9 = locs["90"]
            p5 = slot_bin[loc5[1]:loc5[1] + tens5.shape[0], loc5[0]:loc5[0] + tens5.shape[1]]
            p9 = slot_bin[loc9[1]:loc9[1] + tens9.shape[0], loc9[0]:loc9[0] + tens9.shape[1]]
            sc_t5 = float(cv2.matchTemplate(p5, tens5, cv2.TM_CCOEFF_NORMED)[0, 0]) if p5.shape == tens5.shape else 0.0
            sc_t9 = float(cv2.matchTemplate(p9, tens9, cv2.TM_CCOEFF_NORMED)[0, 0]) if p9.shape == tens9.shape else 0.0

            if sc_t5 > sc_t9:
                scores["90"] = min(scores["90"], scores["50"] - 0.05)
            elif sc_t9 > sc_t5:
                scores["50"] = min(scores["50"], scores["90"] - 0.05)

        best_lv = max(scores, key=scores.get)
        best_sc = scores[best_lv]
        if best_sc < threshold:
            return None, best_sc

        # Tens digit verification at the exact match coordinate:
        if best_lv in digit_tmpls and best_lv in locs:
            tmpl_full = digit_tmpls[best_lv]
            tens_w = 5 if best_lv == "50" else 6
            tens_tmpl = tmpl_full[:, :tens_w]
            mx, my = locs[best_lv]
            patch_tens = slot_bin[my:my + tens_tmpl.shape[0], mx:mx + tens_tmpl.shape[1]]
            if patch_tens.shape == tens_tmpl.shape:
                tens_score = float(cv2.matchTemplate(patch_tens, tens_tmpl, cv2.TM_CCOEFF_NORMED)[0, 0])
                min_tens = 0.65 if best_lv == "50" else 0.55
                if tens_score < min_tens and best_sc < 0.85:
                    return None, best_sc

        return best_lv, best_sc

    # ---------------------------------------------------------
    # Automatic Inventory Grid Box Anchor
    # ---------------------------------------------------------
    def get_inventory_roi(self) -> Dict[str, int]:
        """
        Uses calibrated ROI from config if available, or automatically locates inv_tab_btn.png.
        """
        cfg_rois = self.config.get("rois", {})
        calibrated = cfg_rois.get("inventory_roi") or cfg_rois.get("inventory_grid")
        if calibrated and calibrated.get("width", 0) > 40 and calibrated.get("height", 0) > 40:
            return calibrated

        # Auto-detect via inv_tab_btn.png
        screen = ScreenCapture.capture_screen()
        match = self.matcher.find_template(screen, "inv_tab_btn.png", threshold=0.72)
        if match:
            tab_x, tab_y, tab_w, tab_h, _ = match
            return {
                "x": max(0, tab_x - 10),
                "y": max(0, tab_y - 165),
                "width": 330,
                "height": 155
            }

        # Fallback coordinates
        return {"x": 1416, "y": 646, "width": 330, "height": 155}

    # ---------------------------------------------------------
    # Inventory Scanning (3-Stage Decoupled Engine)
    # ---------------------------------------------------------
    def scan_visible_inventory(
        self,
        inventory_roi: Optional[Dict[str, int]] = None,
        min_y_offset: int = 0,
        roi_img: Optional[np.ndarray] = None,
        threshold: Optional[float] = None,
        level_filter: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans current visible inventory grid ROI using the 3-Stage Decoupled Engine:
        Stage 1: Border Rarity Classification with Immortal Guard.
        Stage 2: Precision Level Digit Verification on corner bitmap font.
        Stage 3: SS/ Reference Gear Verification for exact sprite confirmation.
        Filters clipped rows and locked items.
        """
        roi = inventory_roi or self.get_inventory_roi()
        if roi_img is None:
            roi_img = ScreenCapture.capture_screen(roi)

        if roi_img is None or roi_img.size == 0:
            return []

        roi_h, roi_w = roi_img.shape[:2]
        if roi_h < 30 or roi_w < 30:
            return []

        if not self.has_reference_gear_library():
            return []

        search_lib = self._ref_gear_library
        if level_filter is not None:
            if isinstance(level_filter, (list, tuple, set)):
                targets = {str(x) for x in level_filter}
                search_lib = [r for r in self._ref_gear_library if str(r.get("level")) in targets or str(r.get("bracket")) in targets]
            else:
                target = str(level_filter)
                search_lib = [r for r in self._ref_gear_library if str(r.get("level")) == target or str(r.get("bracket")) == target]

        if not search_lib:
            return []

        conf_threshold = threshold if threshold is not None else float(self.config.get("confidence_threshold", 0.75))
        badge_w = max(8, int(self.config.get("badge_detector_width", 19)))
        badge_h = max(6, int(self.config.get("badge_detector_height", 15)))
        badge_thresh = float(self.config.get("badge_match_threshold", 0.75))
        multi_corner_enabled = bool(self.config.get("multi_corner_rarity_enabled", False))
        corner_size = max(4, int(self.config.get("corner_detector_size", 10)))

        raw_candidates = []
        roi_gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY) if len(roi_img.shape) == 3 else roi_img

        # Pass 1: Standard 0.8x scaled templates (100% DPI game scale)
        for ref in search_lib:
            tmpl = ref["tmpl_08"]
            tmpl_gray = ref.get("tmpl_08_gray")
            if tmpl_gray is None:
                tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY) if len(tmpl.shape) == 3 else tmpl
            th, tw = tmpl.shape[:2]
            if th > roi_h or tw > roi_w:
                continue

            res = cv2.matchTemplate(roi_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= conf_threshold)
            for pt in zip(*loc[::-1]):
                px, py = pt[0], pt[1]
                score = float(res[py, px])

                # Skip items clipped by top or bottom ROI boundary
                if py < -4 or (py + th) > roi_h + 4:
                    continue

                crop_y1 = max(0, py)
                crop_y2 = min(roi_h, py + th)
                crop_x1 = max(0, px)
                crop_x2 = min(roi_w, px + tw)
                slot_crop = roi_img[crop_y1:crop_y2, crop_x1:crop_x2]
                tmpl_crop = tmpl[:crop_y2 - crop_y1, :crop_x2 - crop_x1]

                # 1. Immortal Guard
                r_detected = self.classify_slot_border_rarity(slot_crop)
                if r_detected == "Immortal":
                    continue

                # 2. Color Fidelity
                diff = float(np.mean(cv2.absdiff(slot_crop, tmpl_crop)))
                if diff > 30.0:
                    continue

                # Optional Switchable 3-Corner Rarity Check
                corner_info = None
                if multi_corner_enabled:
                    corner_info = self.classify_multi_corner_rarity(slot_crop, corner_size=corner_size)
                    if corner_info.get("rarity") == "Immortal":
                        continue
                    if corner_info.get("confidence", 0.0) >= 0.85 and corner_info.get("rarity") != ref["rarity"]:
                        continue

                # 3. Corner Level Badge Verification
                ch, cw = slot_crop.shape[:2]
                lv_score = 1.0
                effective_bw = min(badge_w, 20)
                effective_bh = min(badge_h, 16)
                if ch >= effective_bh and cw >= effective_bw:
                    c_slot = slot_crop[max(0, ch - effective_bh):ch, max(0, cw - effective_bw):cw]
                    c_tmpl = tmpl_crop[max(0, ch - effective_bh):ch, max(0, cw - effective_bw):cw]
                    if c_slot.shape == c_tmpl.shape:
                        corner_match = float(cv2.matchTemplate(c_slot, c_tmpl, cv2.TM_CCOEFF_NORMED)[0, 0])
                        lv_score = max(0.0, corner_match)
                        if corner_match < badge_thresh:
                            continue

                    ref_lv = str(ref.get("level", ""))
                    if ref_lv in ("50", "65", "80", "90"):
                        det_lv, _ = self.detect_slot_level(slot_crop, expected_lv=ref_lv)
                        if det_lv is not None and det_lv != ref_lv:
                            continue
                        # Common gear cross-bracket collision guard:
                        # Common items share identical base sprites across brackets (50, 65, 80, 90).
                        # When matching against a Common Lv. 50 template, the slot must be positively confirmed as Lv. 50.
                        if ref_lv == "50" and ref.get("rarity") == "Common" and det_lv != "50":
                            continue

                # Lock Check
                if self.matcher.template_exists("lock_icon.png"):
                    if self.matcher.find_template(slot_crop, "lock_icon.png", threshold=0.75):
                        continue

                raw_candidates.append({
                    "x": px, "y": py, "w": tw, "h": th,
                    "score": score, "lv_score": lv_score,
                    "ref": ref,
                    "corner_info": corner_info
                })

        # Pass 2: Fallback to 1.0x raw templates if no matches found (125% DPI scale)
        if not raw_candidates:
            for ref in search_lib:
                tmpl = ref["tmpl_raw"]
                tmpl_gray = ref.get("tmpl_raw_gray")
                if tmpl_gray is None:
                    tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY) if len(tmpl.shape) == 3 else tmpl
                th, tw = tmpl.shape[:2]
                if th > roi_h or tw > roi_w:
                    continue

                res = cv2.matchTemplate(roi_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res >= conf_threshold)
                for pt in zip(*loc[::-1]):
                    px, py = pt[0], pt[1]
                    score = float(res[py, px])

                    if py < -4 or (py + th) > roi_h + 4:
                        continue

                    crop_y1 = max(0, py)
                    crop_y2 = min(roi_h, py + th)
                    crop_x1 = max(0, px)
                    crop_x2 = min(roi_w, px + tw)
                    slot_crop = roi_img[crop_y1:crop_y2, crop_x1:crop_x2]
                    tmpl_crop = tmpl[:crop_y2 - crop_y1, :crop_x2 - crop_x1]

                    r_detected = self.classify_slot_border_rarity(slot_crop)
                    if r_detected == "Immortal":
                        continue

                    diff = float(np.mean(cv2.absdiff(slot_crop, tmpl_crop)))
                    if diff > 30.0:
                        continue

                    corner_info = None
                    if multi_corner_enabled:
                        corner_info = self.classify_multi_corner_rarity(slot_crop, corner_size=corner_size)
                        if corner_info.get("rarity") == "Immortal":
                            continue
                        if corner_info.get("confidence", 0.0) >= 0.85 and corner_info.get("rarity") != ref["rarity"]:
                            continue

                    ch, cw = slot_crop.shape[:2]
                    lv_score = 1.0
                    effective_bw = min(badge_w, 24)
                    effective_bh = min(badge_h, 20)
                    if ch >= effective_bh and cw >= effective_bw:
                        c_slot = slot_crop[max(0, ch - effective_bh):ch, max(0, cw - effective_bw):cw]
                        c_tmpl = tmpl_crop[max(0, ch - effective_bh):ch, max(0, cw - effective_bw):cw]
                        if c_slot.shape == c_tmpl.shape:
                            corner_match = float(cv2.matchTemplate(c_slot, c_tmpl, cv2.TM_CCOEFF_NORMED)[0, 0])
                            lv_score = max(0.0, corner_match)
                            if corner_match < badge_thresh:
                                continue

                        ref_lv = str(ref.get("level", ""))
                        if ref_lv in ("50", "65", "80", "90"):
                            det_lv, _ = self.detect_slot_level(slot_crop, expected_lv=ref_lv)
                            if det_lv is not None and det_lv != ref_lv:
                                continue
                            # Common gear cross-bracket collision guard:
                            if ref_lv == "50" and ref.get("rarity") == "Common" and det_lv != "50":
                                continue

                    if self.matcher.template_exists("lock_icon.png"):
                        if self.matcher.find_template(slot_crop, "lock_icon.png", threshold=0.75):
                            continue

                    raw_candidates.append({
                        "x": px, "y": py, "w": tw, "h": th,
                        "score": score, "lv_score": lv_score,
                        "ref": ref,
                        "corner_info": corner_info
                    })

        if not raw_candidates:
            return []

        # Non-Maximum Suppression (NMS) by center distance (18px)
        raw_candidates.sort(key=lambda c: (c["score"] + c["lv_score"]), reverse=True)

        accepted_candidates = []
        for cand in raw_candidates:
            cx = cand["x"] + cand["w"] / 2.0
            cy = cand["y"] + cand["h"] / 2.0
            if not any(np.hypot(cx - (a["x"] + a["w"] / 2.0), cy - (a["y"] + a["h"] / 2.0)) < 18 for a in accepted_candidates):
                accepted_candidates.append(cand)

        detected_items = []
        for cand in accepted_candidates:
            slot_x, slot_y = cand["x"], cand["y"]
            slot_w, slot_h = cand["w"], cand["h"]
            ref = cand["ref"]

            # Overlap Line Check: skip items whose top is above min_y_offset
            if min_y_offset > 0 and slot_y < min_y_offset:
                continue

            screen_x = roi["x"] + slot_x + slot_w // 2
            screen_y = roi["y"] + slot_y + slot_h // 2

            detected_items.append({
                "bracket": ref["bracket"],
                "rarity": ref["rarity"],
                "level": ref["level"],
                "gear_name": ref["gear_name"],
                "ref_file": ref["filename"],
                "template_fn": ref["filename"],
                "score": cand["score"],
                "lv_score": cand["lv_score"],
                "corner_info": cand.get("corner_info"),
                "corner_boxes": [
                    (slot_x + 1, slot_y + 1, corner_size, corner_size),
                    (max(0, slot_x + slot_w - corner_size - 1), slot_y + 1, corner_size, corner_size),
                    (slot_x + 1, max(0, slot_y + slot_h - corner_size - 1), corner_size, corner_size)
                ],
                "click_x": screen_x,
                "click_y": screen_y,
                "slot_box": (slot_x, slot_y, slot_w, slot_h),
                "badge_pos": (slot_x + slot_w - badge_w, slot_y + slot_h - badge_h, max(1, badge_w - 1), max(1, badge_h - 1)),
                "slot_x": slot_x,
                "slot_y": slot_y,
                "slot_w": slot_w,
                "slot_h": slot_h,
                "center_x": screen_x,
                "center_y": screen_y,
                "level_bracket": ref["bracket"]
            })

        detected_items.sort(key=lambda itm: (itm["slot_y"], itm["slot_x"]))
        return detected_items

    # ---------------------------------------------------------
    # Scroll Helpers & Overlap Calculation
    # ---------------------------------------------------------
    def detect_vertical_scroll_shift(self, prev_roi_img: np.ndarray, curr_roi_img: np.ndarray) -> int:
        """
        Computes the vertical pixel shift dy (how many pixels content moved UP when scrolling down).
        """
        if prev_roi_img is None or curr_roi_img is None:
            return 0

        h, w = prev_roi_img.shape[:2]
        if h < 40 or w < 40:
            return 0

        cfg_strip_w = int(self.config.get("grid_settings", {}).get("scroll_strip_width", 0))
        strip_w = min(w, max(20, cfg_strip_w)) if cfg_strip_w > 0 else max(20, w - 18)

        slice_y1 = int(h * 0.40)
        slice_y2 = int(h * 0.85)

        prev_slice = prev_roi_img[slice_y1:slice_y2, :strip_w]
        curr_search = curr_roi_img[:, :strip_w]

        res = cv2.matchTemplate(curr_search, prev_slice, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= 0.65:
            matched_y = max_loc[1]
            dy = slice_y1 - matched_y
            if dy > 4:
                return int(dy)

        # Mathematical fallback: 2D FFT Phase Correlation
        try:
            prev_gray = cv2.cvtColor(prev_roi_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
            curr_gray = cv2.cvtColor(curr_roi_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
            hann = cv2.createHanningWindow((w, h), cv2.CV_32F)
            shift, response = cv2.phaseCorrelate(prev_gray, curr_gray, hann)
            if response >= 0.15:
                dy = int(round(-shift[1]))
                if dy > 4:
                    return dy
        except Exception:
            pass

        return 0

    def detect_vertical_scroll_offset(self, prev_roi_img: np.ndarray, curr_roi_img: np.ndarray) -> int:
        """
        Computes vertical pixel shift dy when scrolling down using template strip alignment.
        """
        if prev_roi_img is None or curr_roi_img is None:
            return 0

        h, w = prev_roi_img.shape[:2]
        if h < 50 or w < 50:
            return 0

        cfg_strip_w = int(self.config.get("grid_settings", {}).get("scroll_strip_width", 0))
        strip_w = min(w, max(20, cfg_strip_w)) if cfg_strip_w > 0 else max(20, w - 18)

        slice_y1 = int(h * 0.3)
        slice_y2 = int(h * 0.7)

        prev_slice = prev_roi_img[slice_y1:slice_y2, :strip_w]
        curr_search = curr_roi_img[:, :strip_w]

        res = cv2.matchTemplate(curr_search, prev_slice, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= 0.70:
            matched_y = max_loc[1]
            dy = slice_y1 - matched_y
            if dy > 0:
                return max(0, h - dy)

        # Mathematical fallback: 2D FFT Phase Correlation
        try:
            prev_gray = cv2.cvtColor(prev_roi_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
            curr_gray = cv2.cvtColor(curr_roi_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
            hann = cv2.createHanningWindow((w, h), cv2.CV_32F)
            shift, response = cv2.phaseCorrelate(prev_gray, curr_gray, hann)
            if response >= 0.20:
                dy = int(round(-shift[1]))
                if dy > 4:
                    return max(0, h - dy)
        except Exception:
            pass

        return 0

    def is_inventory_at_bottom(self, prev_roi_img: np.ndarray, curr_roi_img: np.ndarray, threshold: float = 1.5) -> bool:
        """Checks if screen / scrollbar difference is below threshold."""
        if prev_roi_img is None or curr_roi_img is None:
            return False
        diff = float(np.mean(cv2.absdiff(prev_roi_img, curr_roi_img)))
        return diff < threshold
