"""
Template Matching & Asset Management Module for Task Bar Hero.
Supports multi-scale normalized cross-correlation, asset caching, and dynamic snip reloading.
"""
import os
import cv2
import numpy as np
from typing import Optional, List, Tuple, Dict, Any

# Central Registry of Recognized System Templates
TEMPLATE_MANIFEST = [
    # Navigation & Chests
    {
        "key": "chest_btn",
        "filename": "chest_btn.png",
        "name": "Chest Button",
        "desc": "Bottom bar chest icon",
        "category": "Navigation & Chests",
        "aliases": []
    },
    {
        "key": "chest_blue",
        "filename": "chest_blue.png",
        "name": "Blue Chest",
        "desc": "Blue chest available to open on floor",
        "category": "Navigation & Chests",
        "aliases": []
    },
    {
        "key": "chest_brown",
        "filename": "chest_brown.png",
        "name": "Brown Chest",
        "desc": "Brown/wooden chest available to open on floor",
        "category": "Navigation & Chests",
        "aliases": []
    },
    {
        "key": "inv_full_blue",
        "filename": "inv_full_blue.png",
        "name": "Inven Full (Blue Chest)",
        "desc": "Inven Full indicator over blue chest",
        "category": "Navigation & Chests",
        "aliases": ["inv_full_text.png"]
    },
    {
        "key": "inv_full_brown",
        "filename": "inv_full_brown.png",
        "name": "Inven Full (Brown Chest)",
        "desc": "Inven Full indicator over brown chest",
        "category": "Navigation & Chests",
        "aliases": []
    },
    {
        "key": "chest_pile",
        "filename": "chest_pile.png",
        "name": "Chest Pile (Legacy)",
        "desc": "Unopened chest on ground",
        "category": "Navigation & Chests",
        "aliases": ["chest.png", "chest_stack.png", "chest_single.png"]
    },
    {
        "key": "empty_floor",
        "filename": "empty_floor.png",
        "name": "Empty Floor",
        "desc": "Empty chest spot when 0 chests remain",
        "category": "Navigation & Chests",
        "aliases": ["chest_empty.png"]
    },
    {
        "key": "inv_full",
        "filename": "inv_full.png",
        "name": "Inventory Full",
        "desc": "Inventory full warning popup/text",
        "category": "Navigation & Chests",
        "aliases": ["inventory_full.png"]
    },
    {
        "key": "inv_tab_btn",
        "filename": "inv_tab_btn.png",
        "name": "Inventory Tab Button",
        "desc": "Orange 'Inventory' tab button below grid",
        "category": "Navigation & Chests",
        "aliases": []
    },

    # Cube Controls
    {
        "key": "cube_btn",
        "filename": "cube_btn.png",
        "name": "Cube Button",
        "desc": "Bottom bar Cube icon",
        "category": "Cube Controls",
        "aliases": []
    },
    {
        "key": "tier_dropdown",
        "filename": "tier_dropdown.png",
        "name": "Tier Dropdown",
        "desc": "Top-right level selector box in Cube window",
        "category": "Cube Controls",
        "aliases": ["cube_dropdown.png"]
    },
    {
        "key": "tier_65_80",
        "filename": "tier_65_80.png",
        "name": "Option Lv.65~80",
        "desc": "Lv.65~80 option in dropdown",
        "category": "Cube Controls",
        "aliases": []
    },
    {
        "key": "tier_80_90",
        "filename": "tier_80_90.png",
        "name": "Option Lv.80~90",
        "desc": "Lv.80~90 option in dropdown",
        "category": "Cube Controls",
        "aliases": []
    },
    {
        "key": "tier_50",
        "filename": "tier_50.png",
        "name": "Option Lv.50",
        "desc": "Lv.50 option in dropdown",
        "category": "Cube Controls",
        "aliases": ["tier_50_option.png"]
    },
    {
        "key": "synth_btn",
        "filename": "synth_btn.png",
        "name": "Synthesize Button",
        "desc": "Synthesize button to the right of Auto Fill",
        "category": "Cube Controls",
        "aliases": ["cube_synth_btn.png", "synth_confirm.png"]
    },
    {
        "key": "synth_return_btn",
        "filename": "synth_return_btn.png",
        "name": "Synthesis Return Button",
        "desc": "Return/retrieve button with curved arrow above Auto Input",
        "category": "Cube Controls",
        "aliases": ["synth_return_full.png"]
    },

    # Item Controls
    {
        "key": "lock_icon",
        "filename": "lock_icon.png",
        "name": "Lock Icon",
        "desc": "Locked item indicator in slot corner",
        "category": "Item Controls",
        "aliases": []
    },
    {
        "key": "inv_sort_btn",
        "filename": "inv_sort_btn.png",
        "name": "Inventory Sort Button",
        "desc": "Sort button to organize inventory items before scroll",
        "category": "Item Controls",
        "optional": True,
        "aliases": ["sort_btn.png"]
    },
]


class TemplateMatcher:
    def __init__(self, assets_dir: str = "assets", config_data: Optional[Dict[str, Any]] = None):
        self.assets_dir = assets_dir
        self.config = config_data or {}
        self._template_cache: Dict[str, np.ndarray] = {}
        self._template_cache_gray: Dict[str, np.ndarray] = {}
        self._template_mtimes: Dict[str, float] = {}

        if not os.path.exists(self.assets_dir):
            os.makedirs(self.assets_dir, exist_ok=True)

    def _resolve_template_path(self, template_name: str) -> Optional[str]:
        """Finds file path for template or its registered aliases."""
        clean_name = template_name if template_name.endswith(".png") else template_name + ".png"
        direct_path = os.path.join(self.assets_dir, clean_name)
        if os.path.isfile(direct_path):
            return direct_path

        for item in TEMPLATE_MANIFEST:
            if item["filename"] == clean_name or clean_name in item.get("aliases", []):
                p = os.path.join(self.assets_dir, item["filename"])
                if os.path.isfile(p):
                    return p
                for a in item.get("aliases", []):
                    ap = os.path.join(self.assets_dir, a)
                    if os.path.isfile(ap):
                        return ap

        return None

    def load_template(self, template_name: str, grayscale: bool = False) -> Optional[np.ndarray]:
        """
        Loads template dynamically from disk with timestamp caching.
        Reloads immediately if the file was modified on disk.
        Caches both BGR and Grayscale variants for high-performance matching.
        """
        path = self._resolve_template_path(template_name)
        if not path or not os.path.isfile(path):
            return None

        mtime = os.path.getmtime(path)
        if template_name in self._template_cache:
            if self._template_mtimes.get(template_name, 0) == mtime:
                if grayscale:
                    if template_name not in self._template_cache_gray:
                        self._template_cache_gray[template_name] = cv2.cvtColor(
                            self._template_cache[template_name], cv2.COLOR_BGR2GRAY
                        )
                    return self._template_cache_gray[template_name]
                return self._template_cache[template_name]

        template = cv2.imread(path, cv2.IMREAD_COLOR)
        if template is not None:
            self._template_cache[template_name] = template
            self._template_cache_gray[template_name] = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            self._template_mtimes[template_name] = mtime
            if grayscale:
                return self._template_cache_gray[template_name]
        return template

    def template_exists(self, template_name: str) -> bool:
        """Check if template exists on disk."""
        return self._resolve_template_path(template_name) is not None

    def get_template_status(self, template_filename: str) -> Tuple[bool, str, Tuple[int, int]]:
        """Returns (is_loaded, status_str, (width, height)) for GUI tables."""
        path = self._resolve_template_path(template_filename)
        if path and os.path.isfile(path):
            img = self.load_template(template_filename)
            if img is not None:
                h, w = img.shape[:2]
                return True, f"✅ Loaded ({w}x{h})", (w, h)
        return False, "❌ Missing", (0, 0)

    def find_template(
        self,
        haystack: np.ndarray,
        template_name_or_img: Any,
        threshold: Optional[float] = None,
        scales: Optional[List[float]] = None,
        grayscale: bool = True
    ) -> Optional[Tuple[int, int, int, int, float]]:
        """
        Finds best occurrence of template inside haystack.
        Returns (x, y, width, height, confidence) or None.
        """
        if threshold is None:
            threshold = float(self.config.get("confidence_threshold", 0.78))
        if scales is None:
            scales = [0.95, 1.0, 1.05]

        if haystack is None or template_name_or_img is None:
            return None

        if grayscale:
            hay_proc = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY) if len(haystack.shape) == 3 else haystack
            if isinstance(template_name_or_img, str):
                tmpl_proc = self.load_template(template_name_or_img, grayscale=True)
            else:
                tmpl_proc = cv2.cvtColor(template_name_or_img, cv2.COLOR_BGR2GRAY) if len(template_name_or_img.shape) == 3 else template_name_or_img
        else:
            hay_proc = haystack
            tmpl_proc = self.load_template(template_name_or_img, grayscale=False) if isinstance(template_name_or_img, str) else template_name_or_img

        if tmpl_proc is None or hay_proc is None:
            return None

        hh, hw = hay_proc.shape[:2]
        orig_th, orig_tw = tmpl_proc.shape[:2]

        best_match = None
        best_val = -1.0

        for sc in scales:
            if sc == 1.0:
                tw, th = orig_tw, orig_th
                scaled_tmpl = tmpl_proc
            else:
                tw = max(4, int(round(orig_tw * sc)))
                th = max(4, int(round(orig_th * sc)))
                if th > hh or tw > hw:
                    continue
                scaled_tmpl = cv2.resize(tmpl_proc, (tw, th), interpolation=cv2.INTER_LINEAR)

            if th > hh or tw > hw:
                continue

            res = cv2.matchTemplate(hay_proc, scaled_tmpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val > best_val and max_val >= threshold:
                best_val = float(max_val)
                best_match = (max_loc[0], max_loc[1], tw, th, best_val)

        return best_match

    def find_all_templates(
        self,
        haystack: np.ndarray,
        template_name_or_img: Any,
        threshold: Optional[float] = None,
        min_distance: int = 20,
        scales: Optional[List[float]] = None,
        grayscale: bool = True
    ) -> List[Tuple[int, int, int, int, float]]:
        """
        Finds all occurrences of template with multi-scale matching and Non-Maximum Suppression.
        Returns list of (x, y, w, h, confidence).
        """
        if threshold is None:
            threshold = float(self.config.get("confidence_threshold", 0.78))
        if scales is None:
            scales = [0.95, 1.0, 1.05]

        if haystack is None or template_name_or_img is None:
            return []

        if grayscale:
            hay_proc = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY) if len(haystack.shape) == 3 else haystack
            if isinstance(template_name_or_img, str):
                tmpl_proc = self.load_template(template_name_or_img, grayscale=True)
            else:
                tmpl_proc = cv2.cvtColor(template_name_or_img, cv2.COLOR_BGR2GRAY) if len(template_name_or_img.shape) == 3 else template_name_or_img
        else:
            hay_proc = haystack
            tmpl_proc = self.load_template(template_name_or_img, grayscale=False) if isinstance(template_name_or_img, str) else template_name_or_img

        if tmpl_proc is None or hay_proc is None:
            return []

        hh, hw = hay_proc.shape[:2]
        orig_th, orig_tw = tmpl_proc.shape[:2]

        all_raw_matches = []

        for sc in scales:
            if sc == 1.0:
                tw, th = orig_tw, orig_th
                scaled_tmpl = tmpl_proc
            else:
                tw = max(4, int(round(orig_tw * sc)))
                th = max(4, int(round(orig_th * sc)))
                if th > hh or tw > hw:
                    continue
                scaled_tmpl = cv2.resize(tmpl_proc, (tw, th), interpolation=cv2.INTER_LINEAR)

            if th > hh or tw > hw:
                continue

            res = cv2.matchTemplate(hay_proc, scaled_tmpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= threshold)
            for pt in zip(*loc[::-1]):
                score = float(res[pt[1], pt[0]])
                all_raw_matches.append((pt[0], pt[1], tw, th, score))

        if not all_raw_matches:
            return []

        # Non-maximum suppression by center distance
        all_raw_matches.sort(key=lambda m: m[4], reverse=True)
        filtered = []
        for m in all_raw_matches:
            mx, my, mw, mh, score = m
            cx, cy = mx + mw / 2, my + mh / 2
            overlap = False
            for f in filtered:
                fx, fy, fw, fh, _ = f
                fcx, fcy = fx + fw / 2, fy + fh / 2
                if np.hypot(cx - fcx, cy - fcy) < min_distance:
                    overlap = True
                    break
            if not overlap:
                filtered.append(m)

        return filtered

    def clear_cache(self):
        """Clears cached templates in memory."""
        self._template_cache.clear()
        self._template_cache_gray.clear()
        self._template_mtimes.clear()
