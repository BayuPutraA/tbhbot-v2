"""
Fast Screen & ROI Capture Module for Task Bar Hero.
Uses MSS hardware screen grabbing with direct bounding box sub-sampling for maximum FPS.
"""
import cv2
import numpy as np
import mss
from typing import Optional, Dict, Any

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None


class ScreenCapture:
    _mss_instance = None
    _mss_failed = False

    def __init__(self):
        pass

    @classmethod
    def _get_mss(cls):
        if cls._mss_instance is None and not cls._mss_failed:
            try:
                cls._mss_instance = mss.mss()
            except Exception:
                cls._mss_failed = True
        return cls._mss_instance

    @classmethod
    def capture_screen(cls, bbox: Optional[Dict[str, int]] = None) -> np.ndarray:
        """
        Capture the entire screen or a specific bounding box {"x", "y", "width", "height"}.
        Optimized to capture ONLY the requested ROI rectangle from GPU compositor.
        Returns BGR numpy array compatible with OpenCV.
        """
        target_w = int(bbox.get("width", 1920)) if bbox else 1920
        target_h = int(bbox.get("height", 1080)) if bbox else 1080

        # Primary: High-speed MSS capture with persistent context
        if not cls._mss_failed:
            sct = cls._get_mss()
            if sct is not None:
                try:
                    if bbox and bbox.get("width", 0) > 0 and bbox.get("height", 0) > 0:
                        monitor = {
                            "top": int(bbox.get("y", 0)),
                            "left": int(bbox.get("x", 0)),
                            "width": target_w,
                            "height": target_h
                        }
                    else:
                        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

                    raw_shot = sct.grab(monitor)
                    img = np.array(raw_shot)
                    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                except Exception:
                    # Mark MSS as failed so we don't keep repeating failed GDI BitBlt calls
                    cls._mss_failed = True
                    if cls._mss_instance is not None:
                        try:
                            cls._mss_instance.close()
                        except Exception:
                            pass
                        cls._mss_instance = None

        # Fallback: PIL ImageGrab (direct fallback without repeated BitBlt exceptions)
        if ImageGrab is not None:
            try:
                if bbox and bbox.get("width", 0) > 0 and bbox.get("height", 0) > 0:
                    x = int(bbox.get("x", 0))
                    y = int(bbox.get("y", 0))
                    box = (x, y, x + target_w, y + target_h)
                    pil_img = ImageGrab.grab(bbox=box)
                else:
                    pil_img = ImageGrab.grab()
                return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception:
                pass

        return np.zeros((target_h, target_w, 3), dtype=np.uint8)

    @classmethod
    def capture_roi(cls, x: int, y: int, width: int, height: int) -> np.ndarray:
        """Capture a specified rectangular region of interest directly."""
        return cls.capture_screen({"x": x, "y": y, "width": width, "height": height})

