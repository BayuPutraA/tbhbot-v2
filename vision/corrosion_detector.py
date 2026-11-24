"""
corrosion_detector.py - Dedicated Corrosion Material Detection Engine for Task Bar Hero.
Manages the customizable Corrosion Materials library (up to 15 items in SS_corrosion/),
performing high-speed multi-scale template matching across the inventory grid.
"""

import os
import json
import cv2
import numpy as np
from typing import Optional, List, Dict, Any, Tuple
from .screen import ScreenCapture


class CorrosionDetector:
    """
    Detects user-configured materials that must enter the Cube in Corrosion mode.
    Maintains a maximum 15-item customizable list defined in corrosion_manifest.json.
    """
    def __init__(
        self,
        corrosion_dir: str = "SS_corrosion",
        materials_dir: str = "SS_materials",
        manifest_path: str = "corrosion_manifest.json",
        config_data: Optional[Dict[str, Any]] = None
    ):
        self.corrosion_dir = corrosion_dir
        self.materials_dir = materials_dir
        self.manifest_path = manifest_path
        self.config = config_data or {}

        self._corrosion_library: List[Dict[str, Any]] = []
        self._corrosion_mtimes: Dict[str, float] = {}
        self._manifest_cache: List[Dict[str, Any]] = []

        if not os.path.exists(self.corrosion_dir):
            os.makedirs(self.corrosion_dir, exist_ok=True)

        self.load_corrosion_library()

    def update_config(self, config_data: Dict[str, Any]):
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

        # Saturated color mask (isolate colorful gem/item from dark background)
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
            # Neutral / monochrome item (e.g. white fang, gray stone)
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
        Strictly rejects recolored variants sharing identical geometry (e.g. Sapphires vs Rubies/Amethysts).
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

            # Hard rejection for recolored variants (e.g. Sapphire vs Amethyst/Ruby)
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
    # Manifest & Library Management (Max 15 Items)
    # ---------------------------------------------------------
    def load_manifest(self) -> List[Dict[str, Any]]:
        """Loads and returns the corrosion items manifest (enforcing 15 items max)."""
        if os.path.isfile(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    # Enforce max 15 items
                    self._manifest_cache = data[:15]
                    return self._manifest_cache
            except Exception:
                pass

        # Fallback default 15-slot manifest
        self._manifest_cache = [
            {"id": i + 1, "name": f"Corrosion Mat {i + 1}", "filename": f"c_mat_{i + 1}.png", "enabled": (i < 5)}
            for i in range(15)
        ]
        self.save_manifest(self._manifest_cache)
        return self._manifest_cache

    def save_manifest(self, items: List[Dict[str, Any]]) -> bool:
        """Saves corrosion manifest to disk (strictly max 15 items)."""
        clean_items = items[:15]
        self._manifest_cache = clean_items
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(clean_items, f, indent=2)
            self.load_corrosion_library(force=True)
            return True
        except Exception:
            return False

    def _resolve_template_path(self, filename: str) -> Optional[str]:
        """Looks up template in SS_corrosion/, SS_materials/, and assets/."""
        if not filename:
            return None
        fn = filename if filename.lower().endswith(".png") else f"{filename}.png"

        # 1. Primary: SS_corrosion/
        p1 = os.path.join(self.corrosion_dir, fn)
        if os.path.isfile(p1):
            return p1

        # 2. Secondary: SS_materials/
        p2 = os.path.join(self.materials_dir, fn)
        if os.path.isfile(p2):
            return p2

        # 3. Tertiary: assets/
        p3 = os.path.join("assets", fn)
        if os.path.isfile(p3):
            return p3

        return None

    def load_corrosion_library(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        Loads enabled corrosion templates into memory.
        Pre-scales to 0.8x for standard 100% game scale, keeping 1.0x as fallback.
        """
        manifest = self.load_manifest()
        loaded_lib = []
        new_mtimes = {}

        for item in manifest:
            if not item.get("enabled", True):
                continue

            fn = item.get("filename", "")
            fp = self._resolve_template_path(fn)
            if not fp or not os.path.isfile(fp):
                continue

            mtime = os.path.getmtime(fp)
            new_mtimes[fn] = mtime

            img = cv2.imread(fp, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                continue

            h, w = img.shape[:2]
            scale_08 = cv2.resize(
                img,
                (max(8, int(w * 0.8)), max(8, int(h * 0.8))),
                interpolation=cv2.INTER_AREA
            )

            scale_08_gray = cv2.cvtColor(scale_08, cv2.COLOR_BGR2GRAY)
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            color_prof_raw = self.extract_color_profile(img)
            color_prof_08 = self.extract_color_profile(scale_08)

            entry = {
                "id": item.get("id"),
                "name": item.get("name", fn),
                "filename": fn,
                "path": fp,
                "tmpl_raw": img,
                "tmpl_08": scale_08,
                "tmpl_raw_gray": img_gray,
                "tmpl_08_gray": scale_08_gray,
                "color_prof_raw": color_prof_raw,
                "color_prof_08": color_prof_08,
                "raw_shape": (h, w),
                "scale_shape": scale_08.shape[:2],
                "mtime": mtime
            }
            loaded_lib.append(entry)

        self._corrosion_library = loaded_lib
        self._corrosion_mtimes = new_mtimes
        return self._corrosion_library

    def reload_corrosion_library(self) -> Dict[str, Any]:
        self.load_corrosion_library(force=True)
        return self.get_corrosion_library_stats()

    def has_corrosion_library(self) -> bool:
        return len(self._corrosion_library) > 0

    def get_corrosion_library_stats(self) -> Dict[str, Any]:
        manifest = self.load_manifest()
        enabled_count = sum(1 for it in manifest if it.get("enabled", True))
        loaded_count = len(self._corrosion_library)

        items_status = []
        for it in manifest:
            fn = it.get("filename", "")
            fp = self._resolve_template_path(fn)
            loaded = bool(fp and os.path.isfile(fp))
            size_str = ""
            if loaded:
                try:
                    img = cv2.imread(fp)
                    if img is not None:
                        size_str = f"{img.shape[1]}x{img.shape[0]}"
                except Exception:
                    pass
            items_status.append({
                "id": it.get("id"),
                "name": it.get("name"),
                "filename": fn,
                "enabled": it.get("enabled", True),
                "loaded": loaded,
                "size_str": size_str
            })

        return {
            "total_items": len(manifest),
            "enabled_items": enabled_count,
            "loaded_templates": loaded_count,
            "items": items_status
        }

    # ---------------------------------------------------------
    # Inventory Scanning for Corrosion Materials
    # ---------------------------------------------------------
    def scan_visible_corrosion_materials(
        self,
        inventory_roi: Optional[Dict[str, int]] = None,
        roi_img: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans current inventory grid ROI for any enabled Corrosion materials.
        Returns list of detected items with click coordinates and template info.
        """
        if not self.has_corrosion_library():
            return []

        roi = inventory_roi or self.config.get("rois", {}).get("inventory_grid", {"x": 1243, "y": 639, "width": 289, "height": 122})
        if roi_img is None:
            roi_img = ScreenCapture.capture_screen(roi)

        if roi_img is None or roi_img.size == 0:
            return []

        roi_h, roi_w = roi_img.shape[:2]
        if roi_h < 30 or roi_w < 30:
            return []

        conf_threshold = threshold if threshold is not None else float(self.config.get("confidence_threshold", 0.68))
        color_threshold = float(self.config.get("corrosion_color_threshold", 0.65))
        raw_candidates = []
        roi_gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY) if len(roi_img.shape) == 3 else roi_img

        # Multi-scale matching: 1.0x raw (exact user snip) and 0.8x scaled
        for ref in self._corrosion_library:
            scales = [
                ("raw", ref["tmpl_raw"], ref["tmpl_raw_gray"], ref.get("color_prof_raw")),
                ("scale_08", ref["tmpl_08"], ref["tmpl_08_gray"], ref.get("color_prof_08"))
            ]

            for s_name, tmpl, tmpl_gray, color_prof in scales:
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

                    diff = float(np.mean(cv2.absdiff(slot_crop, tmpl_crop)))
                    if diff > 55.0:
                        continue

                    # Strict Anti-Recolor Color Verification (separates same-shape items of different color)
                    if color_prof is not None:
                        color_score, hue_diff, chroma_dist = self.verify_color_similarity(slot_crop, color_prof)
                        if color_score < color_threshold:
                            continue
                    else:
                        color_score = 1.0
                        hue_diff = 0.0
                        chroma_dist = 0.0

                    combined_score = 0.5 * score + 0.5 * color_score

                    raw_candidates.append({
                        "x": px, "y": py, "w": tw, "h": th,
                        "score": combined_score,
                        "shape_score": score,
                        "color_score": color_score,
                        "hue_diff": hue_diff,
                        "chroma_dist": chroma_dist,
                        "scale": s_name,
                        "ref": ref
                    })

        if not raw_candidates:
            return []

        # Spatial Non-Maximum Suppression (deduplicate within 18px)
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

        # Sort top-to-bottom, left-to-right
        accepted.sort(key=lambda c: (c["y"] // 25, c["x"]))

        # Build output list with global click coordinates
        detected_items = []
        for itm in accepted:
            ref = itm["ref"]
            gx = roi["x"] + itm["x"] + itm["w"] // 2
            gy = roi["y"] + itm["y"] + itm["h"] // 2

            detected_items.append({
                "id": ref["id"],
                "name": ref["name"],
                "filename": ref["filename"],
                "click_x": gx,
                "click_y": gy,
                "slot_x": itm["x"],
                "slot_y": itm["y"],
                "slot_w": itm["w"],
                "slot_h": itm["h"],
                "score": itm["score"],
                "shape_score": itm.get("shape_score", itm["score"]),
                "color_score": itm.get("color_score", 1.0)
            })

        return detected_items
