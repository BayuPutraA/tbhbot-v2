"""
VisionEngine facade and coordinator module for Task Bar Hero.
Integrates ScreenCapture, TemplateMatcher, ChestDetector, GearDetector, and OverlayRenderer.
Provides complete backwards compatibility for existing code.
"""
from typing import Optional, List, Tuple, Dict, Any
import numpy as np

from .screen import ScreenCapture
from .template_matcher import TemplateMatcher, TEMPLATE_MANIFEST
from .chest_detector import ChestDetector
from .gear_detector import GearDetector
from .material_detector import MaterialDetector
from .corrosion_detector import CorrosionDetector
from .overlay import OverlayRenderer


class VisionEngine:
    def __init__(
        self,
        config_data: Optional[Dict[str, Any]] = None,
        assets_dir: str = "assets",
        ss_dir: str = "SS",
        materials_dir: str = "SS_materials",
        corrosion_dir: str = "SS_corrosion"
    ):
        self.assets_dir = assets_dir
        self.ss_dir = ss_dir
        self.materials_dir = materials_dir
        self.corrosion_dir = corrosion_dir
        self.config = config_data or {}

        # Specialized sub-engines
        self.screen = ScreenCapture()
        self.matcher = TemplateMatcher(assets_dir=self.assets_dir, config_data=self.config)
        self.chest_detector = ChestDetector(matcher=self.matcher, config=self.config)
        self.gear_detector = GearDetector(
            matcher=self.matcher,
            config=self.config,
            assets_dir=self.assets_dir,
            ss_dir=self.ss_dir
        )
        self.material_detector = MaterialDetector(
            matcher=self.matcher,
            config=self.config,
            materials_dir=self.materials_dir
        )
        self.corrosion_detector = CorrosionDetector(
            corrosion_dir=self.corrosion_dir,
            materials_dir=self.materials_dir,
            config_data=self.config
        )
        self.overlay_renderer = OverlayRenderer(
            chest_detector=self.chest_detector,
            gear_detector=self.gear_detector,
            material_detector=self.material_detector,
            corrosion_detector=self.corrosion_detector,
            config=self.config
        )

    # ---------------------------------------------------------
    # Backward-compatible property views
    # ---------------------------------------------------------
    @property
    def _template_cache(self) -> Dict[str, np.ndarray]:
        return self.matcher._template_cache

    @property
    def _template_mtimes(self) -> Dict[str, float]:
        return self.matcher._template_mtimes

    @property
    def _ref_gear_library(self) -> List[Dict[str, Any]]:
        return self.gear_detector._ref_gear_library

    @property
    def _ref_gear_by_level(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.gear_detector._ref_gear_by_level

    @property
    def _ref_gear_mtimes(self) -> Dict[str, float]:
        return self.gear_detector._ref_gear_mtimes

    # ---------------------------------------------------------
    # Configuration & Cache Management
    # ---------------------------------------------------------
    def update_config(self, config_data: Dict[str, Any]):
        """Update live configuration across all sub-components."""
        self.config = config_data
        self.matcher.config = config_data
        self.chest_detector.update_config(config_data)
        self.gear_detector.update_config(config_data)
        self.material_detector.update_config(config_data)
        self.corrosion_detector.update_config(config_data)
        self.overlay_renderer.update_config(config_data)

    def clear_cache(self):
        """Clear template cache and check for reference library updates."""
        self.matcher.clear_cache()
        self.gear_detector.load_reference_gear_library(force=True)
        self.material_detector.load_material_library(force=True)
        self.corrosion_detector.load_corrosion_library(force=True)

    # ---------------------------------------------------------
    # Low Level (Lv. 50) Gear Library & Stash Scanner (Powered by GearDetector)
    # ---------------------------------------------------------
    def load_lvl50_library(self, force: bool = False) -> List[Dict[str, Any]]:
        self.gear_detector.load_reference_gear_library(force=force)
        return self.gear_detector._ref_gear_by_level.get("50", [])

    def reload_lvl50_library(self) -> Dict[str, Any]:
        self.gear_detector.reload_reference_gear_library()
        return self.get_lvl50_library_stats()

    def has_lvl50_library(self) -> bool:
        return len(self.gear_detector._ref_gear_by_level.get("50", [])) > 0

    def get_lvl50_library_stats(self) -> Dict[str, Any]:
        l50_count = len(self.gear_detector._ref_gear_by_level.get("50", []))
        return {
            "total_items": l50_count,
            "loaded_templates": l50_count,
            "enabled_items": l50_count,
            "status_text": f"✅ {l50_count} Lv. 50 Reference Templates in SS/"
        }

    def scan_visible_lvl50_items(
        self,
        inventory_roi: Optional[Dict[str, int]] = None,
        roi_img: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Unified Lv. 50 scan powered directly by GearDetector and SS/ reference library.
        Filters strictly for level '50' with cross-bracket collision guards.
        """
        ref_items = self.gear_detector.scan_visible_inventory(
            inventory_roi=inventory_roi,
            roi_img=roi_img,
            threshold=threshold,
            level_filter="50"
        )
        for itm in ref_items:
            if "name" not in itm:
                itm["name"] = itm.get("gear_name", "gear")
        return ref_items

    def scan_stash_for_lvl50(
        self,
        stash_roi: Optional[Dict[str, int]] = None,
        roi_img: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        roi = stash_roi or self.config.get("rois", {}).get("stash_grid")
        if not roi:
            roi = {"x": 550, "y": 280, "width": 460, "height": 450}

        detected = self.scan_visible_lvl50_items(inventory_roi=roi, roi_img=roi_img, threshold=threshold)

        by_rarity = {
            "Common": [],
            "Uncommon": [],
            "Rare": [],
            "Legendary": [],
            "Immortal": []
        }
        for itm in detected:
            r = itm.get("rarity", "Common")
            if r in by_rarity:
                by_rarity[r].append(itm)

        ready_rarity = None
        for r_name in ["Rare", "Uncommon", "Common"]:
            if len(by_rarity[r_name]) >= 9:
                ready_rarity = r_name
                break

        counts = {r: len(by_rarity[r]) for r in by_rarity}
        return {
            "total": len(detected),
            "total_detected": len(detected),
            "by_rarity": by_rarity,
            "counts": counts,
            "is_ready": ready_rarity is not None,
            "ready_rarity": ready_rarity,
            "items": detected
        }

    # ---------------------------------------------------------
    # Corrosion Materials Library (Max 15 Items)
    # ---------------------------------------------------------
    def load_corrosion_library(self, force: bool = False) -> List[Dict[str, Any]]:
        return self.corrosion_detector.load_corrosion_library(force=force)

    def reload_corrosion_library(self) -> Dict[str, Any]:
        return self.corrosion_detector.reload_corrosion_library()

    def has_corrosion_library(self) -> bool:
        return self.corrosion_detector.has_corrosion_library()

    def get_corrosion_library_stats(self) -> Dict[str, Any]:
        return self.corrosion_detector.get_corrosion_library_stats()

    def scan_visible_corrosion_materials(
        self,
        inventory_roi: Optional[Dict[str, int]] = None,
        roi_img: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        return self.corrosion_detector.scan_visible_corrosion_materials(
            inventory_roi=inventory_roi,
            roi_img=roi_img,
            threshold=threshold
        )

    # ---------------------------------------------------------
    # Reference Material Library
    # ---------------------------------------------------------
    def load_material_library(self, force: bool = False) -> List[Dict[str, Any]]:
        return self.material_detector.load_material_library(force=force)

    def reload_material_library(self) -> Dict[str, Any]:
        return self.material_detector.reload_material_library()

    def has_material_library(self) -> bool:
        return self.material_detector.has_material_library()

    def get_material_library_stats(self) -> Dict[str, Any]:
        return self.material_detector.get_material_library_stats()

    def scan_visible_materials(
        self,
        inventory_roi: Optional[Dict[str, int]] = None,
        roi_img: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        return self.material_detector.scan_visible_materials(
            inventory_roi=inventory_roi,
            roi_img=roi_img,
            threshold=threshold
        )

    # ---------------------------------------------------------
    # Reference Gear Library
    # ---------------------------------------------------------
    def load_reference_gear_library(self, force: bool = False) -> List[Dict[str, Any]]:
        return self.gear_detector.load_reference_gear_library(force=force)

    def reload_reference_gear_library(self) -> Dict[str, Any]:
        return self.gear_detector.reload_reference_gear_library()

    def has_reference_gear_library(self) -> bool:
        return self.gear_detector.has_reference_gear_library()

    def get_reference_library_stats(self) -> Dict[str, Any]:
        return self.gear_detector.get_reference_library_stats()

    def match_reference_gear(
        self,
        window_bgr: np.ndarray,
        level_hint: Optional[str] = None,
        threshold: float = 0.78,
        max_color_diff: float = 26.0
    ) -> Optional[Dict[str, Any]]:
        return self.gear_detector.match_reference_gear(
            window_bgr=window_bgr,
            level_hint=level_hint,
            threshold=threshold,
            max_color_diff=max_color_diff
        )

    # ---------------------------------------------------------
    # Screen Capture
    # ---------------------------------------------------------
    def capture_screen(self, bbox: Optional[Dict[str, int]] = None) -> np.ndarray:
        return ScreenCapture.capture_screen(bbox)

    def capture_roi(self, x: int, y: int, width: int, height: int) -> np.ndarray:
        return ScreenCapture.capture_roi(x, y, width, height)

    # ---------------------------------------------------------
    # Template Matching
    # ---------------------------------------------------------
    def load_template(self, template_name: str) -> Optional[np.ndarray]:
        return self.matcher.load_template(template_name)

    def template_exists(self, template_name: str) -> bool:
        return self.matcher.template_exists(template_name)

    def get_template_status(self, template_filename: str) -> Tuple[bool, str, Tuple[int, int]]:
        return self.matcher.get_template_status(template_filename)

    def find_template(
        self,
        haystack: np.ndarray,
        template_name_or_img: Any,
        threshold: Optional[float] = None,
        scales: Optional[List[float]] = None,
        grayscale: bool = True
    ) -> Optional[Tuple[int, int, int, int, float]]:
        return self.matcher.find_template(
            haystack=haystack,
            template_name_or_img=template_name_or_img,
            threshold=threshold,
            scales=scales,
            grayscale=grayscale
        )

    def find_all_templates(
        self,
        haystack: np.ndarray,
        template_name_or_img: Any,
        threshold: Optional[float] = None,
        min_distance: int = 20,
        scales: Optional[List[float]] = None,
        grayscale: bool = True
    ) -> List[Tuple[int, int, int, int, float]]:
        return self.matcher.find_all_templates(
            haystack=haystack,
            template_name_or_img=template_name_or_img,
            threshold=threshold,
            min_distance=min_distance,
            scales=scales,
            grayscale=grayscale
        )

    # ---------------------------------------------------------
    # Inventory Anchor & Classification
    # ---------------------------------------------------------
    def get_inventory_roi(self) -> Dict[str, int]:
        return self.gear_detector.get_inventory_roi()

    def get_chest_roi(self) -> Optional[Dict[str, int]]:
        return self.config.get("rois", {}).get("chest_region")

    def classify_slot_border_rarity(self, slot_bgr: np.ndarray) -> str:
        return self.gear_detector.classify_slot_border_rarity(slot_bgr)

    def classify_multi_corner_rarity(self, slot_bgr: np.ndarray, corner_size: int = 10) -> Dict[str, Any]:
        return self.gear_detector.classify_multi_corner_rarity(slot_bgr, corner_size=corner_size)

    def detect_slot_level(self, slot_bgr: np.ndarray, threshold: float = 0.65, expected_lv: Optional[str] = None) -> Tuple[Optional[str], float]:
        return self.gear_detector.detect_slot_level(slot_bgr, threshold=threshold, expected_lv=expected_lv)

    def scan_visible_inventory(
        self,
        inventory_roi: Optional[Dict[str, int]] = None,
        min_y_offset: int = 0,
        roi_img: Optional[np.ndarray] = None,
        threshold: Optional[float] = None,
        level_filter: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        return self.gear_detector.scan_visible_inventory(
            inventory_roi=inventory_roi,
            min_y_offset=min_y_offset,
            roi_img=roi_img,
            threshold=threshold,
            level_filter=level_filter
        )

    # ---------------------------------------------------------
    # Chest Detection
    # ---------------------------------------------------------
    def detect_chest_state(self, chest_roi: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        return self.chest_detector.detect_chest_state(chest_roi=chest_roi)

    def is_chest_present(
        self,
        chest_roi: Optional[Dict[str, int]] = None,
        check_empty: bool = True
    ) -> Tuple[bool, Optional[Tuple[int, int]]]:
        return self.chest_detector.is_chest_present(chest_roi=chest_roi, check_empty=check_empty)

    def is_empty_ground_confirmed(self, chest_roi: Optional[Dict[str, int]] = None, threshold: float = 0.82) -> bool:
        return self.chest_detector.is_empty_ground_confirmed(chest_roi=chest_roi, threshold=threshold)

    def is_inventory_full(self, chest_roi: Optional[Dict[str, int]] = None) -> bool:
        return self.chest_detector.is_inventory_full(chest_roi=chest_roi)

    # ---------------------------------------------------------
    # Scroll Helpers & Overlap Calculation
    # ---------------------------------------------------------
    def detect_vertical_scroll_shift(self, prev_roi_img: np.ndarray, curr_roi_img: np.ndarray) -> int:
        return self.gear_detector.detect_vertical_scroll_shift(prev_roi_img, curr_roi_img)

    def detect_vertical_scroll_offset(self, prev_roi_img: np.ndarray, curr_roi_img: np.ndarray) -> int:
        return self.gear_detector.detect_vertical_scroll_offset(prev_roi_img, curr_roi_img)

    def is_inventory_at_bottom(self, prev_roi_img: np.ndarray, curr_roi_img: np.ndarray, threshold: float = 1.5) -> bool:
        return self.gear_detector.is_inventory_at_bottom(prev_roi_img, curr_roi_img, threshold=threshold)

    # ---------------------------------------------------------
    # Visual Debugger Image Overlay
    # ---------------------------------------------------------
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
        return self.overlay_renderer.render_debug_overlay(
            inv_roi=inv_roi,
            chest_roi=chest_roi,
            mode=mode,
            show_gears=show_gears,
            show_materials=show_materials,
            show_corrosion=show_corrosion,
            show_lvl50=show_lvl50,
            **kwargs
        )
