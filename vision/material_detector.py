"""
Material Detection Module for Task Bar Hero.
Manages the SS_materials/ reference library (42 material types across Uncommon, Rare, Legendary, Immortal)
and detects visible materials in inventory slots for automatic stashing.
"""
import os
import cv2
import numpy as np
from typing import Optional, List, Dict, Any, Tuple
from .template_matcher import TemplateMatcher
from .screen import ScreenCapture


class MaterialDetector:
    def __init__(
        self,
        matcher: TemplateMatcher,
        config: Optional[Dict[str, Any]] = None,
        materials_dir: str = "SS_materials",
        manifest_path: str = "materials_manifest.json"
    ):
        self.matcher = matcher
        self.config = config or {}
        self.materials_dir = materials_dir
        self.manifest_path = manifest_path

        self._mat_library: List[Dict[str, Any]] = []
        self._mat_by_rarity: Dict[str, List[Dict[str, Any]]] = {
            "Common": [],
            "Uncommon": [],
            "Rare": [],
            "Legendary": [],
            "Immortal": []
        }
        self._mat_mtimes: Dict[str, float] = {}

        self.load_material_library()

    def update_config(self, config_data: Dict[str, Any]):
        """Update live configuration data."""
        self.config = config_data

    # ---------------------------------------------------------
    # Color Fingerprinting & Anti-Recolor Matching Engine
    # ---------------------------------------------------------
    @staticmethod
    def extract_color_profile(img: np.ndarray) -> Dict[str, Any]:
        """
        Extracts foreground color fingerprint from a template image.
        Isolates colored icon pixels from dark inventory slot backgrounds,
        computing median Hue, CIELAB a*/b* chromaticities, and 2D HSV histogram.
        """
        if img is None or img.size == 0:
            return {"is_colored": False, "shape": (0, 0)}

        th, tw = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

        sat_mask = (hsv[:, :, 1] >= 30) & (hsv[:, :, 2] >= 35)
        num_sat = int(np.sum(sat_mask))
        is_colored = bool(num_sat >= 30)

        if is_colored:
            med_hue = float(np.median(hsv[:, :, 0][sat_mask]))
            mean_a = float(np.mean(lab[:, :, 1][sat_mask]))
            mean_b = float(np.mean(lab[:, :, 2][sat_mask]))
            mask_u8 = sat_mask.astype(np.uint8) * 255
            hist = cv2.calcHist([hsv], [0, 1], mask_u8, [18, 16], [0, 180, 0, 256])
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        else:
            fg_mask = lab[:, :, 0] >= 35
            if np.sum(fg_mask) < 20:
                fg_mask = np.ones((th, tw), dtype=bool)
            sat_mask = fg_mask
            med_hue = 0.0
            mean_a = float(np.mean(lab[:, :, 1][fg_mask]))
            mean_b = float(np.mean(lab[:, :, 2][fg_mask]))
            hist = None

        return {
            "is_colored": is_colored,
            "sat_mask": sat_mask,
            "med_hue": med_hue,
            "mean_a": mean_a,
            "mean_b": mean_b,
            "hist": hist,
            "shape": (th, tw)
        }

    @staticmethod
    def verify_color_similarity(candidate: np.ndarray, prof: Dict[str, Any]) -> Tuple[float, float, float]:
        """
        Verifies if candidate crop matches the template color profile.
        Strictly rejects recolored variants sharing identical geometry.
        Returns: (color_score: [0.0, 1.0], hue_diff: float, chroma_dist: float)
        """
        if candidate is None or candidate.size == 0 or not prof or not prof.get("shape"):
            return 0.0, 180.0, 100.0

        th, tw = prof["shape"]
        if candidate.shape[:2] != (th, tw):
            candidate = cv2.resize(candidate, (tw, th), interpolation=cv2.INTER_AREA)

        mask = prof["sat_mask"]
        if prof.get("is_colored", False):
            cand_hsv = cv2.cvtColor(candidate, cv2.COLOR_BGR2HSV)
            cand_hues = cand_hsv[:, :, 0][mask]
            if len(cand_hues) == 0:
                return 0.0, 180.0, 100.0

            cand_med_hue = float(np.median(cand_hues))
            hue_diff = abs(cand_med_hue - prof["med_hue"])
            hue_diff = min(hue_diff, 180.0 - hue_diff)

            cand_lab = cv2.cvtColor(candidate, cv2.COLOR_BGR2LAB)
            delta_a = float(np.mean(cand_lab[:, :, 1][mask])) - prof["mean_a"]
            delta_b = float(np.mean(cand_lab[:, :, 2][mask])) - prof["mean_b"]
            chroma_dist = float(np.sqrt(delta_a**2 + delta_b**2))

            if hue_diff > 16.0 or chroma_dist > 25.0:
                return 0.0, hue_diff, chroma_dist

            mask_u8 = mask.astype(np.uint8) * 255
            hist_cand = cv2.calcHist([cand_hsv], [0, 1], mask_u8, [18, 16], [0, 180, 0, 256])
            cv2.normalize(hist_cand, hist_cand, 0, 1, cv2.NORM_MINMAX)
            hist_corr = max(0.0, float(cv2.compareHist(hist_cand, prof["hist"], cv2.HISTCMP_CORREL)))

            hue_score = max(0.0, 1.0 - (hue_diff / 20.0))
            chroma_score = max(0.0, 1.0 - (chroma_dist / 25.0))
            color_score = 0.4 * hue_score + 0.3 * chroma_score + 0.3 * hist_corr
            return color_score, hue_diff, chroma_dist
        else:
            cand_lab = cv2.cvtColor(candidate, cv2.COLOR_BGR2LAB)
            delta_a = float(np.mean(cand_lab[:, :, 1][mask])) - prof["mean_a"]
            delta_b = float(np.mean(cand_lab[:, :, 2][mask])) - prof["mean_b"]
            dist = float(np.sqrt(delta_a**2 + delta_b**2))
            if dist > 35.0:
                return 0.0, 0.0, dist
            color_score = max(0.0, 1.0 - (dist / 35.0))
            return color_score, 0.0, dist

    # ---------------------------------------------------------
    # SS_materials/ Library Management
    # ---------------------------------------------------------
    def load_material_library(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        Loads all reference material templates from materials_dir (default 'SS_materials/').
        Standard filename format: <rarity_code>-<material_name>.png
          rarity_code: 'u' (Uncommon), 'r' (Rare), 'l' (Legendary), 'i' (Immortal)
        Pre-scales templates to 0.8x (optimal for standard 100% DPI game scale),
        and stores 1.0x as fallback.
        """
        if not os.path.isdir(self.materials_dir):
            os.makedirs(self.materials_dir, exist_ok=True)
            return self._mat_library

        rarity_map = {
            "c": "Common",
            "u": "Uncommon",
            "r": "Rare",
            "l": "Legendary",
            "i": "Immortal"
        }

        current_files = [f for f in os.listdir(self.materials_dir) if f.lower().endswith(".png")]
        dir_changed = force or len(current_files) != len(self._mat_library)

        if not dir_changed:
            for f in current_files:
                fp = os.path.join(self.materials_dir, f)
                if os.path.getmtime(fp) != self._mat_mtimes.get(f, 0.0):
                    dir_changed = True
                    break

        if not dir_changed and self._mat_library:
            return self._mat_library

        loaded_lib = []
        by_rarity: Dict[str, List[Dict[str, Any]]] = {
            "Common": [],
            "Uncommon": [],
            "Rare": [],
            "Legendary": [],
            "Immortal": []
        }
        new_mtimes = {}

        # Load custom material names from manifest if available
        manifest_names: Dict[str, str] = {}
        if os.path.isfile(self.manifest_path):
            try:
                import json
                with open(self.manifest_path, "r", encoding="utf-8") as mf:
                    mdata = json.load(mf)
                    for cat_items in mdata.values():
                        if isinstance(cat_items, list):
                            for item in cat_items:
                                if isinstance(item, dict) and "filename" in item and "name" in item:
                                    manifest_names[item["filename"]] = item["name"]
            except Exception:
                pass

        for f in current_files:
            fp = os.path.join(self.materials_dir, f)
            mtime = os.path.getmtime(fp)
            new_mtimes[f] = mtime

            clean_name = f[:-4]
            parts = clean_name.split("-")
            if len(parts) < 2:
                continue

            r_code = parts[0].lower()
            mat_name = manifest_names.get(f, "-".join(parts[1:]))
            rarity = rarity_map.get(r_code)
            if not rarity:
                continue

            img = cv2.imread(fp, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                continue

            # Standard 0.8x scaled template (matches 40px slot from 50px capture)
            h, w = img.shape[:2]
            scale_08 = cv2.resize(img, (max(8, int(w * 0.8)), max(8, int(h * 0.8))), interpolation=cv2.INTER_AREA)

            scale_08_gray = cv2.cvtColor(scale_08, cv2.COLOR_BGR2GRAY)
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            color_prof_raw = self.extract_color_profile(img)
            color_prof_08 = self.extract_color_profile(scale_08)

            entry = {
                "filename": f,
                "path": fp,
                "rarity": rarity,
                "r_code": r_code,
                "name": mat_name,
                "tmpl_raw": img,
                "tmpl_08": scale_08,
                "tmpl_raw_gray": img_gray,
                "tmpl_08_gray": scale_08_gray,
                "color_prof_raw": color_prof_raw,
                "color_prof_08": color_prof_08,
                "raw_shape": img.shape[:2],
                "scale_shape": scale_08.shape[:2],
                "mtime": mtime
            }
            loaded_lib.append(entry)
            by_rarity[rarity].append(entry)

        self._mat_library = loaded_lib
        self._mat_by_rarity = by_rarity
        self._mat_mtimes = new_mtimes
        return self._mat_library

    def reload_material_library(self) -> Dict[str, Any]:
        """Forces full reload of SS_materials/ reference library."""
        self.load_material_library(force=True)
        return self.get_material_library_stats()

    def has_material_library(self) -> bool:
        """Returns True if any reference material templates are loaded."""
        return len(self._mat_library) > 0

    def get_material_library_stats(self) -> Dict[str, Any]:
        """Returns statistics of loaded reference material templates."""
        rc = {r: len(self._mat_by_rarity.get(r, [])) for r in ["Common", "Uncommon", "Rare", "Legendary", "Immortal"]}
        total = sum(rc.values())
        status_str = f"Active ({total} templates loaded)" if total > 0 else "Empty (0 templates in SS_materials/)"
        return {
            "total": total,
            "rarity_counts": rc,
            "loaded": total > 0,
            "status_text": status_str
        }

    # ---------------------------------------------------------
    # Rarity Corner Border Classifier for Materials
    # ---------------------------------------------------------
    def classify_slot_rarity(self, slot_bgr: np.ndarray, corner_size: int = 10) -> Dict[str, Any]:
        """
        Classifies slot rarity border using 3 corners (TL, TR, BL).
        Supports: Common, Uncommon, Rare, Legendary, Immortal.
        """
        if slot_bgr is None or slot_bgr.size == 0:
            return {"rarity": "Common", "confidence": 0.0}

        h, w = slot_bgr.shape[:2]
        cw = min(w // 3, max(4, int(corner_size)))
        ch = min(h // 3, max(4, int(corner_size)))

        corners_def = {
            "tl": (1, 1, cw, ch),
            "tr": (max(0, w - cw - 1), 1, cw, ch),
            "bl": (1, max(0, h - ch - 1), cw, ch)
        }

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
            if np.sum(imm_mask) / n_total >= 0.20:
                votes["Immortal"] += 1
            elif np.sum(leg_mask) / n_total >= 0.25:
                votes["Legendary"] += 1
            elif np.sum(rare_mask) / n_total >= 0.25:
                votes["Rare"] += 1
            elif np.sum(uncom_mask) / n_total >= 0.25:
                votes["Uncommon"] += 1
            else:
                m_b, m_g, m_r = patch.mean(axis=(0, 1))
                if m_b > m_g + 15 and m_b > m_r + 20:
                    votes["Rare"] += 1
                elif m_g > m_b + 15 and m_g > m_r + 15:
                    votes["Uncommon"] += 1
                elif m_r > m_b + 25 and m_r > m_g + 10:
                    votes["Legendary"] += 1
                else:
                    votes["Common"] += 1

        dominant_rarity = max(votes, key=votes.get)
        total_votes = sum(votes.values())
        overall_conf = votes[dominant_rarity] / max(1, total_votes)

        return {
            "rarity": dominant_rarity,
            "confidence": overall_conf
        }

    # ---------------------------------------------------------
    # Inventory Material Scanning
    # ---------------------------------------------------------
    def scan_visible_materials(
        self,
        inventory_roi: Optional[Dict[str, int]] = None,
        roi_img: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans current visible inventory grid ROI for material items registered in SS_materials/.
        Performs:
        1. Normalized template matching across loaded material templates.
        2. Color difference / fidelity verification.
        3. Rarity border verification matching the template rarity.
        4. Spatial non-maximum suppression (deduplication).
        Returns list of detected material item dictionaries with global click coordinates.
        """
        if not self.has_material_library():
            return []

        roi = inventory_roi or self.config.get("rois", {}).get("inventory_grid", {"x": 1243, "y": 639, "width": 289, "height": 122})
        if roi_img is None:
            roi_img = ScreenCapture.capture_screen(roi)

        if roi_img is None or roi_img.size == 0:
            return []

        roi_h, roi_w = roi_img.shape[:2]
        if roi_h < 30 or roi_w < 30:
            return []

        conf_threshold = threshold if threshold is not None else float(self.config.get("confidence_threshold", 0.72))
        raw_candidates = []
        roi_gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY) if len(roi_img.shape) == 3 else roi_img

        # Pass 1: Standard 0.8x scaled templates
        for ref in self._mat_library:
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

                # Skip clipped edge items
                if py < -4 or (py + th) > roi_h + 4:
                    continue

                crop_y1 = max(0, py)
                crop_y2 = min(roi_h, py + th)
                crop_x1 = max(0, px)
                crop_x2 = min(roi_w, px + tw)
                slot_crop = roi_img[crop_y1:crop_y2, crop_x1:crop_x2]
                tmpl_crop = tmpl[:crop_y2 - crop_y1, :crop_x2 - crop_x1]

                # Color Fidelity
                diff = float(np.mean(cv2.absdiff(slot_crop, tmpl_crop)))
                if diff > 38.0:
                    continue

                # Strict Anti-Recolor Color Verification
                color_prof = ref.get("color_prof_08")
                if color_prof is not None:
                    c_score, _, _ = self.verify_color_similarity(slot_crop, color_prof)
                    if c_score < 0.65:
                        continue

                # Rarity Border Verification
                rarity_res = self.classify_slot_rarity(slot_crop)
                det_rarity = rarity_res.get("rarity", "Common")
                if rarity_res.get("confidence", 0.0) >= 0.65 and det_rarity != ref["rarity"]:
                    continue

                raw_candidates.append({
                    "x": px, "y": py, "w": tw, "h": th,
                    "score": score,
                    "ref": ref
                })

        # Pass 2: Fallback to 1.0x raw templates if no matches found
        if not raw_candidates:
            for ref in self._mat_library:
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

                    diff = float(np.mean(cv2.absdiff(slot_crop, tmpl_crop)))
                    if diff > 38.0:
                        continue

                    # Strict Anti-Recolor Color Verification
                    color_prof = ref.get("color_prof_raw")
                    if color_prof is not None:
                        c_score, _, _ = self.verify_color_similarity(slot_crop, color_prof)
                        if c_score < 0.65:
                            continue

                    rarity_res = self.classify_slot_rarity(slot_crop)
                    det_rarity = rarity_res.get("rarity", "Common")
                    if rarity_res.get("confidence", 0.0) >= 0.65 and det_rarity != ref["rarity"]:
                        continue

                    raw_candidates.append({
                        "x": px, "y": py, "w": tw, "h": th,
                        "score": score,
                        "ref": ref
                    })

        # Spatial Non-Maximum Suppression (deduplicate overlapping hits within 18px)
        raw_candidates.sort(key=lambda c: c["score"], reverse=True)
        accepted = []

        for cand in raw_candidates:
            cx = cand["x"] + cand["w"] / 2.0
            cy = cand["y"] + cand["h"] / 2.0

            overlaps = False
            for acc in accepted:
                acx = acc["x"] + acc["w"] / 2.0
                acy = acc["y"] + acc["h"] / 2.0
                if abs(cx - acx) < 18 and abs(cy - acy) < 18:
                    overlaps = True
                    break

            if not overlaps:
                accepted.append(cand)

        # Sort spatially top-to-bottom, left-to-right
        accepted.sort(key=lambda c: (c["y"] // 25, c["x"]))

        # Build output list with global coordinates
        detected_materials = []
        for itm in accepted:
            ref = itm["ref"]
            gx = roi["x"] + itm["x"] + itm["w"] // 2
            gy = roi["y"] + itm["y"] + itm["h"] // 2

            detected_materials.append({
                "click_x": gx,
                "click_y": gy,
                "slot_x": itm["x"],
                "slot_y": itm["y"],
                "slot_w": itm["w"],
                "slot_h": itm["h"],
                "rarity": ref["rarity"],
                "name": ref["name"],
                "filename": ref["filename"],
                "score": itm["score"]
            })

        return detected_materials
