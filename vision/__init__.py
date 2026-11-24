"""
Vision package for Task Bar Hero.
"""
from .engine import VisionEngine
from .template_matcher import TEMPLATE_MANIFEST, TemplateMatcher
from .screen import ScreenCapture
from .chest_detector import ChestDetector
from .gear_detector import GearDetector
from .material_detector import MaterialDetector
from .corrosion_detector import CorrosionDetector
from .overlay import OverlayRenderer

__all__ = [
    "VisionEngine",
    "TEMPLATE_MANIFEST",
    "TemplateMatcher",
    "ScreenCapture",
    "ChestDetector",
    "GearDetector",
    "MaterialDetector",
    "CorrosionDetector",
    "OverlayRenderer",
]
