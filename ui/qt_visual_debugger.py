"""
qt_visual_debugger.py - Hardware-accelerated Visual Debugger for Task Bar Hero.
Renders real-time annotated screen captures with live bounding boxes, rarity colors,
item level badges, and chest statuses with zero DWM lag.
"""

import json
import time
from typing import Dict, Any, Optional, List, Tuple
import cv2
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QFont

from vision import VisionEngine
from .qt_theme import DARK_THEME_QSS


class QtVisualDebugger(QtWidgets.QMainWindow):
    """
    Hardware-accelerated Visual Debugger Window.
    Displays live screen captures with bounding boxes, rarity indicators, and chest status.
    Supports 3 inspection modes:
    - Full Desktop
    - Inventory Grid (zoomed crop)
    - Chest Region (zoomed crop)
    """
    def __init__(self, parent=None, vision_engine: Optional[VisionEngine] = None, config_data: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.setWindowTitle("🔍 Task Bar Hero — Visual Debugger & Live Inspection")
        self.resize(780, 560)
        self.setMinimumSize(440, 320)
        self.setStyleSheet(DARK_THEME_QSS)

        self.vision = vision_engine
        self.config_data = config_data or {}
        self.current_mode = "full"

        # Auto-refresh timer
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(1000)
        self.auto_timer.timeout.connect(self.refresh_view)

        self._build_ui()

        # Trigger initial capture after show
        QTimer.singleShot(150, self.refresh_view)

    def _build_ui(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. Top Toolbar Card
        top_card = QtWidgets.QFrame(central)
        top_card.setProperty("card", True)
        top_layout = QtWidgets.QHBoxLayout(top_card)
        top_layout.setContentsMargins(10, 6, 10, 6)
        top_layout.setSpacing(10)

        lbl_title = QtWidgets.QLabel("🔍 DEBUGGER", top_card)
        lbl_title.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 10pt;")
        top_layout.addWidget(lbl_title)

        # Mode Selector (Combo / Buttons)
        self.mode_combo = QtWidgets.QComboBox(top_card)
        self.mode_combo.addItems([
            "Full Desktop",
            "Inventory Grid",
            "Materials (SS_materials)",
            "Corrosion (SS_corrosion)",
            "Lv. 50 Gears (SS/)",
            "Chest Region"
        ])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        top_layout.addWidget(self.mode_combo)

        # Quick Layer Toggles
        self.cb_show_gears = QtWidgets.QCheckBox("Gears", top_card)
        self.cb_show_gears.setChecked(True)
        self.cb_show_gears.setStyleSheet("color: #38ef7d; font-size: 8.5pt; font-weight: bold;")
        self.cb_show_gears.toggled.connect(self.refresh_view)
        top_layout.addWidget(self.cb_show_gears)

        self.cb_show_mats = QtWidgets.QCheckBox("Materials", top_card)
        self.cb_show_mats.setChecked(True)
        self.cb_show_mats.setStyleSheet("color: #00e5ff; font-size: 8.5pt; font-weight: bold;")
        self.cb_show_mats.toggled.connect(self.refresh_view)
        top_layout.addWidget(self.cb_show_mats)

        self.cb_show_corr = QtWidgets.QCheckBox("Corrosion", top_card)
        self.cb_show_corr.setChecked(True)
        self.cb_show_corr.setStyleSheet("color: #ff79c6; font-size: 8.5pt; font-weight: bold;")
        self.cb_show_corr.toggled.connect(self.refresh_view)
        top_layout.addWidget(self.cb_show_corr)

        self.cb_show_lvl50 = QtWidgets.QCheckBox("Lv.50", top_card)
        self.cb_show_lvl50.setChecked(True)
        self.cb_show_lvl50.setStyleSheet("color: #ffd166; font-size: 8.5pt; font-weight: bold;")
        self.cb_show_lvl50.toggled.connect(self.refresh_view)
        top_layout.addWidget(self.cb_show_lvl50)

        top_layout.addStretch()

        self.cb_auto = QtWidgets.QCheckBox("Auto", top_card)
        self.cb_auto.setToolTip("Auto refresh every 1 second")
        self.cb_auto.toggled.connect(self.on_auto_toggled)
        top_layout.addWidget(self.cb_auto)

        self.btn_refresh = QtWidgets.QPushButton("📸 Capture", top_card)
        self.btn_refresh.setProperty("role", "primary")
        self.btn_refresh.setToolTip("Capture desktop and refresh overlay")
        self.btn_refresh.clicked.connect(self.refresh_view)
        top_layout.addWidget(self.btn_refresh)

        layout.addWidget(top_card)

        # 2. Threshold Adjustments Bar
        tune_card = QtWidgets.QFrame(central)
        tune_card.setProperty("inner_card", True)
        tune_layout = QtWidgets.QHBoxLayout(tune_card)
        tune_layout.setContentsMargins(6, 4, 6, 4)
        tune_layout.setSpacing(6)

        # Confidence
        tune_layout.addWidget(QtWidgets.QLabel("Conf:", tune_card))
        self.spin_conf = QtWidgets.QSpinBox(tune_card)
        self.spin_conf.setRange(40, 99)
        self.spin_conf.setFixedWidth(46)
        conf_pct = int(round(float(self.config_data.get("confidence_threshold", 0.75)) * 100))
        self.spin_conf.setValue(conf_pct)
        tune_layout.addWidget(self.spin_conf)

        # Badge match
        tune_layout.addWidget(QtWidgets.QLabel("Badge:", tune_card))
        self.spin_badge = QtWidgets.QSpinBox(tune_card)
        self.spin_badge.setRange(40, 99)
        self.spin_badge.setFixedWidth(46)
        badge_pct = int(round(float(self.config_data.get("badge_match_threshold", 0.75)) * 100))
        self.spin_badge.setValue(badge_pct)
        tune_layout.addWidget(self.spin_badge)

        # Box dimensions
        tune_layout.addWidget(QtWidgets.QLabel("Box:", tune_card))
        self.spin_bw = QtWidgets.QSpinBox(tune_card)
        self.spin_bw.setRange(10, 40)
        self.spin_bw.setFixedWidth(42)
        self.spin_bw.setValue(int(self.config_data.get("badge_detector_width", 19)))
        tune_layout.addWidget(self.spin_bw)

        self.spin_bh = QtWidgets.QSpinBox(tune_card)
        self.spin_bh.setRange(10, 40)
        self.spin_bh.setFixedWidth(42)
        self.spin_bh.setValue(int(self.config_data.get("badge_detector_height", 15)))
        tune_layout.addWidget(self.spin_bh)

        # 3-Corner Rarity Checkbox
        self.cb_3corner = QtWidgets.QCheckBox("3-Corner", tune_card)
        self.cb_3corner.setChecked(bool(self.config_data.get("multi_corner_rarity_enabled", False)))
        self.cb_3corner.setStyleSheet("color: #ff79c6; font-weight: bold;")
        tune_layout.addWidget(self.cb_3corner)

        # Apply button
        btn_apply = QtWidgets.QPushButton("✔ Apply", tune_card)
        btn_apply.setProperty("role", "success")
        btn_apply.clicked.connect(self.apply_tuning)
        tune_layout.addWidget(btn_apply)

        layout.addWidget(tune_card)

        # 3. Main Viewport (Aspect-Ratio Scaled Image Viewer)
        self.image_label = QtWidgets.QLabel(central)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #0c0d14; border: 1px solid #1e2438; border-radius: 4px;")
        self.image_label.setMinimumSize(240, 150)
        self.image_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout.addWidget(self.image_label, stretch=1)

        # 4. Bottom Info Bar
        self.status_bar_lbl = QtWidgets.QLabel("Ready - Click Capture to inspect screen.", central)
        self.status_bar_lbl.setWordWrap(True)
        self.status_bar_lbl.setStyleSheet("color: #38ef7d; font-weight: bold; font-size: 8.5pt;")
        self.status_bar_lbl.setStyleSheet("color: #38ef7d; font-weight: bold; font-size: 9.5pt;")
        layout.addWidget(self.status_bar_lbl)

        self.raw_bgr: Optional[np.ndarray] = None

    def on_mode_changed(self, text: str):
        mode_map = {
            "Full Desktop": "full",
            "Inventory Grid": "inventory",
            "Materials (SS_materials)": "materials",
            "Corrosion (SS_corrosion)": "corrosion",
            "Lv. 50 Gears (SS/)": "lvl50",
            "Chest Region": "chest"
        }
        self.current_mode = mode_map.get(text, "full")
        self.refresh_view()

    def on_auto_toggled(self, checked: bool):
        if checked:
            self.auto_timer.start()
        else:
            self.auto_timer.stop()

    def apply_tuning(self):
        conf = self.spin_conf.value() / 100.0
        badge = self.spin_badge.value() / 100.0
        bw = self.spin_bw.value()
        bh = self.spin_bh.value()
        c3 = self.cb_3corner.isChecked()

        self.config_data["confidence_threshold"] = conf
        self.config_data["badge_match_threshold"] = badge
        self.config_data["badge_detector_width"] = bw
        self.config_data["badge_detector_height"] = bh
        self.config_data["multi_corner_rarity_enabled"] = c3

        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)
            if self.vision:
                self.vision.update_config(self.config_data)
        except Exception:
            pass
        self.refresh_view()

    def refresh_view(self):
        if not self.vision:
            return

        inv_roi = self.vision.get_inventory_roi()
        chest_roi = self.config_data.get("rois", {}).get("chest_region")

        try:
            annotated_bgr, stats = self.vision.render_debug_overlay(
                inv_roi=inv_roi,
                chest_roi=chest_roi,
                mode=self.current_mode,
                show_gears=getattr(self, "cb_show_gears", None) is None or self.cb_show_gears.isChecked(),
                show_materials=getattr(self, "cb_show_mats", None) is None or self.cb_show_mats.isChecked(),
                show_corrosion=getattr(self, "cb_show_corr", None) is None or self.cb_show_corr.isChecked(),
                show_lvl50=getattr(self, "cb_show_lvl50", None) is None or self.cb_show_lvl50.isChecked()
            )
            self.raw_bgr = annotated_bgr

            # Compose informative status message
            total = stats.get("total_items", 0)
            t65 = stats.get("tier_65", 0)
            t80 = stats.get("tier_80_90", 0)
            rc = stats.get("rarity_counts", {})
            chest_st = stats.get("chest_status", "UNKNOWN")
            mats = stats.get("materials", [])
            corrs = stats.get("corrosion_items", [])

            if self.current_mode == "materials":
                mat_names = ", ".join(f"{m.get('name')}({int(m.get('score', 0)*100)}%)" for m in mats[:5])
                msg = f"Mode: MATERIALS | Found {len(mats)} material(s): {mat_names if mat_names else 'None'}"
            elif self.current_mode == "corrosion":
                corr_names = ", ".join(f"{c.get('name')}({int(c.get('score', 0)*100)}%)" for c in corrs[:5])
                msg = f"Mode: CORROSION | Found {len(corrs)} corrosion item(s): {corr_names if corr_names else 'None'}"
            elif self.current_mode == "lvl50":
                lvl50_list = stats.get("lvl50_items", [])
                lvl50_names = ", ".join(f"{it.get('name')}[{it.get('rarity')}](conf:{int(it.get('score', 0)*100)}%)" for it in lvl50_list[:5])
                msg = f"Mode: LV. 50 | Found {len(lvl50_list)} Lv. 50 item(s): {lvl50_names if lvl50_names else 'None'}"
            else:
                lvl50_cnt = len(stats.get("lvl50_items", []))
                msg = (
                    f"Mode: {self.current_mode.upper()} | Gears: {total} (Lv.65: {t65}, Lv.80~90: {t80}) | "
                    f"Mats: {len(mats)} | Corr: {len(corrs)} | Lv.50: {lvl50_cnt} | "
                    f"Rarity: [L:{rc.get('Legendary', 0)}, R:{rc.get('Rare', 0)}, U:{rc.get('Uncommon', 0)}, C:{rc.get('Common', 0)}] | "
                    f"Chest: {chest_st}"
                )
            self.status_bar_lbl.setText(msg)

            # Convert to QPixmap and display
            annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = annotated_rgb.shape
            q_img = QImage(annotated_rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            # Scale to fit image_label preserving aspect ratio
            lbl_size = self.image_label.size()
            if lbl_size.width() > 10 and lbl_size.height() > 10:
                scaled = pixmap.scaled(lbl_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled)
            else:
                self.image_label.setPixmap(pixmap)
        except Exception as e:
            self.status_bar_lbl.setText(f"Capture/Render Error: {e}")

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        # Smoothly re-scale the existing pixmap on resize without re-capturing desktop
        if self.raw_bgr is not None:
            try:
                rgb = cv2.cvtColor(self.raw_bgr, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                lbl_size = self.image_label.size()
                if lbl_size.width() > 10 and lbl_size.height() > 10:
                    scaled = QPixmap.fromImage(q_img).scaled(lbl_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.image_label.setPixmap(scaled)
            except Exception:
                pass

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.auto_timer.stop()
        super().closeEvent(event)
