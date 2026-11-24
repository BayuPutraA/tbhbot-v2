"""
qt_snipper.py - High-precision GPU-accelerated Screen Snipping Overlay for Task Bar Hero.
Uses PySide6 to display a zero-lag translucent fullscreen overlay with crosshairs,
live dimension tooltips, and instant cropping directly into assets/, SS/, or SS_materials/.
"""

import os
import json
from typing import Optional, Callable, Dict, Any, Tuple
import cv2
import numpy as np
import mss

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QImage, QPixmap


class QtScreenSnipper(QtWidgets.QWidget):
    """
    High-performance fullscreen snipping tool.
    Freezes the screen with a dimmed overlay, provides live crosshair guides,
    and supports rectangle cropping or single-point coordinate selection.
    """
    def __init__(
        self,
        mode: str = "roi",  # 'roi', 'point', 'template'
        title: str = "Select Region",
        template_filename: Optional[str] = None,
        save_dir: Optional[str] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        config_path: str = "config.json"
    ):
        super().__init__()
        self.mode = mode
        self.title_text = title
        self.template_filename = template_filename
        self.save_dir = save_dir
        self.on_complete = on_complete
        self.config_path = config_path

        # 1. Capture screen before opening overlay
        self.clean_bgr, self.screen_rect = self._capture_desktop()
        self.clean_rgb = cv2.cvtColor(self.clean_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = self.clean_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(self.clean_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.base_pixmap = QPixmap.fromImage(q_img)

        # 2. Window flags for borderless fullscreen stay-on-top
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(self.screen_rect)

        # Selection state
        self.start_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = None
        self.is_selecting = False

        self.setMouseTracking(True)
        self.showFullScreen()
        self.activateWindow()

    def _capture_desktop(self) -> Tuple[np.ndarray, QRect]:
        """Captures full screen with mss or falls back to desktop geometry."""
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                bgr = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
                rect = QRect(mon["left"], mon["top"], mon["width"], mon["height"])
                return bgr, rect
        except Exception:
            screen = QtWidgets.QApplication.primaryScreen()
            geo = screen.geometry()
            bgr = np.zeros((geo.height(), geo.width(), 3), dtype=np.uint8)
            bgr[:] = (20, 20, 30)
            return bgr, geo

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.RightButton:
            self.close()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        self.current_pos = event.pos()
        self.update()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            end_pos = event.pos()
            self._finish_selection(self.start_pos, end_pos)

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Draw pristine desktop background
        painter.drawPixmap(0, 0, self.base_pixmap)

        # Bright translucent mask color (light ~18% dimming for clear game visibility)
        dim_color = QColor(0, 0, 0, 45)

        sel_rect = self._get_current_rect()

        if sel_rect.isValid() and sel_rect.width() > 1 and sel_rect.height() > 1:
            # Clip un-dimmed hole for the selected area
            region = QtGui.QRegion(self.rect())
            region = region.subtracted(QtGui.QRegion(sel_rect))
            painter.setClipRegion(region)
            painter.fillRect(self.rect(), dim_color)

            # Reset clip to draw border & labels
            painter.setClipping(False)

            # Draw glowing selection border
            pen = QPen(QColor(0, 229, 255), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(sel_rect)

            # Live dimensions tooltip
            w_px = sel_rect.width()
            h_px = sel_rect.height()
            coord_text = f" {w_px} × {h_px} px  ({sel_rect.x()}, {sel_rect.y()}) "
            
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            text_rect = painter.fontMetrics().boundingRect(coord_text)
            text_x = sel_rect.x()
            text_y = sel_rect.y() - 26 if sel_rect.y() >= 30 else sel_rect.bottom() + 6
            bg_rect = QRect(text_x, text_y, text_rect.width() + 12, 22)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(16, 18, 28, 230))
            painter.drawRoundedRect(bg_rect, 4, 4)
            painter.setPen(QColor(0, 229, 255))
            painter.drawText(bg_rect, Qt.AlignCenter, coord_text)
        else:
            # Draw uniform dimming over entire screen
            painter.fillRect(self.rect(), dim_color)

        # Draw Title Banner at top
        banner_w = 420
        banner_h = 36
        banner_x = (self.width() - banner_w) // 2
        banner_rect = QRect(banner_x, 18, banner_w, banner_h)
        painter.setPen(QPen(QColor(0, 229, 255, 120), 1))
        painter.setBrush(QColor(24, 28, 46, 240))
        painter.drawRoundedRect(banner_rect, 6, 6)

        painter.setPen(QColor(0, 229, 255))
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.drawText(banner_rect, Qt.AlignCenter, f"🎯 {self.title_text}  (ESC to Cancel)")

        # Crosshairs following mouse
        if self.current_pos:
            cx = self.current_pos.x()
            cy = self.current_pos.y()
            pen_cross = QPen(QColor(0, 229, 255, 140), 1, Qt.DashLine)
            painter.setPen(pen_cross)
            painter.drawLine(0, cy, self.width(), cy)
            painter.drawLine(cx, 0, cx, self.height())

    def _get_current_rect(self) -> QRect:
        if not self.start_pos or not self.current_pos:
            return QRect()
        x1 = min(self.start_pos.x(), self.current_pos.x())
        y1 = min(self.start_pos.y(), self.current_pos.y())
        x2 = max(self.start_pos.x(), self.current_pos.x())
        y2 = max(self.start_pos.y(), self.current_pos.y())
        return QRect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))

    def _finish_selection(self, p1: QPoint, p2: QPoint):
        self.close()
        x1 = min(p1.x(), p2.x())
        y1 = min(p1.y(), p2.y())
        x2 = max(p1.x(), p2.x())
        y2 = max(p1.y(), p2.y())
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)

        # Single click check for point calibration
        if w <= 3 and h <= 3:
            res = {"x": p1.x(), "y": p1.y(), "width": 1, "height": 1, "is_point": True}
        else:
            res = {"x": x1, "y": y1, "width": w, "height": h, "is_point": False}

        # Crop image if template filename specified
        if self.template_filename and self.save_dir:
            os.makedirs(self.save_dir, exist_ok=True)
            crop_bgr = self.clean_bgr[y1:y1+h, x1:x1+w]
            save_path = os.path.join(self.save_dir, self.template_filename)
            cv2.imwrite(save_path, crop_bgr)
            res["saved_path"] = save_path

        if self.on_complete:
            self.on_complete(res)
