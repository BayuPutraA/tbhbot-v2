"""
Fast Screen & ROI Capture Module for Task Bar Hero.
Uses MSS hardware screen grabbing with thread-local contexts and direct bounding box sub-sampling.
"""
import time
import threading
import cv2
import numpy as np
import mss
from typing import Optional, Dict, Any

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None


class ScreenCapture:
    _thread_local = threading.local()
    _MSS_RETRY_COOLDOWN = 5.0

    def __init__(self):
        pass

    @classmethod
    def _get_mss(cls):
        failed_until = getattr(cls._thread_local, "failed_until", 0.0)
        if time.monotonic() < failed_until:
            return None

        sct = getattr(cls._thread_local, "sct", None)
        if sct is None:
            try:
                sct = mss.mss()
                cls._thread_local.sct = sct
            except Exception:
                cls._thread_local.sct = None
                cls._thread_local.failed_until = time.monotonic() + cls._MSS_RETRY_COOLDOWN
                return None
        return sct

    @classmethod
    def capture_screen(cls, bbox: Optional[Dict[str, int]] = None) -> np.ndarray:
        """
        Capture the entire screen or a specific bounding box {"x", "y", "width", "height"}.
        Optimized to capture ONLY the requested ROI rectangle from GPU compositor.
        Uses thread-local MSS handles so worker threads never corrupt shared GDI contexts.
        Returns BGR numpy array compatible with OpenCV.
        """
        target_w = int(bbox.get("width", 1920)) if bbox else 1920
        target_h = int(bbox.get("height", 1080)) if bbox else 1080

        # Primary: High-speed MSS capture with thread-local persistent context
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
                img = np.asarray(raw_shot)
                return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            except Exception:
                # Reset only this thread's MSS context with cooldown so recovery remains possible
                try:
                    sct.close()
                except Exception:
                    pass
                cls._thread_local.sct = None
                cls._thread_local.failed_until = time.monotonic() + cls._MSS_RETRY_COOLDOWN

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
                return cv2.cvtColor(np.asarray(pil_img), cv2.COLOR_RGB2BGR)
            except Exception:
                pass

        return np.zeros((target_h, target_w, 3), dtype=np.uint8)

    @classmethod
    def capture_roi(cls, x: int, y: int, width: int, height: int) -> np.ndarray:
        """Capture a specified rectangular region of interest directly."""
        return cls.capture_screen({"x": x, "y": y, "width": width, "height": height})

