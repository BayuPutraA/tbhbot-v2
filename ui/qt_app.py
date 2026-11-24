"""
qt_app.py - Ultra-High-Performance PySide6 GUI Dashboard & Calibrator for Task Bar Hero.
Renders with a single native Win32 HWND directly via DirectX/Direct3D hardware acceleration.
Eliminates 100% of window-dragging lag, DWM GPU spikes, and CustomTkinter canvas overhead,
while preserving all bot automation, computer vision, and calibrator capabilities.
"""

import os
import re
import json
import time
import subprocess
import threading
from typing import Dict, Any, Optional, List, Tuple
import cv2
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QColor, QFont, QIcon

from core import BotEngine
from vision import VisionEngine, TEMPLATE_MANIFEST
from .qt_theme import DARK_THEME_QSS
from .qt_snipper import QtScreenSnipper
from .qt_visual_debugger import QtVisualDebugger

# Reference gear matrix configuration (12 items x 4 rarities x 4 levels = 192 total combinations)
GEAR_NAMES = [
    "armor", "arrow", "boots", "bow", "gloves", "helmet",
    "orb", "scepter", "shield", "staff", "sword", "tome"
]

GEAR_ICONS = {
    "armor": "👕",
    "arrow": "🏹",
    "boots": "👢",
    "bow": "🏹",
    "gloves": "🧤",
    "helmet": "🪖",
    "orb": "🔮",
    "scepter": "🪄",
    "shield": "🛡️",
    "staff": "🦯",
    "sword": "🗡️",
    "tome": "📖"
}

RARITIES_ORDER = [
    ("c", "Common", "#AAAAAA"),
    ("u", "Uncommon", "#32CD32"),
    ("r", "Rare", "#1E90FF"),
    ("l", "Legendary", "#FFA500")
]

LEVELS_ORDER = ["50", "65", "80", "90"]


class BotBridge(QObject):
    """Thread-safe signal dispatcher from BotEngine daemon thread to Qt GUI."""
    sig_status = Signal(str, str)
    sig_log = Signal(str, str)
    sig_countdown = Signal(str, int)
    sig_buckets = Signal(dict)
    sig_progress = Signal(int)


class TaskBarHeroQtApp(QtWidgets.QMainWindow):
    """
    Main Qt 6 Application for Task Bar Hero.
    Delivers zero-lag 144Hz window movement, Direct3D composition, and full bot control.
    """
    def __init__(self):
        import sys
        if QtWidgets.QApplication.instance() is None:
            self._qt_app = QtWidgets.QApplication(sys.argv)
        else:
            self._qt_app = QtWidgets.QApplication.instance()

        super().__init__()
        self.setWindowTitle("Task Bar Hero — Auto Chest & Cube Synthesizer (Qt 6 Performance Edition)")
        self.resize(860, 650)
        self.setMinimumSize(560, 390)
        self.setStyleSheet(DARK_THEME_QSS)

        # File paths
        self.config_path = "config.json"
        self.assets_dir = "assets"
        self.ss_dir = "SS"
        self.materials_dir = "SS_materials"
        self.corrosion_dir = "SS_corrosion"
        self.confirmed_gears_path = "confirmed_gear.json"
        self.materials_manifest_path = "materials_manifest.json"
        self.corrosion_manifest_path = "corrosion_manifest.json"

        # Load configs and records
        self.config_data = self.load_config()
        self.confirmed_gears = self.load_confirmed_gears()
        self.materials_manifest = self.load_materials_manifest()
        self.corrosion_manifest = self.load_corrosion_manifest()
        self.ss_file_cache: Dict[str, Tuple[int, int]] = {}
        self.all_gear_items: List[Dict[str, Any]] = []
        self.log_history: List[Tuple[str, str, str]] = []
        self.log_filter_cbs: Dict[str, QtWidgets.QCheckBox] = {}
        self.current_log_verbosity: str = self.config_data.get("log_verbosity", "Clean")

        # Thread-safe signal bridge
        self.bridge = BotBridge()
        self.bridge.sig_status.connect(self._slot_status)
        self.bridge.sig_log.connect(self._slot_log)
        self.bridge.sig_countdown.connect(self._slot_countdown)
        self.bridge.sig_buckets.connect(self._slot_buckets)
        self.bridge.sig_progress.connect(self._slot_progress)

        # Initialize Bot Engine
        self.bot = BotEngine(
            config_path=self.config_path,
            assets_dir=self.assets_dir,
            on_status=lambda txt, col="#38ef7d": self.bridge.sig_status.emit(txt, col),
            on_log=lambda msg, lvl="info": self.bridge.sig_log.emit(msg, lvl),
            on_countdown=lambda t_str, sec: self.bridge.sig_countdown.emit(t_str, sec),
            on_buckets_update=lambda b: self.bridge.sig_buckets.emit(b),
            on_items_detected=self.record_detected_items
        )

        self.calibrator = self.bot.calibrator if hasattr(self.bot, "calibrator") else None
        self.debugger_window: Optional[QtVisualDebugger] = None

        self._build_ui()

        # Pre-build gear items metadata
        self._init_gear_metadata()

        # Start scheduler after GUI is ready
        QTimer.singleShot(250, self._on_gui_ready)

    def _on_gui_ready(self):
        self.bot.start_scheduler()
        # Initialize Dashboard buckets with engine's live counts
        if hasattr(self.bot, "live_buckets"):
            self._slot_buckets(self.bot.live_buckets)
        self.append_log("Application initialized successfully with Qt 6 High-Performance Direct3D engine.", "success")
        self.append_log(f"F8 Key Emergency Stop listener active.", "info")

    def _build_ui(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Tab Widget
        self.tabs = QtWidgets.QTabWidget(central)
        main_layout.addWidget(self.tabs)

        # Tab 1: Dashboard
        self.tab_dashboard = QtWidgets.QWidget()
        self._build_dashboard_tab()
        self.tabs.addTab(self.tab_dashboard, "Dashboard")

        # Tab 2: Calibrator & Assets
        self.tab_calibrator = QtWidgets.QWidget()
        self._build_calibrator_tab()
        self.tabs.addTab(self.tab_calibrator, "Calibrator & Assets")

        # Tab 3: Gears Checklist
        self.tab_gears = QtWidgets.QWidget()
        self._build_gear_checklist_tab()
        self.tabs.addTab(self.tab_gears, "🛡 Gears")

        # Tab 4: Materials Library
        self.tab_materials = QtWidgets.QWidget()
        self._build_materials_tab()
        self.tabs.addTab(self.tab_materials, "📦 Materials")

        # Tab 5: Corrosion Materials & Cube
        self.tab_corrosion = QtWidgets.QWidget()
        self._build_corrosion_tab()
        self.tabs.addTab(self.tab_corrosion, "⚗ Corrosion")

        # Tab 6: Telegram Watchdog & Remote Service
        self.tab_telegram = QtWidgets.QWidget()
        self._build_telegram_tab()
        self.tabs.addTab(self.tab_telegram, "📱 Telegram")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        tab_name = self.tabs.tabText(index)
        if "Gears" in tab_name:
            self.refresh_gear_checklist_data()
        elif "Materials" in tab_name:
            self.refresh_materials_checklist_data()
        elif "Corrosion" in tab_name:
            self.refresh_corrosion_table_data()
        elif "Telegram" in tab_name:
            self.refresh_telegram_tab_status()
        elif "Calibrator" in tab_name:
            self.refresh_all_asset_statuses()

    # ---------------------------------------------------------
    # TAB 1: AUTOMATION DASHBOARD
    # ---------------------------------------------------------
    def _build_dashboard_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_dashboard)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Status Banner Card
        status_card = QtWidgets.QFrame(self.tab_dashboard)
        status_card.setProperty("card", True)
        status_card.setFixedHeight(34)
        sc_layout = QtWidgets.QHBoxLayout(status_card)
        sc_layout.setContentsMargins(10, 0, 10, 0)

        self.lbl_status = QtWidgets.QLabel("STATUS: Idle - Waiting for Timer", status_card)
        self.lbl_status.setStyleSheet("color: #38ef7d; font-weight: bold; font-size: 11pt;")
        sc_layout.addWidget(self.lbl_status)
        sc_layout.addStretch()

        layout.addWidget(status_card)

        # 2. Timer & Action Controls Row
        timer_card = QtWidgets.QFrame(self.tab_dashboard)
        timer_card.setProperty("card", True)
        tc_layout = QtWidgets.QHBoxLayout(timer_card)
        tc_layout.setContentsMargins(10, 6, 10, 6)
        tc_layout.setSpacing(8)

        lbl_t_tag = QtWidgets.QLabel("⏱ COUNTDOWN:", timer_card)
        lbl_t_tag.setStyleSheet("color: #8892b0; font-weight: bold; font-size: 10pt;")
        tc_layout.addWidget(lbl_t_tag)

        self.lbl_timer = QtWidgets.QLabel("02:00:00", timer_card)
        self.lbl_timer.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 12pt; font-family: 'Consolas', monospace;")
        tc_layout.addWidget(self.lbl_timer)

        tc_layout.addWidget(QtWidgets.QLabel("Interval:", timer_card))
        self.combo_interval = QtWidgets.QComboBox(timer_card)
        self.combo_interval.addItems(["30m", "60m", "90m", "120m (Default)", "180m"])
        self.combo_interval.setCurrentText("120m (Default)")
        self.combo_interval.currentTextChanged.connect(self._on_interval_changed)
        tc_layout.addWidget(self.combo_interval)

        tc_layout.addStretch()

        # Start / Stop / Pause
        self.btn_start = QtWidgets.QPushButton("▶ START", timer_card)
        self.btn_start.setProperty("role", "success")
        self.btn_start.clicked.connect(self.start_cycle_action)
        tc_layout.addWidget(self.btn_start)

        self.btn_pause = QtWidgets.QPushButton("⏸ PAUSE", timer_card)
        self.btn_pause.setProperty("role", "warning")
        self.btn_pause.clicked.connect(self.pause_cycle_action)
        tc_layout.addWidget(self.btn_pause)

        self.btn_stop = QtWidgets.QPushButton("⏹ STOP", timer_card)
        self.btn_stop.setProperty("role", "danger")
        self.btn_stop.clicked.connect(self.stop_cycle_action)
        tc_layout.addWidget(self.btn_stop)

        layout.addWidget(timer_card)

        # 3. Progress Bar
        self.progress_bar = QtWidgets.QProgressBar(self.tab_dashboard)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        layout.addWidget(self.progress_bar)

        # 4. Live Item Buckets Card
        bucket_card = QtWidgets.QFrame(self.tab_dashboard)
        bucket_card.setProperty("card", True)
        bc_layout = QtWidgets.QVBoxLayout(bucket_card)
        bc_layout.setContentsMargins(10, 6, 10, 6)
        bc_layout.setSpacing(4)

        lbl_b_title = QtWidgets.QLabel("📦 LIVE INVENTORY GEAR COUNTERS (STASH BUCKETS)", bucket_card)
        lbl_b_title.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 9.5pt;")
        bc_layout.addWidget(lbl_b_title)

        grid_frame = QtWidgets.QFrame(bucket_card)
        b_grid = QtWidgets.QGridLayout(grid_frame)
        b_grid.setContentsMargins(0, 2, 0, 2)
        b_grid.setHorizontalSpacing(12)
        b_grid.setVerticalSpacing(4)

        rarities = [("Common", "#AAAAAA"), ("Uncommon", "#32CD32"), ("Rare", "#1E90FF"), ("Legendary", "#FFA500")]
        self.lbl_counts = {}

        # Lv.65 Row
        lbl_lv65 = QtWidgets.QLabel("Lv.65:", grid_frame)
        lbl_lv65.setStyleSheet("color: #d0d5e2; font-weight: bold;")
        b_grid.addWidget(lbl_lv65, 0, 0)
        for col_idx, (r_name, r_col) in enumerate(rarities):
            lbl = QtWidgets.QLabel(f"{r_name}: 0", grid_frame)
            lbl.setStyleSheet(f"color: {r_col}; font-weight: bold; font-size: 9.5pt;")
            b_grid.addWidget(lbl, 0, col_idx + 1)
            self.lbl_counts[("65", r_name)] = lbl

        # Lv.80~90 Row
        lbl_lv80_90 = QtWidgets.QLabel("Lv.80~90:", grid_frame)
        lbl_lv80_90.setStyleSheet("color: #d0d5e2; font-weight: bold;")
        b_grid.addWidget(lbl_lv80_90, 1, 0)
        for col_idx, (r_name, r_col) in enumerate(rarities):
            lbl = QtWidgets.QLabel(f"{r_name}: 0", grid_frame)
            lbl.setStyleSheet(f"color: {r_col}; font-weight: bold; font-size: 9.5pt;")
            b_grid.addWidget(lbl, 1, col_idx + 1)
            self.lbl_counts[("80_90", r_name)] = lbl

        bc_layout.addWidget(grid_frame)
        layout.addWidget(bucket_card)

        # 5. Quick Tools & Toggles Bar
        tools_card = QtWidgets.QFrame(self.tab_dashboard)
        tools_card.setProperty("inner_card", True)
        tools_layout = QtWidgets.QVBoxLayout(tools_card)
        tools_layout.setContentsMargins(8, 6, 8, 6)
        tools_layout.setSpacing(6)

        # Row 1: Feature Toggles
        toggles_row = QtWidgets.QHBoxLayout()
        toggles_row.setSpacing(12)

        self.cb_auto_loop = QtWidgets.QCheckBox("Auto Loop", tools_card)
        self.cb_auto_loop.setChecked(bool(self.bot.auto_loop_enabled))
        self.cb_auto_loop.toggled.connect(self.toggle_auto_loop_action)
        toggles_row.addWidget(self.cb_auto_loop)

        self.cb_3corner = QtWidgets.QCheckBox("3-Corner Rarity", tools_card)
        self.cb_3corner.setChecked(bool(self.config_data.get("multi_corner_rarity_enabled", False)))
        self.cb_3corner.setStyleSheet("color: #ff79c6; font-weight: bold;")
        self.cb_3corner.toggled.connect(self.toggle_3corner_rarity_action)
        toggles_row.addWidget(self.cb_3corner)

        self.cb_full_inv = QtWidgets.QCheckBox("Full Inv Anticipation", tools_card)
        init_full_inv = bool(self.config_data.get("full_inventory_anticipation", self.config_data.get("full_inventory_anticipation_enabled", False)))
        self.cb_full_inv.setChecked(init_full_inv)
        self.cb_full_inv.setStyleSheet("color: #00e5ff; font-weight: bold;")
        self.cb_full_inv.toggled.connect(self.toggle_full_inv_action)
        toggles_row.addWidget(self.cb_full_inv)

        self.cb_dash_low_level = QtWidgets.QCheckBox("Low Level Stash (Lv.50)", tools_card)
        self.cb_dash_low_level.setChecked(bool(self.config_data.get("low_level_stashing_enabled", False)))
        self.cb_dash_low_level.setStyleSheet("color: #ffd166; font-weight: bold;")
        self.cb_dash_low_level.toggled.connect(self.toggle_low_level_stashing_action)
        toggles_row.addWidget(self.cb_dash_low_level)

        self.cb_dash_telegram = QtWidgets.QCheckBox("📱 Telegram Watchdog", tools_card)
        self.cb_dash_telegram.setChecked(bool(self.config_data.get("telegram", {}).get("enabled", False)))
        self.cb_dash_telegram.setStyleSheet("color: #00e5ff; font-weight: bold;")
        self.cb_dash_telegram.toggled.connect(self.toggle_telegram_service_action)
        toggles_row.addWidget(self.cb_dash_telegram)

        toggles_row.addStretch()
        tools_layout.addLayout(toggles_row)

        # Row 2: Action Buttons (even distribution, highly legible on small resolutions)
        btns_row = QtWidgets.QHBoxLayout()
        btns_row.setSpacing(6)

        btn_dbg = QtWidgets.QPushButton("🔍 Debugger", tools_card)
        btn_dbg.setProperty("role", "indigo")
        btn_dbg.setToolTip("Open Hardware-Accelerated Visual Debugger Window")
        btn_dbg.clicked.connect(self.open_visual_debugger_action)
        btns_row.addWidget(btn_dbg, stretch=1)

        btn_assets = QtWidgets.QPushButton("📁 Assets", tools_card)
        btn_assets.setProperty("role", "primary")
        btn_assets.setToolTip("Open assets folder in Windows Explorer")
        btn_assets.clicked.connect(self.open_assets_folder_action)
        btns_row.addWidget(btn_assets, stretch=1)

        btn_test_syn = QtWidgets.QPushButton("🧪 Test Synth", tools_card)
        btn_test_syn.setProperty("role", "purple")
        btn_test_syn.setToolTip("Execute single-run test synthesis on current inventory")
        btn_test_syn.clicked.connect(self.run_test_synthesis_action)
        btns_row.addWidget(btn_test_syn, stretch=1)

        btn_test_chest = QtWidgets.QPushButton("📦 Test Chests", tools_card)
        btn_test_chest.setProperty("role", "success")
        btn_test_chest.setToolTip("Execute single-run test chest detection and open cycle")
        btn_test_chest.clicked.connect(self.run_test_chest_action)
        btns_row.addWidget(btn_test_chest, stretch=1)

        tools_layout.addLayout(btns_row)
        layout.addWidget(tools_card)

        # 6. Live Activity Log View with Category Filters
        log_header = QtWidgets.QHBoxLayout()
        log_header.setSpacing(8)

        lbl_log_title = QtWidgets.QLabel("📜 ACTIVITY LOG", self.tab_dashboard)
        lbl_log_title.setStyleSheet("color: #8892b0; font-weight: bold; font-size: 9.5pt;")
        log_header.addWidget(lbl_log_title)
        log_header.addStretch()

        # Log verbosity & filter controls group
        lbl_verbosity = QtWidgets.QLabel("Verbosity:", self.tab_dashboard)
        lbl_verbosity.setStyleSheet("color: #6272a4; font-size: 8.5pt;")
        log_header.addWidget(lbl_verbosity)

        self.combo_log_verbosity = QtWidgets.QComboBox(self.tab_dashboard)
        self.combo_log_verbosity.setFixedSize(115, 24)
        self.combo_log_verbosity.setStyleSheet("font-size: 8.5pt; font-weight: bold; padding: 1px 6px;")
        self.combo_log_verbosity.addItem("✨ Clean", "Clean")
        self.combo_log_verbosity.addItem("📋 Normal", "Normal")
        self.combo_log_verbosity.addItem("🔍 Verbose", "Verbose")

        saved_verb = self.config_data.get("log_verbosity", "Clean")
        v_idx = 0 if saved_verb == "Clean" else (2 if saved_verb == "Verbose" else 1)
        self.combo_log_verbosity.setCurrentIndex(v_idx)
        self.combo_log_verbosity.currentIndexChanged.connect(self.on_log_verbosity_changed)
        log_header.addWidget(self.combo_log_verbosity)

        log_header.addSpacing(12)

        lbl_filter = QtWidgets.QLabel("Filter:", self.tab_dashboard)
        lbl_filter.setStyleSheet("color: #6272a4; font-size: 8.5pt;")
        log_header.addWidget(lbl_filter)

        saved_filters = self.config_data.get("log_filters", {})
        filter_defs = [
            ("info", "Info", "#d0d5e2", saved_filters.get("info", True)),
            ("success", "Success", "#38ef7d", saved_filters.get("success", True)),
            ("warning", "Warning", "#ffd166", saved_filters.get("warning", True)),
            ("error", "Error", "#ff5555", saved_filters.get("error", True)),
        ]

        for lvl_key, label_txt, col_hex, is_checked in filter_defs:
            cb = QtWidgets.QCheckBox(label_txt, self.tab_dashboard)
            cb.setChecked(bool(is_checked))
            cb.setStyleSheet(f"color: {col_hex}; font-size: 8.5pt; font-weight: bold;")
            cb.toggled.connect(self.on_log_filter_changed)
            log_header.addWidget(cb)
            self.log_filter_cbs[lvl_key] = cb

        btn_clear_log = QtWidgets.QPushButton("🧹 Clear", self.tab_dashboard)
        btn_clear_log.setFixedSize(55, 22)
        btn_clear_log.clicked.connect(self.clear_logs_action)
        log_header.addWidget(btn_clear_log)
        layout.addLayout(log_header)

        self.log_text = QtWidgets.QTextEdit(self.tab_dashboard)
        self.log_text.setReadOnly(True)
        self.log_text.document().setMaximumBlockCount(400)
        layout.addWidget(self.log_text, stretch=1)

    # ---------------------------------------------------------
    # TAB 2: CALIBRATOR & ASSETS
    # ---------------------------------------------------------
    def _build_calibrator_tab(self):
        scroll = QtWidgets.QScrollArea(self.tab_calibrator)
        scroll.setWidgetResizable(True)

        container = QtWidgets.QWidget()
        container.setObjectName("calibrator_container")
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Header Info Card
        info_card = QtWidgets.QFrame(container)
        info_card.setProperty("card", True)
        ic_layout = QtWidgets.QVBoxLayout(info_card)
        ic_layout.setContentsMargins(10, 8, 10, 8)

        lbl_a_title = QtWidgets.QLabel("📁 ASSET CHECKLIST (15 USER-CAPTURED TEMPLATES IN assets/)", info_card)
        lbl_a_title.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11pt;")
        ic_layout.addWidget(lbl_a_title)

        lbl_desc = QtWidgets.QLabel(
            "Every template can be snipped directly from screen and auto-saves to assets/ with the exact required name.\n"
            "Green ✅ Loaded indicates ready. Click 'Snip Selected' on any template to capture or replace it instantly.",
            info_card
        )
        lbl_desc.setStyleSheet("color: #8892b0; font-size: 9.5pt;")
        ic_layout.addWidget(lbl_desc)

        btn_ref_all = QtWidgets.QPushButton("🔄 Refresh All Asset Statuses", info_card)
        btn_ref_all.setProperty("role", "primary")
        btn_ref_all.clicked.connect(self.refresh_all_asset_statuses)
        ic_layout.addWidget(btn_ref_all, alignment=Qt.AlignRight)
        layout.addWidget(info_card)

        # 2. SS Reference Gear Library Card
        ss_card = QtWidgets.QFrame(container)
        ss_card.setProperty("card", True)
        ss_layout = QtWidgets.QVBoxLayout(ss_card)
        ss_layout.setContentsMargins(10, 8, 10, 8)

        ss_h = QtWidgets.QHBoxLayout()
        lbl_ss = QtWidgets.QLabel("🛡 SS REFERENCE GEAR LIBRARY (SS/ FOLDER)", ss_card)
        lbl_ss.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11pt;")
        ss_h.addWidget(lbl_ss)
        ss_h.addStretch()

        btn_ss_reload = QtWidgets.QPushButton("🔄 Reload SS Library", ss_card)
        btn_ss_reload.setProperty("role", "primary")
        btn_ss_reload.clicked.connect(self.reload_ss_library_action)
        ss_h.addWidget(btn_ss_reload)
        ss_layout.addLayout(ss_h)

        ss_stats = self.bot.vision.get_reference_library_stats()
        self.lbl_ss_status = QtWidgets.QLabel(ss_stats["status_text"], ss_card)
        self.lbl_ss_status.setStyleSheet("color: #38ef7d; font-weight: bold; font-size: 9.5pt;")
        ss_layout.addWidget(self.lbl_ss_status)

        rc = ss_stats["rarity_counts"]
        lc = ss_stats["level_counts"]
        self.lbl_ss_breakdown = QtWidgets.QLabel(
            f"Rarities: Common: {rc['Common']} | Uncommon: {rc['Uncommon']} | Rare: {rc['Rare']} | Legendary: {rc['Legendary']}\n"
            f"Levels: Lv.65: {lc['65']} | Lv.80: {lc['80']} | Lv.90: {lc['90']}\n"
            "Strict Filter: Only gear matching images in SS/ is counted or synthesized. Unmatched items are skipped.",
            ss_card
        )
        self.lbl_ss_breakdown.setStyleSheet("color: #d0d5e2; font-size: 9pt;")
        ss_layout.addWidget(self.lbl_ss_breakdown)
        layout.addWidget(ss_card)

        # 3. System Templates Checklist Card
        tmpl_card = QtWidgets.QFrame(container)
        tmpl_card.setProperty("card", True)
        tc_layout = QtWidgets.QVBoxLayout(tmpl_card)
        tc_layout.setContentsMargins(10, 8, 10, 8)

        th_layout = QtWidgets.QHBoxLayout()
        lbl_tc = QtWidgets.QLabel("📁 SYSTEM TEMPLATES CHECKLIST (assets/)", tmpl_card)
        lbl_tc.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 10.5pt;")
        th_layout.addWidget(lbl_tc)
        th_layout.addStretch()

        btn_snip_tmpl = QtWidgets.QPushButton("✂ Snip Selected", tmpl_card)
        btn_snip_tmpl.setProperty("role", "teal")
        btn_snip_tmpl.clicked.connect(self.snip_selected_template_action)
        th_layout.addWidget(btn_snip_tmpl)
        tc_layout.addLayout(th_layout)

        self.table_templates = QtWidgets.QTableWidget(tmpl_card)
        self.table_templates.setColumnCount(4)
        self.table_templates.setHorizontalHeaderLabels(["FILENAME", "CATEGORY", "STATUS", "DESCRIPTION"])
        self.table_templates.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.table_templates.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table_templates.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.table_templates.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.table_templates.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_templates.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table_templates.setFixedHeight(180)
        self.table_templates.doubleClicked.connect(lambda: self.snip_selected_template_action())
        tc_layout.addWidget(self.table_templates)
        layout.addWidget(tmpl_card)

        # 4. Region of Interest (ROI) Calibration Card
        roi_card = QtWidgets.QFrame(container)
        roi_card.setProperty("card", True)
        rc_layout = QtWidgets.QVBoxLayout(roi_card)
        rc_layout.setContentsMargins(10, 8, 10, 8)

        lbl_roi_head = QtWidgets.QLabel("🎯 REGION OF INTEREST (ROI) CALIBRATION", roi_card)
        lbl_roi_head.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11pt;")
        rc_layout.addWidget(lbl_roi_head)

        lbl_roi_tip = QtWidgets.QLabel("Tip: If Inventory Grid ROI is not manually set, the bot automatically anchors it directly above inv_tab_btn.png.", roi_card)
        lbl_roi_tip.setStyleSheet("color: #8892b0; font-size: 9pt;")
        rc_layout.addWidget(lbl_roi_tip)

        grid_roi = QtWidgets.QGridLayout()
        grid_roi.setHorizontalSpacing(10)
        grid_roi.setVerticalSpacing(6)

        # Chest ROI
        self.lbl_chest_roi = QtWidgets.QLabel(self._format_roi_text("chest_region"), roi_card)
        btn_snip_chest = QtWidgets.QPushButton("✂ Snip Chest ROI", roi_card)
        btn_snip_chest.setProperty("role", "teal")
        btn_snip_chest.clicked.connect(lambda: self.snip_roi_action("chest_region", "Chest Pile Area", self.lbl_chest_roi))
        grid_roi.addWidget(self.lbl_chest_roi, 0, 0)
        grid_roi.addWidget(btn_snip_chest, 0, 1)

        # Inv ROI
        self.lbl_inv_roi = QtWidgets.QLabel(self._format_roi_text("inventory_grid"), roi_card)
        btn_snip_inv = QtWidgets.QPushButton("✂ Snip Inv Grid ROI", roi_card)
        btn_snip_inv.setProperty("role", "teal")
        btn_snip_inv.clicked.connect(lambda: self.snip_roi_action("inventory_grid", "7-Column Inventory Grid", self.lbl_inv_roi))
        grid_roi.addWidget(self.lbl_inv_roi, 1, 0)
        grid_roi.addWidget(btn_snip_inv, 1, 1)

        # Synth Button
        self.lbl_synth_btn = QtWidgets.QLabel(self._format_synth_btn_text(), roi_card)
        btn_sel_synth = QtWidgets.QPushButton("🎯 Select Target", roi_card)
        btn_sel_synth.setProperty("role", "primary")
        btn_sel_synth.clicked.connect(self.calibrate_synth_btn_action)
        btn_test_synth_clk = QtWidgets.QPushButton("▶ Test Click", roi_card)
        btn_test_synth_clk.setProperty("role", "indigo")
        btn_test_synth_clk.clicked.connect(self.test_click_synth_btn_action)
        grid_roi.addWidget(self.lbl_synth_btn, 2, 0)
        grid_roi.addWidget(btn_sel_synth, 2, 1)
        grid_roi.addWidget(btn_test_synth_clk, 2, 2)

        # Stash Slot
        self.lbl_stash_slot = QtWidgets.QLabel(self._format_stash_slot_text(), roi_card)
        btn_sel_stash = QtWidgets.QPushButton("🎯 Select Target", roi_card)
        btn_sel_stash.setProperty("role", "primary")
        btn_sel_stash.clicked.connect(self.calibrate_stash_slot_action)
        btn_test_stash_drag = QtWidgets.QPushButton("🔄 Test Drag", roi_card)
        btn_test_stash_drag.setProperty("role", "success")
        btn_test_stash_drag.clicked.connect(self.test_stash_drag_action)
        grid_roi.addWidget(self.lbl_stash_slot, 3, 0)
        grid_roi.addWidget(btn_sel_stash, 3, 1)
        grid_roi.addWidget(btn_test_stash_drag, 3, 2)

        # Cube Dropdown
        self.lbl_cube_dropdown = QtWidgets.QLabel(self._format_cube_dropdown_text(), roi_card)
        btn_sel_cube = QtWidgets.QPushButton("🎯 Select Dropdown", roi_card)
        btn_sel_cube.setProperty("role", "primary")
        btn_sel_cube.clicked.connect(self.calibrate_cube_dropdown_action)
        btn_test_cube = QtWidgets.QPushButton("▶ Test Dropdown", roi_card)
        btn_test_cube.setProperty("role", "warning")
        btn_test_cube.clicked.connect(self.test_cube_dropdown_action)
        grid_roi.addWidget(self.lbl_cube_dropdown, 4, 0)
        grid_roi.addWidget(btn_sel_cube, 4, 1)
        grid_roi.addWidget(btn_test_cube, 4, 2)

        # Tier 80~90
        self.lbl_tier_80_90 = QtWidgets.QLabel(self._format_tier_80_90_text(), roi_card)
        btn_sel_t80 = QtWidgets.QPushButton("🎯 Select Lv.80~90", roi_card)
        btn_sel_t80.setProperty("role", "primary")
        btn_sel_t80.clicked.connect(self.calibrate_tier_80_90_action)
        grid_roi.addWidget(self.lbl_tier_80_90, 5, 0)
        grid_roi.addWidget(btn_sel_t80, 5, 1)

        # Tier 65~80
        self.lbl_tier_65_80 = QtWidgets.QLabel(self._format_tier_65_80_text(), roi_card)
        btn_sel_t65 = QtWidgets.QPushButton("🎯 Select Lv.65~80", roi_card)
        btn_sel_t65.setProperty("role", "primary")
        btn_sel_t65.clicked.connect(self.calibrate_tier_65_80_action)
        grid_roi.addWidget(self.lbl_tier_65_80, 6, 0)
        grid_roi.addWidget(btn_sel_t65, 6, 1)

        # Mode Dropdown (Synthesis / Corrosion)
        self.lbl_calib_cube_mode = QtWidgets.QLabel(self._format_cube_mode_dropdown_text(), roi_card)
        btn_sel_mode_calib = QtWidgets.QPushButton("🎯 Select Mode Dropdown", roi_card)
        btn_sel_mode_calib.setProperty("role", "primary")
        btn_sel_mode_calib.clicked.connect(self.calibrate_cube_mode_dropdown_action)
        grid_roi.addWidget(self.lbl_calib_cube_mode, 7, 0)
        grid_roi.addWidget(btn_sel_mode_calib, 7, 1)

        # Option Corrosion
        self.lbl_calib_cube_corr = QtWidgets.QLabel(self._format_cube_option_corrosion_text(), roi_card)
        btn_sel_corr_calib = QtWidgets.QPushButton("🎯 Select Option Corrosion", roi_card)
        btn_sel_corr_calib.setProperty("role", "primary")
        btn_sel_corr_calib.clicked.connect(self.calibrate_cube_option_corrosion_action)
        btn_test_corr_calib = QtWidgets.QPushButton("▶ Test Corrosion Mode", roi_card)
        btn_test_corr_calib.setProperty("role", "purple")
        btn_test_corr_calib.clicked.connect(self.test_switch_corrosion_mode_action)
        grid_roi.addWidget(self.lbl_calib_cube_corr, 8, 0)
        grid_roi.addWidget(btn_sel_corr_calib, 8, 1)
        grid_roi.addWidget(btn_test_corr_calib, 8, 2)

        # Option Synthesis
        self.lbl_calib_cube_synth = QtWidgets.QLabel(self._format_cube_option_synthesis_text(), roi_card)
        btn_sel_synth_calib = QtWidgets.QPushButton("🎯 Select Option Synthesis", roi_card)
        btn_sel_synth_calib.setProperty("role", "primary")
        btn_sel_synth_calib.clicked.connect(self.calibrate_cube_option_synthesis_action)
        btn_test_synth_calib = QtWidgets.QPushButton("▶ Test Synthesis Mode", roi_card)
        btn_test_synth_calib.setProperty("role", "success")
        btn_test_synth_calib.clicked.connect(self.test_switch_synthesis_mode_action)
        grid_roi.addWidget(self.lbl_calib_cube_synth, 9, 0)
        grid_roi.addWidget(btn_sel_synth_calib, 9, 1)
        grid_roi.addWidget(btn_test_synth_calib, 9, 2)

        # Tier Lv. 50
        self.lbl_tier_50 = QtWidgets.QLabel(self._format_tier_50_text(), roi_card)
        btn_sel_t50 = QtWidgets.QPushButton("🎯 Select Lv.50 Option", roi_card)
        btn_sel_t50.setProperty("role", "primary")
        btn_sel_t50.clicked.connect(self.calibrate_tier_50_action)
        btn_test_t50 = QtWidgets.QPushButton("▶ Test Select Lv.50", roi_card)
        btn_test_t50.setProperty("role", "purple")
        btn_test_t50.clicked.connect(self.test_click_tier_50_action)
        grid_roi.addWidget(self.lbl_tier_50, 10, 0)
        grid_roi.addWidget(btn_sel_t50, 10, 1)
        grid_roi.addWidget(btn_test_t50, 10, 2)

        # Stash 1 (Common, Uncommon, Rare)
        self.lbl_stash_tab_1 = QtWidgets.QLabel(self._format_stash_tab_1_text(), roi_card)
        btn_sel_s1 = QtWidgets.QPushButton("🎯 Select Stash 1", roi_card)
        btn_sel_s1.setProperty("role", "primary")
        btn_sel_s1.clicked.connect(self.calibrate_stash_tab_1_action)
        btn_test_s1 = QtWidgets.QPushButton("▶ Test Click", roi_card)
        btn_test_s1.setProperty("role", "warning")
        btn_test_s1.clicked.connect(self.test_click_stash_tab_1_action)
        grid_roi.addWidget(self.lbl_stash_tab_1, 11, 0)
        grid_roi.addWidget(btn_sel_s1, 11, 1)
        grid_roi.addWidget(btn_test_s1, 11, 2)

        # Stash 2 (Legendary, Immortal)
        self.lbl_stash_tab_2 = QtWidgets.QLabel(self._format_stash_tab_2_text(), roi_card)
        btn_sel_s2 = QtWidgets.QPushButton("🎯 Select Stash 2", roi_card)
        btn_sel_s2.setProperty("role", "primary")
        btn_sel_s2.clicked.connect(self.calibrate_stash_tab_2_action)
        btn_test_s2 = QtWidgets.QPushButton("▶ Test Click", roi_card)
        btn_test_s2.setProperty("role", "warning")
        btn_test_s2.clicked.connect(self.test_click_stash_tab_2_action)
        grid_roi.addWidget(self.lbl_stash_tab_2, 12, 0)
        grid_roi.addWidget(btn_sel_s2, 12, 1)
        grid_roi.addWidget(btn_test_s2, 12, 2)

        # Stash Material (Return Tab)
        self.lbl_stash_tab_material = QtWidgets.QLabel(self._format_stash_tab_material_text(), roi_card)
        btn_sel_sm = QtWidgets.QPushButton("🎯 Select Material Tab", roi_card)
        btn_sel_sm.setProperty("role", "primary")
        btn_sel_sm.clicked.connect(self.calibrate_stash_tab_material_action)
        btn_test_sm = QtWidgets.QPushButton("▶ Test Click", roi_card)
        btn_test_sm.setProperty("role", "warning")
        btn_test_sm.clicked.connect(self.test_click_stash_tab_material_action)
        grid_roi.addWidget(self.lbl_stash_tab_material, 13, 0)
        grid_roi.addWidget(btn_sel_sm, 13, 1)
        grid_roi.addWidget(btn_test_sm, 13, 2)

        # Stash Grid ROI
        self.lbl_stash_grid_roi = QtWidgets.QLabel(self._format_stash_grid_roi_text(), roi_card)
        btn_snip_sgrid = QtWidgets.QPushButton("✂ Snip Stash Grid", roi_card)
        btn_snip_sgrid.setProperty("role", "teal")
        btn_snip_sgrid.clicked.connect(self.calibrate_stash_grid_roi_action)
        btn_test_sgrid = QtWidgets.QPushButton("🔍 Test Stash Scan", roi_card)
        btn_test_sgrid.setProperty("role", "success")
        btn_test_sgrid.clicked.connect(self.test_scan_stash_grid_action)
        grid_roi.addWidget(self.lbl_stash_grid_roi, 14, 0)
        grid_roi.addWidget(btn_snip_sgrid, 14, 1)
        grid_roi.addWidget(btn_test_sgrid, 14, 2)

        # Auto Fill Button
        self.lbl_auto_fill_btn = QtWidgets.QLabel(self._format_auto_fill_btn_text(), roi_card)
        btn_sel_af = QtWidgets.QPushButton("🎯 Select Auto Fill", roi_card)
        btn_sel_af.setProperty("role", "primary")
        btn_sel_af.clicked.connect(self.calibrate_auto_fill_btn_action)
        btn_test_af = QtWidgets.QPushButton("⚗ Test Auto-Fill", roi_card)
        btn_test_af.setProperty("role", "indigo")
        btn_test_af.clicked.connect(self.test_autofill_synth_action)
        grid_roi.addWidget(self.lbl_auto_fill_btn, 15, 0)
        grid_roi.addWidget(btn_sel_af, 15, 1)
        grid_roi.addWidget(btn_test_af, 15, 2)

        rc_layout.addLayout(grid_roi)

        # Toggles row inside Calibrator
        t_row = QtWidgets.QHBoxLayout()
        self.chk_auto_tier = QtWidgets.QCheckBox("Auto-Select Cube Tier (uncheck to bypass dropdown)", roi_card)
        self.chk_auto_tier.setChecked(bool(self.config_data.get("auto_select_cube_tier", False)))
        self.chk_auto_tier.toggled.connect(self.toggle_auto_tier_action)
        t_row.addWidget(self.chk_auto_tier)

        self.chk_autofill_synth = QtWidgets.QCheckBox("Auto-Fill Synth (After 5 Unstopped Loops)", roi_card)
        self.chk_autofill_synth.setChecked(bool(self.config_data.get("autofill_synth_enabled", True)))
        self.chk_autofill_synth.toggled.connect(self.toggle_autofill_synth_action)
        t_row.addWidget(self.chk_autofill_synth)

        self.chk_calib_full_inv = QtWidgets.QCheckBox("Full Inventory Anticipation (stash 1 slot if full)", roi_card)
        calib_full_inv = bool(self.config_data.get("full_inventory_anticipation", self.config_data.get("full_inventory_anticipation_enabled", False)))
        self.chk_calib_full_inv.setChecked(calib_full_inv)
        self.chk_calib_full_inv.toggled.connect(self.toggle_full_inv_action)
        t_row.addWidget(self.chk_calib_full_inv)
        t_row.addStretch()
        rc_layout.addLayout(t_row)

        layout.addWidget(roi_card)

        # 5. Manual Adjustment Controls Card
        dim_card = QtWidgets.QFrame(container)
        dim_card.setProperty("inner_card", True)
        dc_layout = QtWidgets.QVBoxLayout(dim_card)
        dc_layout.setContentsMargins(10, 8, 10, 8)

        lbl_dim_title = QtWidgets.QLabel("📏 MANUAL DETECTOR & DIMENSION SETTINGS", dim_card)
        lbl_dim_title.setStyleSheet("color: #ffd166; font-weight: bold; font-size: 10pt;")
        dc_layout.addWidget(lbl_dim_title)

        curr_inv = self.config_data.get("rois", {}).get("inventory_grid", {})
        curr_strip_w = self.config_data.get("grid_settings", {}).get("scroll_strip_width", 270)
        curr_conf_pct = int(round(float(self.config_data.get("confidence_threshold", 0.75)) * 100))
        curr_badge_pct = int(round(float(self.config_data.get("badge_match_threshold", 0.75)) * 100))
        curr_bw = int(self.config_data.get("badge_detector_width", 19))
        curr_bh = int(self.config_data.get("badge_detector_height", 15))
        curr_sdepth = self.config_data.get("grid_settings", {}).get("scroll_depth_px", 40)
        curr_synth = self.config_data.get("button_coords", {}).get("cube_synth_btn") or self.config_data.get("button_coords", {}).get("synth_btn", {})
        curr_stash = self.config_data.get("button_coords", {}).get("stash_slot", {})

        dg = QtWidgets.QGridLayout()
        dg.setHorizontalSpacing(8)
        dg.setVerticalSpacing(4)

        dg.addWidget(QtWidgets.QLabel("Inv Width:"), 0, 0)
        self.entry_inv_w = QtWidgets.QLineEdit(str(curr_inv.get("width", 289)))
        self.entry_inv_w.setFixedWidth(65)
        dg.addWidget(self.entry_inv_w, 0, 1)

        dg.addWidget(QtWidgets.QLabel("Inv Height:"), 0, 2)
        self.entry_inv_h = QtWidgets.QLineEdit(str(curr_inv.get("height", 122)))
        self.entry_inv_h.setFixedWidth(65)
        dg.addWidget(self.entry_inv_h, 0, 3)

        dg.addWidget(QtWidgets.QLabel("Scroll Width:"), 1, 0)
        self.entry_scroll_w = QtWidgets.QLineEdit(str(curr_strip_w))
        self.entry_scroll_w.setFixedWidth(65)
        dg.addWidget(self.entry_scroll_w, 1, 1)

        dg.addWidget(QtWidgets.QLabel("Scroll Depth:"), 1, 2)
        self.entry_scroll_depth = QtWidgets.QLineEdit(str(curr_sdepth))
        self.entry_scroll_depth.setFixedWidth(65)
        dg.addWidget(self.entry_scroll_depth, 1, 3)

        dg.addWidget(QtWidgets.QLabel("Detect Conf (%):"), 2, 0)
        self.entry_conf_thresh = QtWidgets.QLineEdit(str(curr_conf_pct))
        self.entry_conf_thresh.setFixedWidth(65)
        dg.addWidget(self.entry_conf_thresh, 2, 1)

        dg.addWidget(QtWidgets.QLabel("Badge Match (%):"), 2, 2)
        self.entry_badge_thresh = QtWidgets.QLineEdit(str(curr_badge_pct))
        self.entry_badge_thresh.setFixedWidth(65)
        dg.addWidget(self.entry_badge_thresh, 2, 3)

        dg.addWidget(QtWidgets.QLabel("Box Width:"), 3, 0)
        self.entry_badge_w = QtWidgets.QLineEdit(str(curr_bw))
        self.entry_badge_w.setFixedWidth(65)
        dg.addWidget(self.entry_badge_w, 3, 1)

        dg.addWidget(QtWidgets.QLabel("Box Height:"), 3, 2)
        self.entry_badge_h = QtWidgets.QLineEdit(str(curr_bh))
        self.entry_badge_h.setFixedWidth(65)
        dg.addWidget(self.entry_badge_h, 3, 3)

        dg.addWidget(QtWidgets.QLabel("Synth X:"), 4, 0)
        self.entry_synth_x = QtWidgets.QLineEdit(str(curr_synth.get("x", 520)))
        self.entry_synth_x.setFixedWidth(65)
        dg.addWidget(self.entry_synth_x, 4, 1)

        dg.addWidget(QtWidgets.QLabel("Synth Y:"), 4, 2)
        self.entry_synth_y = QtWidgets.QLineEdit(str(curr_synth.get("y", 510)))
        self.entry_synth_y.setFixedWidth(65)
        dg.addWidget(self.entry_synth_y, 4, 3)

        dg.addWidget(QtWidgets.QLabel("Stash X:"), 5, 0)
        self.entry_stash_x = QtWidgets.QLineEdit(str(curr_stash.get("x", "")))
        self.entry_stash_x.setFixedWidth(65)
        dg.addWidget(self.entry_stash_x, 5, 1)

        dg.addWidget(QtWidgets.QLabel("Stash Y:"), 5, 2)
        self.entry_stash_y = QtWidgets.QLineEdit(str(curr_stash.get("y", "")))
        self.entry_stash_y.setFixedWidth(65)
        dg.addWidget(self.entry_stash_y, 5, 3)

        dc_layout.addLayout(dg)

        btn_box = QtWidgets.QHBoxLayout()
        btn_apply_dim = QtWidgets.QPushButton("✔ Apply Settings", dim_card)
        btn_apply_dim.setProperty("role", "success")
        btn_apply_dim.clicked.connect(self.apply_manual_dimensions_action)
        btn_box.addWidget(btn_apply_dim)

        btn_step_scroll = QtWidgets.QPushButton("📜 Step Scroll", dim_card)
        btn_step_scroll.setProperty("role", "indigo")
        btn_step_scroll.clicked.connect(self.run_test_single_step_scroll_action)
        btn_box.addWidget(btn_step_scroll)
        btn_box.addStretch()
        dc_layout.addLayout(btn_box)

        layout.addWidget(dim_card)

        # 6. Bottom Diagnostics & Save
        diag_box = QtWidgets.QHBoxLayout()
        btn_diag_scan = QtWidgets.QPushButton("🖼 Visual Scan")
        btn_diag_scan.setProperty("role", "indigo")
        btn_diag_scan.clicked.connect(self.run_test_visual_scan_action)
        diag_box.addWidget(btn_diag_scan)

        btn_diag_scroll = QtWidgets.QPushButton("📜 Test Scroll")
        btn_diag_scroll.setProperty("role", "indigo")
        btn_diag_scroll.clicked.connect(self.run_test_scroll_action)
        diag_box.addWidget(btn_diag_scroll)

        btn_diag_chest = QtWidgets.QPushButton("📦 Test Chests")
        btn_diag_chest.setProperty("role", "success")
        btn_diag_chest.clicked.connect(self.run_test_chest_action)
        diag_box.addWidget(btn_diag_chest)

        btn_diag_synth = QtWidgets.QPushButton("🧪 Test Synthesis")
        btn_diag_synth.setProperty("role", "purple")
        btn_diag_synth.clicked.connect(self.run_test_synthesis_action)
        diag_box.addWidget(btn_diag_synth)
        layout.addLayout(diag_box)

        btn_save_cfg = QtWidgets.QPushButton("💾 Save Configuration")
        btn_save_cfg.setProperty("role", "success")
        btn_save_cfg.setFixedHeight(34)
        btn_save_cfg.clicked.connect(self.save_config)
        layout.addWidget(btn_save_cfg)

        scroll.setWidget(container)
        c_layout = QtWidgets.QVBoxLayout(self.tab_calibrator)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.addWidget(scroll)

    # ---------------------------------------------------------
    # TAB 3: GEAR CHECKLIST
    # ---------------------------------------------------------
    def _build_gear_checklist_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_gears)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Top Stats Card
        top_card = QtWidgets.QFrame(self.tab_gears)
        top_card.setProperty("card", True)
        tc_layout = QtWidgets.QVBoxLayout(top_card)
        tc_layout.setContentsMargins(10, 6, 10, 6)

        t_row = QtWidgets.QHBoxLayout()
        lbl_title = QtWidgets.QLabel("🛡 REFERENCE GEAR CHECKLIST (192 MATRIX ITEMS)", top_card)
        lbl_title.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11pt;")
        t_row.addWidget(lbl_title)
        t_row.addStretch()

        self.lbl_gear_showing = QtWidgets.QLabel("Showing: 192 / 192 gears", top_card)
        self.lbl_gear_showing.setStyleSheet("color: #8892b0; font-weight: bold;")
        t_row.addWidget(self.lbl_gear_showing)
        tc_layout.addLayout(t_row)

        b_row = QtWidgets.QHBoxLayout()
        self.lbl_g_total = QtWidgets.QLabel("Total: 192", top_card)
        self.lbl_g_total.setStyleSheet("color: #d0d5e2; font-weight: bold;")
        b_row.addWidget(self.lbl_g_total)

        self.lbl_g_in_ss = QtWidgets.QLabel("📁 In SS: 0 / 192", top_card)
        self.lbl_g_in_ss.setStyleSheet("color: #38ef7d; font-weight: bold;")
        b_row.addWidget(self.lbl_g_in_ss)

        self.lbl_g_conf = QtWidgets.QLabel("🟢 Confirmed: 0 / 192", top_card)
        self.lbl_g_conf.setStyleSheet("color: #00e5ff; font-weight: bold;")
        b_row.addWidget(self.lbl_g_conf)

        self.lbl_g_miss = QtWidgets.QLabel("❌ Missing: 0", top_card)
        self.lbl_g_miss.setStyleSheet("color: #ff5555; font-weight: bold;")
        b_row.addWidget(self.lbl_g_miss)

        self.lbl_g_outliers = QtWidgets.QLabel("⚠️ Outliers: 0", top_card)
        self.lbl_g_outliers.setStyleSheet("color: #ffa500; font-weight: bold;")
        b_row.addWidget(self.lbl_g_outliers)
        b_row.addStretch()
        tc_layout.addLayout(b_row)

        layout.addWidget(top_card)

        # Filter Bar Card
        filter_card = QtWidgets.QFrame(self.tab_gears)
        filter_card.setProperty("card", True)
        fc_layout = QtWidgets.QVBoxLayout(filter_card)
        fc_layout.setContentsMargins(8, 4, 8, 4)

        f_row1 = QtWidgets.QHBoxLayout()
        f_row1.addWidget(QtWidgets.QLabel("Rarity:"))
        self.combo_gear_rarity = QtWidgets.QComboBox(filter_card)
        self.combo_gear_rarity.addItems(["All Rarities", "Common", "Uncommon", "Rare", "Legendary"])
        self.combo_gear_rarity.currentTextChanged.connect(self.apply_gear_filter)
        f_row1.addWidget(self.combo_gear_rarity)

        f_row1.addWidget(QtWidgets.QLabel("Level:"))
        self.combo_gear_level = QtWidgets.QComboBox(filter_card)
        self.combo_gear_level.addItems(["All Levels", "Lv. 50", "Lv. 65", "Lv. 80", "Lv. 90"])
        self.combo_gear_level.currentTextChanged.connect(self.apply_gear_filter)
        f_row1.addWidget(self.combo_gear_level)

        f_row1.addWidget(QtWidgets.QLabel("Status:"))
        self.combo_gear_status = QtWidgets.QComboBox(filter_card)
        self.combo_gear_status.addItems([
            "All Statuses",
            "🟢 Confirmed Detected",
            "📁 Listed in SS (Not Detected)",
            "❌ Missing from SS",
            "⚠️ Size Outliers (<45px)"
        ])
        self.combo_gear_status.currentTextChanged.connect(self.apply_gear_filter)
        f_row1.addWidget(self.combo_gear_status)

        self.entry_gear_search = QtWidgets.QLineEdit(filter_card)
        self.entry_gear_search.setPlaceholderText("Search gear...")
        self.entry_gear_search.textChanged.connect(self.apply_gear_filter)
        f_row1.addWidget(self.entry_gear_search)
        fc_layout.addLayout(f_row1)

        f_row2 = QtWidgets.QHBoxLayout()
        btn_refresh_gear = QtWidgets.QPushButton("🔄 Refresh", filter_card)
        btn_refresh_gear.clicked.connect(self.refresh_gear_checklist_data)
        f_row2.addWidget(btn_refresh_gear)

        btn_test_scan_gear = QtWidgets.QPushButton("🖼 Test Scan", filter_card)
        btn_test_scan_gear.setProperty("role", "primary")
        btn_test_scan_gear.clicked.connect(self.test_scan_and_confirm_action)
        f_row2.addWidget(btn_test_scan_gear)

        btn_snip_gear = QtWidgets.QPushButton("✂ Snip Selected", filter_card)
        btn_snip_gear.setProperty("role", "teal")
        btn_snip_gear.clicked.connect(self.snip_selected_gear_action)
        f_row2.addWidget(btn_snip_gear)

        btn_reset_gear = QtWidgets.QPushButton("🧹 Reset Detections", filter_card)
        btn_reset_gear.setProperty("role", "danger")
        btn_reset_gear.clicked.connect(self.reset_confirmed_gears_action)
        f_row2.addWidget(btn_reset_gear)

        f_row2.addStretch()
        fc_layout.addLayout(f_row2)
        layout.addWidget(filter_card)

        # 144 Items Table
        self.table_gears = QtWidgets.QTableWidget(self.tab_gears)
        self.table_gears.setColumnCount(5)
        self.table_gears.setHorizontalHeaderLabels(["GEAR TYPE", "LEVEL", "RARITY", "SS TEMPLATE", "CONFIRMATION"])
        self.table_gears.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table_gears.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table_gears.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.table_gears.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.table_gears.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
        self.table_gears.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_gears.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table_gears.doubleClicked.connect(lambda: self.snip_selected_gear_action())
        layout.addWidget(self.table_gears, stretch=1)

    # ---------------------------------------------------------
    # TAB 4: MATERIALS
    # ---------------------------------------------------------
    def _build_materials_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_materials)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header Card
        top_card = QtWidgets.QFrame(self.tab_materials)
        top_card.setProperty("card", True)
        tc_layout = QtWidgets.QVBoxLayout(top_card)
        tc_layout.setContentsMargins(10, 6, 10, 6)

        th = QtWidgets.QHBoxLayout()
        lbl_title = QtWidgets.QLabel("📦 MATERIAL LIBRARY & AUTO-STASH (SS_materials/)", top_card)
        lbl_title.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11pt;")
        th.addWidget(lbl_title)
        th.addStretch()
        tc_layout.addLayout(th)

        btn_row = QtWidgets.QHBoxLayout()
        mat_stats = self.bot.vision.get_material_library_stats()
        total_mats = sum(len(v) for v in self.materials_manifest.values()) if hasattr(self, 'materials_manifest') else 47
        self.lbl_mat_status = QtWidgets.QLabel(f"Total: {total_mats} | Loaded: {mat_stats['total']} / {total_mats} templates", top_card)
        self.lbl_mat_status.setStyleSheet("color: #38ef7d; font-weight: bold;")
        btn_row.addWidget(self.lbl_mat_status)
        btn_row.addStretch()

        btn_test_mat = QtWidgets.QPushButton("🧪 Test Stash", top_card)
        btn_test_mat.setProperty("role", "primary")
        btn_test_mat.clicked.connect(self.run_test_material_stash_action)
        btn_row.addWidget(btn_test_mat)

        btn_reload_mat = QtWidgets.QPushButton("🔄 Reload", top_card)
        btn_reload_mat.clicked.connect(self.reload_materials_library_action)
        btn_row.addWidget(btn_reload_mat)
        tc_layout.addLayout(btn_row)

        layout.addWidget(top_card)

        # Editor Bar Card
        edit_card = QtWidgets.QFrame(self.tab_materials)
        edit_card.setProperty("card", True)
        ec_layout = QtWidgets.QHBoxLayout(edit_card)
        ec_layout.setContentsMargins(8, 4, 8, 4)
        ec_layout.setSpacing(8)

        ec_layout.addWidget(QtWidgets.QLabel("Selected:"))
        self.lbl_selected_mat_fn = QtWidgets.QLabel("(select row)", edit_card)
        self.lbl_selected_mat_fn.setStyleSheet("color: #00e5ff; font-weight: bold; font-family: 'Consolas';")
        ec_layout.addWidget(self.lbl_selected_mat_fn)

        ec_layout.addWidget(QtWidgets.QLabel("Name:"))
        self.entry_mat_name = QtWidgets.QLineEdit(edit_card)
        self.entry_mat_name.setFixedWidth(180)
        self.entry_mat_name.returnPressed.connect(self.apply_selected_material_name)
        ec_layout.addWidget(self.entry_mat_name)

        btn_save_name = QtWidgets.QPushButton("💾 Save Name", edit_card)
        btn_save_name.setProperty("role", "success")
        btn_save_name.clicked.connect(self.apply_selected_material_name)
        ec_layout.addWidget(btn_save_name)

        btn_snip_mat = QtWidgets.QPushButton("✂ Snip Selected", edit_card)
        btn_snip_mat.setProperty("role", "teal")
        btn_snip_mat.clicked.connect(self.snip_selected_material_action)
        ec_layout.addWidget(btn_snip_mat)

        ec_layout.addStretch()
        layout.addWidget(edit_card)

        # 42 Materials Table
        self.table_materials = QtWidgets.QTableWidget(self.tab_materials)
        self.table_materials.setColumnCount(4)
        self.table_materials.setHorizontalHeaderLabels(["FILENAME", "MATERIAL NAME", "RARITY", "SS STATUS"])
        self.table_materials.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.table_materials.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table_materials.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.table_materials.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.table_materials.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_materials.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table_materials.itemSelectionChanged.connect(self.on_mat_table_select)
        self.table_materials.doubleClicked.connect(lambda: self.snip_selected_material_action())
        layout.addWidget(self.table_materials, stretch=1)

    # ---------------------------------------------------------
    # TAB 5: CORROSION MATERIALS & CUBE
    # ---------------------------------------------------------
    def _build_corrosion_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_corrosion)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Header Card
        top_card = QtWidgets.QFrame(self.tab_corrosion)
        top_card.setProperty("card", True)
        tc_layout = QtWidgets.QVBoxLayout(top_card)
        tc_layout.setContentsMargins(10, 6, 10, 6)

        th = QtWidgets.QHBoxLayout()
        lbl_title = QtWidgets.QLabel("⚗ CORROSION MATERIALS & CUBE AUTOMATION (MAX 15 ITEMS)", top_card)
        lbl_title.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11pt;")
        th.addWidget(lbl_title)
        th.addStretch()
        tc_layout.addLayout(th)

        btn_row = QtWidgets.QHBoxLayout()
        stats = self.bot.vision.get_corrosion_library_stats()
        self.lbl_corrosion_status = QtWidgets.QLabel(
            f"Total Slots: {len(self.corrosion_manifest)}/15 | Templates Loaded: {stats.get('total', 0)} | Enabled: {stats.get('enabled', 0)}",
            top_card
        )
        self.lbl_corrosion_status.setStyleSheet("color: #38ef7d; font-weight: bold;")
        btn_row.addWidget(self.lbl_corrosion_status)
        btn_row.addStretch()

        self.cb_auto_corrosion = QtWidgets.QCheckBox("Enable Auto-Corrosion Flow (triggers after chest opening)", top_card)
        self.cb_auto_corrosion.setChecked(bool(self.config_data.get("auto_corrosion_enabled", True)))
        self.cb_auto_corrosion.setStyleSheet("color: #00e5ff; font-weight: bold;")
        self.cb_auto_corrosion.toggled.connect(self.toggle_auto_corrosion_action)
        btn_row.addWidget(self.cb_auto_corrosion)

        btn_test_corr = QtWidgets.QPushButton("🧪 Test Corrosion Flow", top_card)
        btn_test_corr.setProperty("role", "primary")
        btn_test_corr.clicked.connect(self.run_test_corrosion_flow_action)
        btn_row.addWidget(btn_test_corr)

        btn_reload_corr = QtWidgets.QPushButton("🔄 Reload", top_card)
        btn_reload_corr.clicked.connect(self.reload_corrosion_library_action)
        btn_row.addWidget(btn_reload_corr)
        tc_layout.addLayout(btn_row)

        layout.addWidget(top_card)

        # 2. Cube Mode Calibration Card
        mode_card = QtWidgets.QFrame(self.tab_corrosion)
        mode_card.setProperty("card", True)
        mc_layout = QtWidgets.QVBoxLayout(mode_card)
        mc_layout.setContentsMargins(10, 6, 10, 6)
        lbl_mhead = QtWidgets.QLabel("🎯 CUBE MODE SWITCH CALIBRATION (Synthesis ⮂ Corrosion)", mode_card)
        lbl_mhead.setStyleSheet("color: #ffd166; font-weight: bold; font-size: 9.5pt;")
        mc_layout.addWidget(lbl_mhead)

        grid_mode = QtWidgets.QGridLayout()
        grid_mode.setHorizontalSpacing(10)
        grid_mode.setVerticalSpacing(4)

        # Dropdown
        self.lbl_cube_mode_dropdown = QtWidgets.QLabel(self._format_cube_mode_dropdown_text(), mode_card)
        btn_sel_mode = QtWidgets.QPushButton("🎯 Select Dropdown", mode_card)
        btn_sel_mode.setProperty("role", "primary")
        btn_sel_mode.clicked.connect(self.calibrate_cube_mode_dropdown_action)
        btn_test_mode = QtWidgets.QPushButton("▶ Test Click Dropdown", mode_card)
        btn_test_mode.setProperty("role", "warning")
        btn_test_mode.clicked.connect(self.test_cube_dropdown_action)
        grid_mode.addWidget(self.lbl_cube_mode_dropdown, 0, 0)
        grid_mode.addWidget(btn_sel_mode, 0, 1)
        grid_mode.addWidget(btn_test_mode, 0, 2)

        # Corrosion Option
        self.lbl_cube_opt_corrosion = QtWidgets.QLabel(self._format_cube_option_corrosion_text(), mode_card)
        btn_sel_corr = QtWidgets.QPushButton("🎯 Select Option", mode_card)
        btn_sel_corr.setProperty("role", "primary")
        btn_sel_corr.clicked.connect(self.calibrate_cube_option_corrosion_action)
        btn_test_corr_mode = QtWidgets.QPushButton("▶ Test Mode Corrosion", mode_card)
        btn_test_corr_mode.setProperty("role", "purple")
        btn_test_corr_mode.clicked.connect(self.test_switch_corrosion_mode_action)
        grid_mode.addWidget(self.lbl_cube_opt_corrosion, 1, 0)
        grid_mode.addWidget(btn_sel_corr, 1, 1)
        grid_mode.addWidget(btn_test_corr_mode, 1, 2)

        # Synthesis Option
        self.lbl_cube_opt_synthesis = QtWidgets.QLabel(self._format_cube_option_synthesis_text(), mode_card)
        btn_sel_synth = QtWidgets.QPushButton("🎯 Select Option", mode_card)
        btn_sel_synth.setProperty("role", "primary")
        btn_sel_synth.clicked.connect(self.calibrate_cube_option_synthesis_action)
        btn_test_synth_mode = QtWidgets.QPushButton("▶ Test Mode Synthesis", mode_card)
        btn_test_synth_mode.setProperty("role", "success")
        btn_test_synth_mode.clicked.connect(self.test_switch_synthesis_mode_action)
        grid_mode.addWidget(self.lbl_cube_opt_synthesis, 2, 0)
        grid_mode.addWidget(btn_sel_synth, 2, 1)
        grid_mode.addWidget(btn_test_synth_mode, 2, 2)

        mc_layout.addLayout(grid_mode)
        layout.addWidget(mode_card)

        # 3. Editor Bar Card
        edit_card = QtWidgets.QFrame(self.tab_corrosion)
        edit_card.setProperty("card", True)
        ec_layout = QtWidgets.QHBoxLayout(edit_card)
        ec_layout.setContentsMargins(8, 4, 8, 4)
        ec_layout.setSpacing(8)

        ec_layout.addWidget(QtWidgets.QLabel("Selected:"))
        self.lbl_selected_corrosion_fn = QtWidgets.QLabel("(select slot)", edit_card)
        self.lbl_selected_corrosion_fn.setStyleSheet("color: #00e5ff; font-weight: bold; font-family: 'Consolas';")
        ec_layout.addWidget(self.lbl_selected_corrosion_fn)

        ec_layout.addWidget(QtWidgets.QLabel("Custom Name:"))
        self.entry_corrosion_name = QtWidgets.QLineEdit(edit_card)
        self.entry_corrosion_name.setFixedWidth(160)
        self.entry_corrosion_name.returnPressed.connect(self.apply_selected_corrosion_name)
        ec_layout.addWidget(self.entry_corrosion_name)

        btn_save_name = QtWidgets.QPushButton("💾 Save Name", edit_card)
        btn_save_name.setProperty("role", "success")
        btn_save_name.clicked.connect(self.apply_selected_corrosion_name)
        ec_layout.addWidget(btn_save_name)

        btn_snip_corr = QtWidgets.QPushButton("✂ Snip Selected", edit_card)
        btn_snip_corr.setProperty("role", "teal")
        btn_snip_corr.clicked.connect(self.snip_selected_corrosion_action)
        ec_layout.addWidget(btn_snip_corr)

        btn_add_slot = QtWidgets.QPushButton("➕ Add Slot (Max 15)", edit_card)
        btn_add_slot.setProperty("role", "indigo")
        btn_add_slot.clicked.connect(self.add_corrosion_slot_action)
        ec_layout.addWidget(btn_add_slot)

        btn_remove_slot = QtWidgets.QPushButton("🗑 Remove Slot", edit_card)
        btn_remove_slot.setProperty("role", "danger")
        btn_remove_slot.clicked.connect(self.remove_corrosion_slot_action)
        ec_layout.addWidget(btn_remove_slot)

        ec_layout.addStretch()
        layout.addWidget(edit_card)

        # 4. Table (Max 15 items)
        self.table_corrosion = QtWidgets.QTableWidget(self.tab_corrosion)
        self.table_corrosion.setColumnCount(5)
        self.table_corrosion.setHorizontalHeaderLabels(["#", "ENABLE", "MATERIAL NAME (CUSTOM)", "FILENAME", "STATUS"])
        self.table_corrosion.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.table_corrosion.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table_corrosion.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.table_corrosion.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.table_corrosion.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        self.table_corrosion.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_corrosion.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table_corrosion.itemSelectionChanged.connect(self.on_corrosion_table_select)
        self.table_corrosion.doubleClicked.connect(lambda: self.snip_selected_corrosion_action())
        layout.addWidget(self.table_corrosion, stretch=1)

    # ---------------------------------------------------------
    # THREAD-SAFE GUI SLOTS
    # ---------------------------------------------------------
    @Slot(str, str)
    def _slot_status(self, text: str, color: str):
        self.lbl_status.setText(f"STATUS: {text}")
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11pt;")

    @Slot(str, str)
    def _slot_log(self, msg: str, level: str):
        # 1. Normalize level name
        level = level.lower().strip()
        if level in ("danger", "err"):
            level = "error"
        elif level in ("warn",):
            level = "warning"

        # 2. Strip any incoming duplicate timestamp prefix (prevents double timestamp)
        clean_msg = re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s*", "", msg)
        time_tag = time.strftime("[%H:%M:%S]")

        # 3. Buffer in memory history (up to 1000 items)
        self.log_history.append((time_tag, level, clean_msg))
        if len(self.log_history) > 1000:
            self.log_history.pop(0)

        # 4. Check if current category is active in filter checkboxes
        cb = self.log_filter_cbs.get(level)
        if cb is not None and not cb.isChecked():
            return

        # 4b. Check verbosity filter
        if not self._is_log_visible_by_verbosity(clean_msg, level):
            return

        # 5. Render styled HTML line
        color_map = {
            "info": "#d0d5e2",
            "success": "#38ef7d",
            "warning": "#ffd166",
            "error": "#ff5555"
        }
        col = color_map.get(level, "#d0d5e2")
        html = f'<span style="color: #6272a4;">{time_tag}</span> <span style="color: {col};">{clean_msg}</span>'
        self.log_text.append(html)

    def _is_log_visible_by_verbosity(self, clean_msg: str, level: str) -> bool:
        """Determines if a log message should be displayed given current verbosity."""
        if level in ("warning", "error", "success", "danger"):
            return True

        verbosity = getattr(self, "current_log_verbosity", "Clean")
        if verbosity == "Verbose":
            return True

        m_lower = clean_msg.lower()

        # In Normal and Clean: filter out raw CV math / pixel diffs
        if "pixel diff:" in m_lower or "target depth:" in m_lower or "measured shift=" in m_lower:
            return False

        if verbosity == "Normal":
            return True

        # In Clean mode: additionally filter out repetitive micro-actions
        if "2x left-click on slot (0,0)" in m_lower or "regaining inventory focus" in m_lower or "activating scroll focus" in m_lower:
            return False
        if "clicking inventory sort button" in m_lower or "inventory sorted successfully" in m_lower or "sorting inventory" in m_lower:
            return False
        if "scrolling up to top row" in m_lower or "resetting inventory" in m_lower or "slowly scrolling down" in m_lower or "scrolling down to bottom" in m_lower:
            return False
        if re.search(r"step\s+[1-5]/[2-5]:", m_lower):
            return False
        if "step 2: visually inspecting chest area" in m_lower:
            return False

        return True

    def on_log_verbosity_changed(self, idx: int):
        modes = ["Clean", "Normal", "Verbose"]
        self.current_log_verbosity = modes[idx] if 0 <= idx < len(modes) else "Clean"
        self.config_data["log_verbosity"] = self.current_log_verbosity
        self.save_config(show_dialog=False)
        self.on_log_filter_changed()

    def on_log_filter_changed(self):
        # Save filter preferences to config
        filters = {lvl: cb.isChecked() for lvl, cb in self.log_filter_cbs.items()}
        self.config_data["log_filters"] = filters

        # Re-render log_text from history based on active categories and verbosity
        self.log_text.clear()
        color_map = {
            "info": "#d0d5e2",
            "success": "#38ef7d",
            "warning": "#ffd166",
            "error": "#ff5555"
        }
        lines = []
        for time_tag, level, clean_msg in self.log_history:
            if self.log_filter_cbs.get(level) is None or self.log_filter_cbs[level].isChecked():
                if self._is_log_visible_by_verbosity(clean_msg, level):
                    col = color_map.get(level, "#d0d5e2")
                    lines.append(f'<span style="color: #6272a4;">{time_tag}</span> <span style="color: {col};">{clean_msg}</span>')
        if lines:
            self.log_text.setHtml("<br>".join(lines))
            sb = self.log_text.verticalScrollBar()
            sb.setValue(sb.maximum())

    def clear_logs_action(self):
        self.log_history.clear()
        self.log_text.clear()

    @Slot(str, int)
    def _slot_countdown(self, time_str: str, seconds: int):
        self.lbl_timer.setText(time_str)
        total = max(1, self.bot.interval_seconds)
        pct = int(((total - seconds) / total) * 100)
        self.progress_bar.setValue(min(100, max(0, pct)))

    @Slot(dict)
    def _slot_buckets(self, counts: dict):
        if not counts:
            return
        for (bracket, rarity), lbl in self.lbl_counts.items():
            if (bracket, rarity) in counts:
                val = counts[(bracket, rarity)]
            elif bracket in counts and isinstance(counts[bracket], dict):
                val = counts[bracket].get(rarity, 0)
            elif f"tier_{bracket}" in counts and isinstance(counts[f"tier_{bracket}"], dict):
                val = counts[f"tier_{bracket}"].get(rarity, 0)
            else:
                val = 0
            lbl.setText(f"{rarity}: {val}")

    @Slot(int)
    def _slot_progress(self, pct: int):
        self.progress_bar.setValue(min(100, max(0, pct)))

    def append_log(self, msg: str, level: str = "info"):
        self._slot_log(msg, level)

    # ---------------------------------------------------------
    # DATA & LOGIC CONTROLLERS
    # ---------------------------------------------------------
    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            example_cfg = os.path.join(os.path.dirname(self.config_path), "config.example.json")
            if os.path.exists(example_cfg):
                import shutil
                try:
                    shutil.copyfile(example_cfg, self.config_path)
                except Exception:
                    pass
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self, show_dialog: bool = True):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)
            self.bot.reload_config()
            self.append_log("Configuration saved to config.json successfully.", "success")
            if show_dialog:
                QtWidgets.QMessageBox.information(
                    self,
                    "Save Successful",
                    "✅ Configuration saved to config.json successfully!"
                )
        except Exception as e:
            self.append_log(f"Error saving config: {e}", "warning")
            if show_dialog:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Save Error",
                    f"❌ Failed to save configuration:\n{e}"
                )

    def load_confirmed_gears(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.confirmed_gears_path):
            try:
                with open(self.confirmed_gears_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_confirmed_gears(self):
        try:
            with open(self.confirmed_gears_path, "w", encoding="utf-8") as f:
                json.dump(self.confirmed_gears, f, indent=2)
        except Exception:
            pass

    def load_materials_manifest(self) -> Dict[str, List[Dict[str, Any]]]:
        if os.path.exists(self.materials_manifest_path):
            try:
                with open(self.materials_manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        if "common" not in data:
                            data["common"] = [
                                {"id": f"c-mat_{i}", "name": f"Common Mat {i}", "filename": f"c-mat_{i}.png"}
                                for i in range(1, 6)
                            ]
                        return data
            except Exception:
                pass
        return {}

    def save_materials_manifest(self):
        try:
            with open(self.materials_manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.materials_manifest, f, indent=2)
        except Exception:
            pass

    def record_detected_items(self, items: List[Dict[str, Any]]):
        dirty = False
        for itm in items:
            fn = itm.get("ref_file") or itm.get("template_fn") or itm.get("filename")
            if fn:
                self.confirmed_gears[fn] = {
                    "confirmed": True,
                    "score": round(float(itm.get("score", 1.0)), 3),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                dirty = True
        if dirty:
            self.save_confirmed_gears()
            self.refresh_gear_checklist_data()

    # ---------------------------------------------------------
    # ACTIONS & TESTING
    # ---------------------------------------------------------
    def start_cycle_action(self):
        self.bot.reset_abort_state()
        if not self.bot.auto_loop_enabled:
            self.bot.toggle_auto_loop()
            self.cb_auto_loop.setChecked(True)
        self.bot.start_cycle_async()
        self.append_log("Manual cycle execution triggered.", "info")

    def stop_cycle_action(self):
        self.bot.trigger_emergency_stop()
        if self.bot.auto_loop_enabled:
            self.bot.toggle_auto_loop()
            self.cb_auto_loop.setChecked(False)
        self._slot_status("Stopped by User", "#ff5555")
        self.append_log("Emergency stop requested. Automation stopped.", "danger")

    def pause_cycle_action(self):
        is_running = self.bot.toggle_auto_loop()
        self.cb_auto_loop.setChecked(is_running)

    def _on_interval_changed(self, text: str):
        int_map = {"30m": 30, "60m": 60, "90m": 90, "120m (Default)": 120, "180m": 180}
        mins = int_map.get(text, 120)
        self.bot.set_timer_interval(mins)
        self.config_data["timer_interval_minutes"] = mins
        self.save_config()

    def toggle_auto_loop_action(self, checked: bool):
        if self.bot.auto_loop_enabled != checked:
            self.bot.toggle_auto_loop()

    def toggle_3corner_rarity_action(self, checked: bool):
        self.config_data["multi_corner_rarity_enabled"] = checked
        self.save_config()
        self.bot.reload_config()
        self.append_log(f"3-Corner Rarity set to: {'ENABLED' if checked else 'DISABLED'}", "info")

    def toggle_full_inv_action(self, checked: bool):
        self.config_data["full_inventory_anticipation"] = checked
        self.config_data["full_inventory_anticipation_enabled"] = checked
        self.save_config()
        self.bot.reload_config()
        self.chk_calib_full_inv.setChecked(checked)
        self.cb_full_inv.setChecked(checked)
        self.append_log(f"Full Inventory Anticipation set to: {'ENABLED' if checked else 'DISABLED'}", "info")

    def toggle_auto_tier_action(self, checked: bool):
        self.config_data["auto_select_cube_tier"] = checked
        self.save_config()
        self.bot.reload_config()

    def open_visual_debugger_action(self):
        if not self.debugger_window or not self.debugger_window.isVisible():
            self.debugger_window = QtVisualDebugger(self, self.bot.vision, self.config_data)
            self.debugger_window.show()
        else:
            self.debugger_window.raise_()
            self.debugger_window.activateWindow()

    def open_assets_folder_action(self):
        os.makedirs(self.assets_dir, exist_ok=True)
        os.startfile(os.path.abspath(self.assets_dir))

    def run_test_synthesis_action(self):
        def _worker():
            self.append_log("Testing Synthesis loading flow in background...", "info")
            loaded, t_label, rarity = self.bot.test_synthesis_loading()
            self.append_log(f"Synthesis Test Completed: Loaded {loaded}/9 gears ({t_label} {rarity}).", "success" if loaded >= 9 else "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def run_test_chest_action(self):
        def _worker():
            self.append_log("Testing Chest detection and opening...", "info")
            opened = self.bot.execute_chest_opening_flow()
            self.append_log(f"Chest Opening Test Finished: Opened {opened} chests.", "info")
        threading.Thread(target=_worker, daemon=True).start()

    def run_test_material_stash_action(self):
        def _worker():
            self.append_log("Testing Material Auto-Stash flow...", "info")
            stashed = self.bot.test_stash_transfer()
            self.append_log(f"Material Auto-Stash Finished: {stashed} materials stashed.", "info")
        threading.Thread(target=_worker, daemon=True).start()

    def run_test_visual_scan_action(self):
        self.open_visual_debugger_action()

    def run_test_scroll_action(self):
        def _worker():
            self.append_log("Testing Win32 mouse scroll down...", "info")
            self.bot.wheel_scroll(down=True, ticks=5)
        threading.Thread(target=_worker, daemon=True).start()

    def run_test_single_step_scroll_action(self):
        def _worker():
            self.append_log("Performing single-step scroll test...", "info")
            self.bot.wheel_scroll(down=True, ticks=2)
        threading.Thread(target=_worker, daemon=True).start()

    # ---------------------------------------------------------
    # CALIBRATION ACTIONS & SNIPPERS
    # ---------------------------------------------------------
    def _format_roi_text(self, roi_key: str) -> str:
        roi = self.config_data.get("rois", {}).get(roi_key, {})
        tag = "Chest" if "chest" in roi_key else "Inv Grid"
        return f"{tag}: {roi.get('width', 0)}x{roi.get('height', 0)} ({roi.get('x', 0)}, {roi.get('y', 0)})"

    def _format_synth_btn_text(self) -> str:
        sc = self.config_data.get("button_coords", {}).get("cube_synth_btn") or self.config_data.get("button_coords", {}).get("synth_btn", {})
        return f"Synth Button: ({sc.get('x', 0)}, {sc.get('y', 0)})"

    def _format_auto_fill_btn_text(self) -> str:
        af = self.config_data.get("button_coords", {}).get("cube_auto_fill_btn") or self.config_data.get("button_coords", {}).get("auto_fill_btn", {})
        return f"Auto Fill Button: ({af.get('x', 0)}, {af.get('y', 0)})"

    def _format_stash_slot_text(self) -> str:
        ss = self.config_data.get("button_coords", {}).get("stash_slot", {})
        return f"Stash Slot: ({ss.get('x', 0)}, {ss.get('y', 0)})"

    def _format_cube_dropdown_text(self) -> str:
        cd = self.config_data.get("button_coords", {}).get("cube_dropdown", {})
        return f"Cube Dropdown: ({cd.get('x', 0)}, {cd.get('y', 0)})"

    def _format_tier_80_90_text(self) -> str:
        t80 = self.config_data.get("button_coords", {}).get("tier_80_90", {})
        return f"Tier Lv.80~90: ({t80.get('x', 0)}, {t80.get('y', 0)})"

    def _format_tier_65_80_text(self) -> str:
        t65 = self.config_data.get("button_coords", {}).get("tier_65_80", {})
        return f"Tier Lv.65~80: ({t65.get('x', 0)}, {t65.get('y', 0)})"

    def _format_cube_mode_dropdown_text(self) -> str:
        cmd = self.config_data.get("button_coords", {}).get("cube_mode_dropdown", {})
        return f"Mode Dropdown: ({cmd.get('x', 0)}, {cmd.get('y', 0)})"

    def _format_cube_option_corrosion_text(self) -> str:
        coc = self.config_data.get("button_coords", {}).get("cube_option_corrosion", {})
        return f"Option Corrosion: ({coc.get('x', 0)}, {coc.get('y', 0)})"

    def _format_cube_option_synthesis_text(self) -> str:
        cos = self.config_data.get("button_coords", {}).get("cube_option_synthesis", {})
        return f"Option Synthesis: ({cos.get('x', 0)}, {cos.get('y', 0)})"

    def _format_stash_tab_1_text(self) -> str:
        s1 = self.config_data.get("button_coords", {}).get("stash_tab_1", {})
        return f"Stash 1: ({s1.get('x', 0)}, {s1.get('y', 0)})"

    def _format_stash_tab_2_text(self) -> str:
        s2 = self.config_data.get("button_coords", {}).get("stash_tab_2", {})
        return f"Stash 2: ({s2.get('x', 0)}, {s2.get('y', 0)})"

    def _format_stash_tab_material_text(self) -> str:
        sm = self.config_data.get("button_coords", {}).get("stash_tab_material", {})
        return f"Stash Material: ({sm.get('x', 0)}, {sm.get('y', 0)})"

    def _format_tier_50_text(self) -> str:
        t50 = self.config_data.get("button_coords", {}).get("tier_50", {})
        return f"Tier Lv.50: ({t50.get('x', 0)}, {t50.get('y', 0)})"

    def _format_stash_grid_roi_text(self) -> str:
        sgrid = self.config_data.get("rois", {}).get("stash_grid", {})
        return f"Stash Grid: {sgrid.get('width', 0)}x{sgrid.get('height', 0)} ({sgrid.get('x', 0)}, {sgrid.get('y', 0)})"

    def snip_roi_action(self, roi_key: str, title: str, label_widget: QtWidgets.QLabel):
        def on_done(res):
            if "rois" not in self.config_data:
                self.config_data["rois"] = {}
            self.config_data["rois"][roi_key] = {"x": res["x"], "y": res["y"], "width": res["width"], "height": res["height"]}
            self.save_config()
            label_widget.setText(f"{roi_key}: {res['width']}x{res['height']} ({res['x']}, {res['y']})")
            if roi_key == "inventory_grid":
                self.entry_inv_w.setText(str(res["width"]))
                self.entry_inv_h.setText(str(res["height"]))
            self.append_log(f"Calibrated ROI for {roi_key}: {res['width']}x{res['height']} at ({res['x']}, {res['y']})", "info")

        self.snipper = QtScreenSnipper(mode="roi", title=title, on_complete=on_done)

    def calibrate_point_action(self, coord_key: str, title: str, label_widget: QtWidgets.QLabel):
        def on_done(res):
            if "button_coords" not in self.config_data:
                self.config_data["button_coords"] = {}
            cx = res["x"] + res["width"] // 2 if not res.get("is_point") else res["x"]
            cy = res["y"] + res["height"] // 2 if not res.get("is_point") else res["y"]
            self.config_data["button_coords"][coord_key] = {"x": cx, "y": cy}
            self.save_config()
            label_widget.setText(f"{title}: ({cx}, {cy})")
            self.append_log(f"Calibrated {title} point: ({cx}, {cy})", "info")

        self.snipper = QtScreenSnipper(mode="point", title=title, on_complete=on_done)

    def calibrate_synth_btn_action(self):
        self.calibrate_point_action("cube_synth_btn", "Synth Button", self.lbl_synth_btn)

    def test_click_synth_btn_action(self):
        def _worker():
            self.bot.click_synth_button()
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_stash_slot_action(self):
        self.calibrate_point_action("stash_slot", "Stash Slot", self.lbl_stash_slot)

    def test_stash_drag_action(self):
        def _worker():
            self.bot.test_stash_transfer()
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_cube_dropdown_action(self):
        self.calibrate_point_action("cube_dropdown", "Cube Dropdown", self.lbl_cube_dropdown)

    def test_cube_dropdown_action(self):
        def _worker():
            self.bot.test_cube_tier_selection()
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_tier_80_90_action(self):
        self.calibrate_point_action("tier_80_90", "Tier Lv.80~90", self.lbl_tier_80_90)

    def calibrate_tier_65_80_action(self):
        self.calibrate_point_action("tier_65_80", "Tier Lv.65~80", self.lbl_tier_65_80)

    def calibrate_cube_mode_dropdown_action(self):
        def on_done(res):
            if "button_coords" not in self.config_data:
                self.config_data["button_coords"] = {}
            cx = res["x"] + res["width"] // 2 if not res.get("is_point") else res["x"]
            cy = res["y"] + res["height"] // 2 if not res.get("is_point") else res["y"]
            self.config_data["button_coords"]["cube_mode_dropdown"] = {"x": cx, "y": cy}
            self.save_config()
            txt = self._format_cube_mode_dropdown_text()
            if hasattr(self, "lbl_cube_mode_dropdown"):
                self.lbl_cube_mode_dropdown.setText(txt)
            if hasattr(self, "lbl_calib_cube_mode"):
                self.lbl_calib_cube_mode.setText(txt)
            self.append_log(f"Calibrated Cube Mode Dropdown point: ({cx}, {cy})", "info")
        self.snipper = QtScreenSnipper(mode="point", title="Cube Mode Dropdown", on_complete=on_done)

    def calibrate_cube_option_corrosion_action(self):
        def on_done(res):
            if "button_coords" not in self.config_data:
                self.config_data["button_coords"] = {}
            cx = res["x"] + res["width"] // 2 if not res.get("is_point") else res["x"]
            cy = res["y"] + res["height"] // 2 if not res.get("is_point") else res["y"]
            self.config_data["button_coords"]["cube_option_corrosion"] = {"x": cx, "y": cy}
            self.save_config()
            txt = self._format_cube_option_corrosion_text()
            if hasattr(self, "lbl_cube_opt_corrosion"):
                self.lbl_cube_opt_corrosion.setText(txt)
            if hasattr(self, "lbl_calib_cube_corr"):
                self.lbl_calib_cube_corr.setText(txt)
            self.append_log(f"Calibrated Cube Option Corrosion point: ({cx}, {cy})", "info")
        self.snipper = QtScreenSnipper(mode="point", title="Cube Option Corrosion", on_complete=on_done)

    def calibrate_cube_option_synthesis_action(self):
        def on_done(res):
            if "button_coords" not in self.config_data:
                self.config_data["button_coords"] = {}
            cx = res["x"] + res["width"] // 2 if not res.get("is_point") else res["x"]
            cy = res["y"] + res["height"] // 2 if not res.get("is_point") else res["y"]
            self.config_data["button_coords"]["cube_option_synthesis"] = {"x": cx, "y": cy}
            self.save_config()
            txt = self._format_cube_option_synthesis_text()
            if hasattr(self, "lbl_cube_opt_synthesis"):
                self.lbl_cube_opt_synthesis.setText(txt)
            if hasattr(self, "lbl_calib_cube_synth"):
                self.lbl_calib_cube_synth.setText(txt)
            self.append_log(f"Calibrated Cube Option Synthesis point: ({cx}, {cy})", "info")
        self.snipper = QtScreenSnipper(mode="point", title="Cube Option Synthesis", on_complete=on_done)

    def test_switch_corrosion_mode_action(self):
        def _worker():
            self.append_log("Testing switch to Cube Corrosion mode...", "info")
            res = self.bot.synthesis.test_switch_cube_mode("corrosion")
            if res:
                self.append_log("Cube mode switch to Corrosion succeeded.", "success")
            else:
                self.append_log("Cube mode switch to Corrosion failed.", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def test_switch_synthesis_mode_action(self):
        def _worker():
            self.append_log("Testing switch to Cube Synthesis mode...", "info")
            res = self.bot.synthesis.test_switch_cube_mode("synthesis")
            if res:
                self.append_log("Cube mode switch to Synthesis succeeded.", "success")
            else:
                self.append_log("Cube mode switch to Synthesis failed.", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_stash_tab_1_action(self):
        self.calibrate_point_action("stash_tab_1", "Stash Tab 1", self.lbl_stash_tab_1)

    def test_click_stash_tab_1_action(self):
        pt = self.config_data.get("button_coords", {}).get("stash_tab_1")
        if not pt or "x" not in pt or "y" not in pt:
            self.append_log("Stash Tab 1 coordinates not calibrated!", "warning")
            return
        def _worker():
            self.append_log(f"Testing click on Stash Tab 1 at ({pt['x']}, {pt['y']})...", "info")
            self.bot.click_point(pt["x"], pt["y"], delay_after=0.2)
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_stash_tab_2_action(self):
        self.calibrate_point_action("stash_tab_2", "Stash Tab 2", self.lbl_stash_tab_2)

    def test_click_stash_tab_2_action(self):
        pt = self.config_data.get("button_coords", {}).get("stash_tab_2")
        if not pt or "x" not in pt or "y" not in pt:
            self.append_log("Stash Tab 2 coordinates not calibrated!", "warning")
            return
        def _worker():
            self.append_log(f"Testing click on Stash Tab 2 at ({pt['x']}, {pt['y']})...", "info")
            self.bot.click_point(pt["x"], pt["y"], delay_after=0.2)
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_stash_tab_material_action(self):
        self.calibrate_point_action("stash_tab_material", "Stash Material Tab", self.lbl_stash_tab_material)

    def test_click_stash_tab_material_action(self):
        pt = self.config_data.get("button_coords", {}).get("stash_tab_material")
        if not pt or "x" not in pt or "y" not in pt:
            self.append_log("Stash Material Tab coordinates not calibrated!", "warning")
            return
        def _worker():
            self.append_log(f"Testing click on Stash Material Tab at ({pt['x']}, {pt['y']})...", "info")
            self.bot.click_point(pt["x"], pt["y"], delay_after=0.2)
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_tier_50_action(self):
        self.calibrate_point_action("tier_50", "Tier Lv.50 Option", self.lbl_tier_50)

    def test_click_tier_50_action(self):
        def _worker():
            self.append_log("Testing Cube Tier Lv. 50 selection...", "info")
            ok = self.bot.synthesis.select_cube_tier("50")
            if ok:
                self.append_log("Successfully selected Cube Tier Lv. 50!", "success")
            else:
                self.append_log("Failed to select Cube Tier Lv. 50 (check dropdown and tier coords).", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_stash_grid_roi_action(self):
        self.snip_roi_action("stash_grid", "Stash Grid ROI", self.lbl_stash_grid_roi)

    def test_scan_stash_grid_action(self):
        def _worker():
            self.append_log("Testing Stash Grid scan for Lv. 50 items...", "info")
            res = self.bot.vision.scan_stash_for_lvl50()
            items = res.get("items", []) if isinstance(res, dict) else res
            counts = res.get("counts", {}) if isinstance(res, dict) else {}
            self.append_log(f"Stash Grid Scan complete: {len(items)} Lv. 50 item(s) found.", "success")
            for itm in items:
                self.append_log(f"  • {itm.get('rarity')} {itm.get('name')} at ({itm['click_x']}, {itm['click_y']})", "info")
            c_cnt = counts.get("Common", 0)
            u_cnt = counts.get("Uncommon", 0)
            r_cnt = counts.get("Rare", 0)
            self.append_log(f"Counts: Common: {c_cnt}, Uncommon: {u_cnt}, Rare: {r_cnt}", "info")
            if isinstance(res, dict) and res.get("is_ready"):
                self.append_log(f"Synthesis Ready: {res.get('ready_rarity')} has reached >= 9 items!", "success")
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_auto_fill_btn_action(self):
        self.calibrate_point_action("cube_auto_fill_btn", "Auto Fill Button", self.lbl_auto_fill_btn)

    def test_autofill_synth_action(self):
        def _worker():
            self.append_log("Testing native Auto-Fill Synthesis flow (Lv. 80~90)...", "info")
            ok = self.bot.execute_autofill_synthesis_flow()
            if ok:
                self.append_log("Auto-Fill Synthesis test succeeded!", "success")
            else:
                self.append_log("Auto-Fill Synthesis test finished with warnings or failed.", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def toggle_autofill_synth_action(self, checked: bool):
        self.config_data["autofill_synth_enabled"] = checked
        self.save_config()
        self.bot.reload_config()
        self.append_log(f"Auto-Fill Synthesis (every 5 unstopped loops) set to: {checked}", "info")

    def apply_manual_dimensions_action(self):
        try:
            w_val = int(self.entry_inv_w.text().strip())
            h_val = int(self.entry_inv_h.text().strip())
            scroll_w = int(self.entry_scroll_w.text().strip())
            sdepth_val = int(self.entry_scroll_depth.text().strip())
            conf_pct = float(self.entry_conf_thresh.text().strip())
            badge_pct = float(self.entry_badge_thresh.text().strip())
            bw_val = int(self.entry_badge_w.text().strip())
            bh_val = int(self.entry_badge_h.text().strip())

            if "rois" not in self.config_data:
                self.config_data["rois"] = {}
            if "inventory_grid" not in self.config_data["rois"]:
                self.config_data["rois"]["inventory_grid"] = {}
            self.config_data["rois"]["inventory_grid"]["width"] = w_val
            self.config_data["rois"]["inventory_grid"]["height"] = h_val

            if "grid_settings" not in self.config_data:
                self.config_data["grid_settings"] = {}
            self.config_data["grid_settings"]["scroll_strip_width"] = scroll_w
            self.config_data["grid_settings"]["scroll_depth_px"] = sdepth_val

            self.config_data["confidence_threshold"] = round(conf_pct / 100.0, 2)
            self.config_data["badge_match_threshold"] = round(badge_pct / 100.0, 2)
            self.config_data["badge_detector_width"] = bw_val
            self.config_data["badge_detector_height"] = bh_val

            self.save_config()
            self.lbl_inv_roi.setText(self._format_roi_text("inventory_grid"))
            self.append_log(f"Applied settings: Conf={conf_pct}% | Inv={w_val}x{h_val}px | Badge={bw_val}x{bh_val}px", "info")
        except Exception as e:
            self.append_log(f"Error applying manual settings: {e}", "warning")

    # ---------------------------------------------------------
    # ASSET CHECKLIST TABLE
    # ---------------------------------------------------------
    def refresh_all_asset_statuses(self):
        self.table_templates.setRowCount(0)
        for row, item in enumerate(TEMPLATE_MANIFEST):
            fn = item["filename"]
            cat = item.get("category", "")
            desc = item.get("desc", "")
            is_loaded, status_str, dims = self.bot.vision.get_template_status(fn)

            self.table_templates.insertRow(row)
            item_fn = QtWidgets.QTableWidgetItem(fn)
            item_cat = QtWidgets.QTableWidgetItem(cat)

            item_status = QtWidgets.QTableWidgetItem(status_str)
            item_status.setForeground(QColor("#38ef7d" if is_loaded else "#ff5555"))
            item_status.setTextAlignment(Qt.AlignCenter)

            item_desc = QtWidgets.QTableWidgetItem(desc)
            item_desc.setForeground(QColor("#8892b0"))

            self.table_templates.setItem(row, 0, item_fn)
            self.table_templates.setItem(row, 1, item_cat)
            self.table_templates.setItem(row, 2, item_status)
            self.table_templates.setItem(row, 3, item_desc)

    def snip_selected_template_action(self):
        sel = self.table_templates.selectedItems()
        if not sel:
            QtWidgets.QMessageBox.information(self, "Select Template", "Please select a template row from the table first.")
            return
        row = sel[0].row()
        fn = self.table_templates.item(row, 0).text()

        def on_done(res):
            self.refresh_all_asset_statuses()
            self.bot.vision.reload_all_templates()
            self.append_log(f"Snipped and saved template {fn} to assets/", "success")

        self.snipper = QtScreenSnipper(
            mode="template",
            title=f"Snip Template: {fn}",
            template_filename=fn,
            save_dir=self.assets_dir,
            on_complete=on_done
        )

    def reload_ss_library_action(self):
        stats = self.bot.vision.reload_reference_gear_library()
        self.lbl_ss_status.setText(stats["status_text"])
        self.lbl_ss_status.setStyleSheet("color: #38ef7d; font-weight: bold;" if stats["loaded"] else "color: #ff5555; font-weight: bold;")
        rc = stats["rarity_counts"]
        lc = stats["level_counts"]
        self.lbl_ss_breakdown.setText(
            f"Rarities: Common: {rc['Common']} | Uncommon: {rc['Uncommon']} | Rare: {rc['Rare']} | Legendary: {rc['Legendary']}\n"
            f"Levels: Lv.65: {lc['65']} | Lv.80: {lc['80']} | Lv.90: {lc['90']}\n"
            "Strict Filter: Only gear matching images in SS/ is counted or synthesized. Unmatched items are skipped."
        )
        self.append_log(f"Reloaded SS/ gear library: {stats['total']} templates active.", "info")

    # ---------------------------------------------------------
    # GEAR CHECKLIST TABLE (144 ITEMS)
    # ---------------------------------------------------------
    def _init_gear_metadata(self):
        self.all_gear_items = []
        for r_code, r_name, r_color in RARITIES_ORDER:
            for lv in LEVELS_ORDER:
                for g_name in GEAR_NAMES:
                    fn = f"{r_code}-{lv}-{g_name}.png"
                    icon = GEAR_ICONS.get(g_name, "🗡️")
                    self.all_gear_items.append({
                        "filename": fn,
                        "gear_name": g_name,
                        "display_name": f"{icon} {g_name.capitalize()}",
                        "rarity": r_name,
                        "r_code": r_code,
                        "r_color": r_color,
                        "level": lv
                    })

    def refresh_gear_checklist_data(self):
        if not self.all_gear_items:
            return

        total_items = len(self.all_gear_items)
        in_ss_count = 0
        confirmed_count = 0
        missing_count = 0
        outlier_count = 0

        for itm in self.all_gear_items:
            fn = itm["filename"]
            p = os.path.join(self.ss_dir, fn)
            exists = os.path.exists(p)

            dims = self.ss_file_cache.get(fn)
            if exists:
                in_ss_count += 1
                if dims is None:
                    img = cv2.imread(p)
                    dims = (img.shape[1], img.shape[0]) if img is not None else (0, 0)
                    self.ss_file_cache[fn] = dims
                w, h = dims
                if w > 0 and (w < 45 or h < 45):
                    itm["is_outlier"] = True
                    outlier_count += 1
                    itm["ss_text"] = f"⚠️ {w}x{h} px (Small)"
                else:
                    itm["is_outlier"] = False
                    itm["ss_text"] = f"📁 {w}x{h} px"
            else:
                itm["is_outlier"] = False
                missing_count += 1
                itm["ss_text"] = "❌ Missing"

            if fn in self.confirmed_gears and self.confirmed_gears[fn].get("confirmed"):
                confirmed_count += 1
                itm["conf_text"] = "🟢 Confirmed Detected ✅"
                itm["state_key"] = "detected"
            elif exists:
                itm["conf_text"] = "⬜ Listed in SS"
                itm["state_key"] = "listed"
            else:
                itm["conf_text"] = "❌ Missing from SS"
                itm["state_key"] = "missing"

        self.lbl_g_in_ss.setText(f"📁 In SS: {in_ss_count} / {total_items}")
        self.lbl_g_conf.setText(f"🟢 Confirmed: {confirmed_count} / {total_items}")
        self.lbl_g_miss.setText(f"❌ Missing: {missing_count}")
        self.lbl_g_outliers.setText(f"⚠️ Outliers: {outlier_count}")

        self.apply_gear_filter()

    def apply_gear_filter(self):
        sel_rarity = self.combo_gear_rarity.currentText()
        sel_level = self.combo_gear_level.currentText()
        sel_status = self.combo_gear_status.currentText()
        search_q = self.entry_gear_search.text().strip().lower()

        filtered = []
        for itm in self.all_gear_items:
            if sel_rarity != "All Rarities" and itm["rarity"] != sel_rarity:
                continue
            if sel_level != "All Levels" and f"Lv. {itm['level']}" != sel_level:
                continue
            if sel_status != "All Statuses":
                if sel_status.startswith("🟢") and itm["state_key"] != "detected":
                    continue
                if sel_status.startswith("📁") and (itm["state_key"] != "listed" or itm.get("is_outlier")):
                    continue
                if sel_status.startswith("❌") and itm["state_key"] != "missing":
                    continue
                if sel_status.startswith("⚠️") and not itm.get("is_outlier"):
                    continue
            if search_q and search_q not in itm["gear_name"] and search_q not in itm["filename"].lower():
                continue
            filtered.append(itm)

        self.table_gears.setRowCount(0)
        for row, itm in enumerate(filtered):
            self.table_gears.insertRow(row)
            item_name = QtWidgets.QTableWidgetItem(itm["display_name"])
            item_name.setData(Qt.UserRole, itm["filename"])

            item_lv = QtWidgets.QTableWidgetItem(f"Lv.{itm['level']}")
            item_lv.setTextAlignment(Qt.AlignCenter)

            item_r = QtWidgets.QTableWidgetItem(itm["rarity"])
            item_r.setForeground(QColor(itm["r_color"]))
            item_r.setTextAlignment(Qt.AlignCenter)

            item_ss = QtWidgets.QTableWidgetItem(itm["ss_text"])
            if "⚠️" in itm["ss_text"]:
                item_ss.setForeground(QColor("#ffa500"))
            elif "❌" in itm["ss_text"]:
                item_ss.setForeground(QColor("#ff5555"))
            else:
                item_ss.setForeground(QColor("#60a5fa"))

            item_conf = QtWidgets.QTableWidgetItem(itm["conf_text"])
            if "🟢" in itm["conf_text"]:
                item_conf.setForeground(QColor("#38ef7d"))
            elif "❌" in itm["conf_text"]:
                item_conf.setForeground(QColor("#ff6b6b"))
            else:
                item_conf.setForeground(QColor("#8892b0"))

            self.table_gears.setItem(row, 0, item_name)
            self.table_gears.setItem(row, 1, item_lv)
            self.table_gears.setItem(row, 2, item_r)
            self.table_gears.setItem(row, 3, item_ss)
            self.table_gears.setItem(row, 4, item_conf)

        self.lbl_gear_showing.setText(f"Showing: {len(filtered)} / {len(self.all_gear_items)} gears")

    def snip_selected_gear_action(self):
        sel = self.table_gears.selectedItems()
        if not sel:
            QtWidgets.QMessageBox.information(self, "Select Gear", "Please select a gear row to snip.")
            return
        row = sel[0].row()
        fn = self.table_gears.item(row, 0).data(Qt.UserRole)

        def on_done(res):
            w, h = res.get("width", 0), res.get("height", 0)
            self.ss_file_cache[fn] = (w, h)
            self.bot.vision.reload_reference_gear_library()
            self.refresh_gear_checklist_data()
            self.append_log(f"Snipped gear template {fn} ({w}x{h} px) into SS/", "success")

        self.snipper = QtScreenSnipper(
            mode="template",
            title=f"Snip Gear: {fn}",
            template_filename=fn,
            save_dir=self.ss_dir,
            on_complete=on_done
        )

    def reset_confirmed_gears_action(self):
        ret = QtWidgets.QMessageBox.question(self, "Reset Detections", "Are you sure you want to clear all confirmed gear detections?")
        if ret == QtWidgets.QMessageBox.Yes:
            self.confirmed_gears = {}
            self.save_confirmed_gears()
            self.refresh_gear_checklist_data()
            self.append_log("All confirmed gear detections have been cleared.", "info")

    def test_scan_and_confirm_action(self):
        self.append_log("Scanning visible inventory for gear confirmation...", "info")
        inv_roi = self.bot.vision.get_inventory_roi()
        items = self.bot.vision.scan_visible_inventory(inv_roi)
        self.record_detected_items(items)

        counts = {(b, r): 0 for b in ["65", "80_90"] for r in ["Common", "Uncommon", "Rare", "Legendary"]}
        for itm in items:
            b = itm.get("bracket", "")
            r = itm.get("rarity", "")
            if (b, r) in counts:
                counts[(b, r)] += 1
        self.bot._sync_and_publish_counts(counts)
        self.refresh_gear_checklist_data()
        self.append_log(f"Test Scan detected {len(items)} matching items and auto-confirmed them.", "success")
        QtWidgets.QMessageBox.information(self, "Scan Completed", f"Scan finished! Found {len(items)} matching items.\nChecklist and live buckets updated.")

    # ---------------------------------------------------------
    # MATERIALS CHECKLIST TABLE (42 ITEMS)
    # ---------------------------------------------------------
    def refresh_materials_checklist_data(self):
        curr_selected = self.lbl_selected_mat_fn.text()
        self.table_materials.blockSignals(True)
        self.table_materials.setRowCount(0)
        row = 0
        color_map = {
            "common": "#b0b8c4",
            "uncommon": "#32CD32",
            "rare": "#1E90FF",
            "legendary": "#FFA500",
            "immortal": "#ff79c6"
        }

        selected_row_idx = None
        for cat_key, items_list in self.materials_manifest.items():
            r_col = color_map.get(cat_key, "#ffffff")
            for itm in items_list:
                fn = itm.get("filename") or itm.get("file", "")
                name = itm.get("name", "")
                p = os.path.join(self.materials_dir, fn)
                exists = os.path.exists(p)

                self.table_materials.insertRow(row)
                item_fn = QtWidgets.QTableWidgetItem(fn)
                item_name = QtWidgets.QTableWidgetItem(name)
                item_name.setForeground(QColor("#ffffff"))

                item_r = QtWidgets.QTableWidgetItem(cat_key.capitalize())
                item_r.setForeground(QColor(r_col))
                item_r.setTextAlignment(Qt.AlignCenter)

                status_txt = "✅ Loaded" if exists else "❌ Missing"
                item_st = QtWidgets.QTableWidgetItem(status_txt)
                item_st.setForeground(QColor("#38ef7d" if exists else "#ff5555"))
                item_st.setTextAlignment(Qt.AlignCenter)

                self.table_materials.setItem(row, 0, item_fn)
                self.table_materials.setItem(row, 1, item_name)
                self.table_materials.setItem(row, 2, item_r)
                self.table_materials.setItem(row, 3, item_st)

                if curr_selected and curr_selected != "(select row)" and fn == curr_selected:
                    selected_row_idx = row

                row += 1

        if selected_row_idx is not None:
            self.table_materials.selectRow(selected_row_idx)

        self.table_materials.blockSignals(False)

        mat_stats = self.bot.vision.get_material_library_stats()
        total_mats = sum(len(items) for items in self.materials_manifest.values())
        self.lbl_mat_status.setText(f"Total: {total_mats} | Loaded: {mat_stats['total']} / {total_mats} templates")

    def on_mat_table_select(self):
        sel = self.table_materials.selectedItems()
        if not sel:
            self.lbl_selected_mat_fn.setText("(select row)")
            self.entry_mat_name.clear()
            return
        row = sel[0].row()
        fn = self.table_materials.item(row, 0).text()
        curr_name = self.table_materials.item(row, 1).text()
        self.lbl_selected_mat_fn.setText(fn)
        self.entry_mat_name.setText(curr_name)

    def apply_selected_material_name(self):
        fn = self.lbl_selected_mat_fn.text()
        if not fn or fn == "(select row)":
            return
        new_name = self.entry_mat_name.text().strip()
        updated = False
        for cat_key, items_list in self.materials_manifest.items():
            for itm in items_list:
                m_fn = itm.get("filename") or itm.get("file", "")
                if m_fn == fn:
                    itm["name"] = new_name
                    updated = True
                    break
        if updated:
            self.save_materials_manifest()
            self.refresh_materials_checklist_data()
            self.append_log(f"Renamed material {fn} to '{new_name}'", "success")

    def snip_selected_material_action(self):
        fn = self.lbl_selected_mat_fn.text()
        if not fn or fn == "(select row)":
            QtWidgets.QMessageBox.information(self, "Select Material", "Please select a material row to snip.")
            return

        def on_done(res):
            self.bot.vision.reload_material_library()
            self.refresh_materials_checklist_data()
            self.append_log(f"Snipped material template {fn} into SS_materials/", "success")

        self.snipper = QtScreenSnipper(
            mode="template",
            title=f"Snip Material: {fn}",
            template_filename=fn,
            save_dir=self.materials_dir,
            on_complete=on_done
        )

    def reload_materials_library_action(self):
        stats = self.bot.vision.reload_material_library()
        total_mats = sum(len(items) for items in self.materials_manifest.values())
        self.lbl_mat_status.setText(f"Total: {total_mats} | Loaded: {stats['total']} / {total_mats} templates")
        self.lbl_mat_status.setStyleSheet("color: #38ef7d; font-weight: bold;" if stats["loaded"] else "color: #ff5555; font-weight: bold;")
        self.refresh_materials_checklist_data()
        self.append_log(f"Reloaded Materials library: {stats['total']} templates active.", "info")

    # ---------------------------------------------------------
    # CORROSION MATERIALS & CUBE ACTIONS
    # ---------------------------------------------------------
    def load_corrosion_manifest(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.corrosion_manifest_path):
            try:
                with open(self.corrosion_manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[:15]
            except Exception as e:
                self.append_log(f"Error loading corrosion_manifest.json: {e}", "warning")
        default_items = []
        for i in range(1, 16):
            default_items.append({
                "id": i,
                "name": f"Corrosion Mat {i}",
                "filename": f"c_mat_{i}.png",
                "enabled": (i <= 5)
            })
        return default_items

    def save_corrosion_manifest(self):
        try:
            # Enforce max 15 items limit
            self.corrosion_manifest = self.corrosion_manifest[:15]
            with open(self.corrosion_manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.corrosion_manifest, f, indent=2)
            self.bot.vision.reload_corrosion_library()
        except Exception as e:
            self.append_log(f"Error saving corrosion_manifest.json: {e}", "warning")

    def refresh_corrosion_table_data(self):
        stats = self.bot.vision.get_corrosion_library_stats()
        total_slots = len(self.corrosion_manifest)
        loaded = stats.get("total", 0)
        enabled = stats.get("enabled", 0)
        self.lbl_corrosion_status.setText(f"Total Slots: {total_slots}/15 | Templates Loaded: {loaded} | Enabled: {enabled}")
        self.lbl_corrosion_status.setStyleSheet("color: #38ef7d; font-weight: bold;" if loaded > 0 else "color: #ffd166; font-weight: bold;")

        self.table_corrosion.blockSignals(True)
        self.table_corrosion.setRowCount(0)
        for idx, item in enumerate(self.corrosion_manifest):
            row = self.table_corrosion.rowCount()
            self.table_corrosion.insertRow(row)

            # Col 0: #
            it_id = QtWidgets.QTableWidgetItem(str(item.get("id", idx + 1)))
            it_id.setTextAlignment(Qt.AlignCenter)
            it_id.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table_corrosion.setItem(row, 0, it_id)

            # Col 1: ENABLE Checkbox
            cb_widget = QtWidgets.QWidget()
            cb_layout = QtWidgets.QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignCenter)
            chk = QtWidgets.QCheckBox()
            chk.setChecked(bool(item.get("enabled", True)))
            chk.toggled.connect(lambda chk_val, itm_id=item.get("id", idx + 1): self.toggle_corrosion_item_enabled(itm_id, chk_val))
            cb_layout.addWidget(chk)
            self.table_corrosion.setCellWidget(row, 1, cb_widget)

            # Col 2: MATERIAL NAME (Customizable)
            it_name = QtWidgets.QTableWidgetItem(str(item.get("name", "")))
            it_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table_corrosion.setItem(row, 2, it_name)

            # Col 3: FILENAME
            fn = item.get("filename", f"c_mat_{item.get('id', idx+1)}.png")
            it_fn = QtWidgets.QTableWidgetItem(fn)
            it_fn.setTextAlignment(Qt.AlignCenter)
            it_fn.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table_corrosion.setItem(row, 3, it_fn)

            # Col 4: STATUS (Loaded vs Missing)
            fp = os.path.join(self.corrosion_dir, fn)
            exists = os.path.isfile(fp)
            st_text = "✅ Loaded" if exists else "❌ Missing"
            it_st = QtWidgets.QTableWidgetItem(st_text)
            it_st.setTextAlignment(Qt.AlignCenter)
            it_st.setForeground(QtGui.QBrush(QtGui.QColor("#38ef7d" if exists else "#ff5555")))
            it_st.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table_corrosion.setItem(row, 4, it_st)

        self.table_corrosion.blockSignals(False)

    def on_corrosion_table_select(self):
        sel = self.table_corrosion.selectedItems()
        if not sel:
            self.lbl_selected_corrosion_fn.setText("(select slot)")
            self.entry_corrosion_name.clear()
            return
        row = sel[0].row()
        item_id_str = self.table_corrosion.item(row, 0).text()
        curr_name = self.table_corrosion.item(row, 2).text()
        fn = self.table_corrosion.item(row, 3).text()
        self.lbl_selected_corrosion_fn.setText(f"Slot #{item_id_str} ({fn})")
        self.entry_corrosion_name.setText(curr_name)

    def apply_selected_corrosion_name(self):
        sel_text = self.lbl_selected_corrosion_fn.text()
        if not sel_text or sel_text == "(select slot)":
            QtWidgets.QMessageBox.information(self, "Select Slot", "Please select a corrosion item slot to rename.")
            return
        new_name = self.entry_corrosion_name.text().strip()
        if not new_name:
            return

        sel = self.table_corrosion.selectedItems()
        if not sel:
            return
        row = sel[0].row()
        try:
            slot_id = int(self.table_corrosion.item(row, 0).text())
        except ValueError:
            slot_id = row + 1

        for itm in self.corrosion_manifest:
            if itm.get("id") == slot_id:
                itm["name"] = new_name
                break
        self.save_corrosion_manifest()
        self.refresh_corrosion_table_data()
        self.append_log(f"Renamed corrosion slot #{slot_id} to '{new_name}'", "success")

    def snip_selected_corrosion_action(self):
        sel = self.table_corrosion.selectedItems()
        if not sel:
            QtWidgets.QMessageBox.information(self, "Select Corrosion Material", "Please select a corrosion slot to snip.")
            return
        row = sel[0].row()
        fn = self.table_corrosion.item(row, 3).text()
        name = self.table_corrosion.item(row, 2).text()

        def on_done(res):
            self.bot.vision.reload_corrosion_library()
            self.refresh_corrosion_table_data()
            self.append_log(f"Snipped corrosion template {fn} into SS_corrosion/", "success")

        self.snipper = QtScreenSnipper(
            mode="template",
            title=f"Snip Corrosion Material: {name} ({fn})",
            template_filename=fn,
            save_dir=self.corrosion_dir,
            on_complete=on_done
        )

    def add_corrosion_slot_action(self):
        if len(self.corrosion_manifest) >= 15:
            QtWidgets.QMessageBox.warning(
                self,
                "Maximum Limit Reached",
                "Maximum 15 corrosion items allowed. You cannot add more than 15 slots."
            )
            return

        existing_ids = {item.get("id", 0) for item in self.corrosion_manifest}
        new_id = 1
        while new_id in existing_ids:
            new_id += 1

        new_slot = {
            "id": new_id,
            "name": f"Corrosion Mat {new_id}",
            "filename": f"c_mat_{new_id}.png",
            "enabled": True
        }
        self.corrosion_manifest.append(new_slot)
        self.corrosion_manifest.sort(key=lambda x: x.get("id", 0))
        self.save_corrosion_manifest()
        self.refresh_corrosion_table_data()
        self.append_log(f"Added new customizable corrosion slot #{new_id} ({len(self.corrosion_manifest)}/15 slots).", "info")

    def remove_corrosion_slot_action(self):
        sel = self.table_corrosion.selectedItems()
        if not sel:
            QtWidgets.QMessageBox.information(self, "Select Slot", "Please select a corrosion slot to remove.")
            return
        row = sel[0].row()
        try:
            slot_id = int(self.table_corrosion.item(row, 0).text())
        except ValueError:
            slot_id = row + 1

        self.corrosion_manifest = [itm for itm in self.corrosion_manifest if itm.get("id") != slot_id]
        self.save_corrosion_manifest()
        self.refresh_corrosion_table_data()
        self.append_log(f"Removed corrosion slot #{slot_id}. Remaining: {len(self.corrosion_manifest)}/15 slots.", "info")

    def toggle_corrosion_item_enabled(self, item_id: int, checked: bool):
        for itm in self.corrosion_manifest:
            if itm.get("id") == item_id:
                itm["enabled"] = checked
                break
        self.save_corrosion_manifest()
        stats = self.bot.vision.get_corrosion_library_stats()
        self.lbl_corrosion_status.setText(f"Total Slots: {len(self.corrosion_manifest)}/15 | Templates Loaded: {stats.get('total', 0)} | Enabled: {stats.get('enabled', 0)}")

    def toggle_auto_corrosion_action(self, checked: bool):
        self.config_data["auto_corrosion_enabled"] = checked
        self.save_config(show_dialog=False)
        self.append_log(f"Auto-Corrosion Flow set to: {'ENABLED' if checked else 'DISABLED'}", "info")

    def run_test_corrosion_flow_action(self):
        def _worker():
            self.append_log("Starting test execution of Cube Corrosion Flow...", "info")
            loaded = self.bot.test_corrosion_flow()
            self.append_log(f"Test Corrosion Flow complete: {loaded} material(s) included.", "success")
        threading.Thread(target=_worker, daemon=True).start()

    def reload_corrosion_library_action(self):
        stats = self.bot.vision.reload_corrosion_library()
        self.refresh_corrosion_table_data()
        self.append_log(f"Reloaded Corrosion library: {stats.get('total', 0)} template(s) loaded, {stats.get('enabled', 0)} enabled.", "info")

    # ---------------------------------------------------------
    # LOW LEVEL (LV. 50) AUTOMATION ACTIONS
    # ---------------------------------------------------------
    def toggle_low_level_stashing_action(self, checked: bool):
        self.config_data["low_level_stashing_enabled"] = checked
        if hasattr(self, "cb_low_level_stashing") and self.cb_low_level_stashing.isChecked() != checked:
            self.cb_low_level_stashing.blockSignals(True)
            self.cb_low_level_stashing.setChecked(checked)
            self.cb_low_level_stashing.blockSignals(False)
        if hasattr(self, "cb_dash_low_level") and self.cb_dash_low_level.isChecked() != checked:
            self.cb_dash_low_level.blockSignals(True)
            self.cb_dash_low_level.setChecked(checked)
            self.cb_dash_low_level.blockSignals(False)
        self.save_config(show_dialog=False)
        self.append_log(f"Low-Level Stashing (Lv. 50) set to: {'ENABLED' if checked else 'DISABLED'}", "info")

    def run_test_low_level_stashing_action(self):
        def _worker():
            self.append_log("Starting test execution of Low-Level Stashing Transfer...", "info")
            res = self.bot.test_low_level_stash_transfer()
            self.append_log(f"Test Low-Level Stashing complete: {res.get('low_tier', 0)} low-tier (Stash 1), {res.get('high_tier', 0)} high-tier (Stash 2).", "success")
        threading.Thread(target=_worker, daemon=True).start()

    def run_test_stash_lvl50_synth_action(self):
        def _worker():
            self.append_log("Starting test execution of Stash Lv. 50 Cube Synthesis...", "info")
            ok = self.bot.test_stash_lvl50_synthesis()
            if ok:
                self.append_log("Test Stash Lv. 50 Synthesis: Succeeded (items loaded and synth triggered).", "success")
            else:
                self.append_log("Test Stash Lv. 50 Synthesis: No rarity had >= 9 items in Stash 1 or aborted.", "info")
        threading.Thread(target=_worker, daemon=True).start()

    def jump_to_gears_lvl50_action(self):
        """Switches to the Gears matrix tab and filters for Lv. 50 items."""
        self.tabs.setCurrentWidget(self.tab_gears)
        self.combo_gear_level.setCurrentText("Lv. 50")
        self.apply_gear_filter()

    # ---------------------------------------------------------
    # TAB 7: TELEGRAM REMOTE WATCHDOG & MOBILE MONITOR
    # ---------------------------------------------------------
    def _build_telegram_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_telegram)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # 1. Status Banner Card
        top_card = QtWidgets.QFrame(self.tab_telegram)
        top_card.setProperty("card", True)
        tc_layout = QtWidgets.QHBoxLayout(top_card)
        tc_layout.setContentsMargins(12, 8, 12, 8)
        tc_layout.setSpacing(10)

        self.lbl_tg_status = QtWidgets.QLabel("Status: Checking Telegram...", top_card)
        self.lbl_tg_status.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 10.5pt;")
        tc_layout.addWidget(self.lbl_tg_status)
        tc_layout.addStretch()

        self.cb_tg_enabled = QtWidgets.QCheckBox("Enable Telegram Watchdog", top_card)
        self.cb_tg_enabled.setChecked(bool(self.config_data.get("telegram", {}).get("enabled", False)))
        self.cb_tg_enabled.setStyleSheet("color: #ffd166; font-weight: bold; font-size: 10pt;")
        self.cb_tg_enabled.toggled.connect(self.toggle_telegram_service_action)
        tc_layout.addWidget(self.cb_tg_enabled)

        layout.addWidget(top_card)

        # 2. Main Content Split / Grid: Credentials + Settings
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(8)

        # Left Column: Bot Credentials & Test Actions
        creds_card = QtWidgets.QFrame(self.tab_telegram)
        creds_card.setProperty("card", True)
        cc_layout = QtWidgets.QVBoxLayout(creds_card)
        cc_layout.setContentsMargins(12, 8, 12, 8)
        cc_layout.setSpacing(8)

        lbl_c_head = QtWidgets.QLabel("🔑 BOT CREDENTIALS & CONNECTION", creds_card)
        lbl_c_head.setStyleSheet("color: #ffd166; font-weight: bold; font-size: 10pt;")
        cc_layout.addWidget(lbl_c_head)

        # Bot Token Field
        cc_layout.addWidget(QtWidgets.QLabel("Bot Token (from @BotFather):", creds_card))
        token_row = QtWidgets.QHBoxLayout()
        token_row.setSpacing(4)
        self.entry_tg_token = QtWidgets.QLineEdit(creds_card)
        self.entry_tg_token.setEchoMode(QtWidgets.QLineEdit.Password)
        self.entry_tg_token.setText(self.config_data.get("telegram", {}).get("bot_token", ""))
        self.entry_tg_token.setPlaceholderText("e.g. 7123456789:AAHxyz...")
        token_row.addWidget(self.entry_tg_token, stretch=1)

        self.btn_toggle_token = QtWidgets.QPushButton("👁 Show", creds_card)
        self.btn_toggle_token.setFixedWidth(65)
        self.btn_toggle_token.clicked.connect(self.toggle_token_visibility_action)
        token_row.addWidget(self.btn_toggle_token)
        cc_layout.addLayout(token_row)

        # Chat ID Field
        cc_layout.addWidget(QtWidgets.QLabel("Your Chat ID (from @userinfobot):", creds_card))
        self.entry_tg_chat_id = QtWidgets.QLineEdit(creds_card)
        self.entry_tg_chat_id.setText(str(self.config_data.get("telegram", {}).get("chat_id", "")))
        self.entry_tg_chat_id.setPlaceholderText("e.g. 123456789")
        cc_layout.addWidget(self.entry_tg_chat_id)

        # Action Buttons
        btn_row_creds = QtWidgets.QHBoxLayout()
        btn_row_creds.setSpacing(6)

        btn_save_creds = QtWidgets.QPushButton("💾 Save", creds_card)
        btn_save_creds.setProperty("role", "success")
        btn_save_creds.clicked.connect(self.save_telegram_credentials_action)
        btn_row_creds.addWidget(btn_save_creds)

        btn_test_ping = QtWidgets.QPushButton("⚡ Ping Phone", creds_card)
        btn_test_ping.setProperty("role", "primary")
        btn_test_ping.clicked.connect(self.test_telegram_connection_action)
        btn_row_creds.addWidget(btn_test_ping)

        btn_test_screen = QtWidgets.QPushButton("📸 Send Screenshot", creds_card)
        btn_test_screen.setProperty("role", "teal")
        btn_test_screen.clicked.connect(self.send_test_telegram_screenshot_action)
        btn_row_creds.addWidget(btn_test_screen)

        cc_layout.addLayout(btn_row_creds)

        # Quick Setup Instructions Subcard
        help_box = QtWidgets.QFrame(creds_card)
        help_box.setStyleSheet("background-color: #1a1e2a; border-radius: 6px; padding: 6px;")
        hb_layout = QtWidgets.QVBoxLayout(help_box)
        hb_layout.setContentsMargins(6, 6, 6, 6)
        lbl_guide = QtWidgets.QLabel(
            "<b>1-Minute Quick Setup:</b><br>"
            "1. Open Telegram ➔ Search <code>@BotFather</code> ➔ send <code>/newbot</code> ➔ Copy HTTP API Token.<br>"
            "2. Search <code>@userinfobot</code> in Telegram ➔ send <code>/start</code> ➔ Copy your numeric Id.<br>"
            "3. Paste Token & Chat ID above ➔ Tap <b>Save</b> then <b>Ping Phone</b>!",
            help_box
        )
        lbl_guide.setTextFormat(Qt.RichText)
        lbl_guide.setStyleSheet("color: #8892b0; font-size: 8.5pt;")
        hb_layout.addWidget(lbl_guide)
        cc_layout.addWidget(help_box)
        cc_layout.addStretch()

        content_layout.addWidget(creds_card, stretch=1)

        # Right Column: Watchdog Settings & Commands
        right_col = QtWidgets.QVBoxLayout()
        right_col.setSpacing(8)

        settings_card = QtWidgets.QFrame(self.tab_telegram)
        settings_card.setProperty("card", True)
        sc_layout = QtWidgets.QVBoxLayout(settings_card)
        sc_layout.setContentsMargins(12, 8, 12, 8)
        sc_layout.setSpacing(8)

        lbl_s_head = QtWidgets.QLabel("⚙️ WATCHDOG ALERTS & NOTIFICATIONS", settings_card)
        lbl_s_head.setStyleSheet("color: #ffd166; font-weight: bold; font-size: 10pt;")
        sc_layout.addWidget(lbl_s_head)

        # Stuck Timeout
        timeout_row = QtWidgets.QHBoxLayout()
        timeout_row.addWidget(QtWidgets.QLabel("Stuck Alert Timeout:", settings_card))
        self.spin_tg_timeout = QtWidgets.QSpinBox(settings_card)
        self.spin_tg_timeout.setRange(30, 900)
        self.spin_tg_timeout.setSingleStep(15)
        self.spin_tg_timeout.setValue(int(self.config_data.get("telegram", {}).get("stuck_timeout_seconds", 180)))
        self.spin_tg_timeout.setSuffix(" sec")
        timeout_row.addWidget(self.spin_tg_timeout)
        timeout_row.addStretch()
        sc_layout.addLayout(timeout_row)

        self.cb_notify_stuck = QtWidgets.QCheckBox("⚠️ Send Emergency Alert if bot gets stuck", settings_card)
        self.cb_notify_stuck.setChecked(bool(self.config_data.get("telegram", {}).get("notify_on_stuck", True)))
        sc_layout.addWidget(self.cb_notify_stuck)

        self.cb_send_stuck_screen = QtWidgets.QCheckBox("📸 Attach Live Screenshot on Stuck Alert", settings_card)
        self.cb_send_stuck_screen.setChecked(bool(self.config_data.get("telegram", {}).get("send_screenshot_on_stuck", True)))
        sc_layout.addWidget(self.cb_send_stuck_screen)

        self.cb_notify_synth = QtWidgets.QCheckBox("⚗ Notify on Cube Synthesis Completion", settings_card)
        self.cb_notify_synth.setChecked(bool(self.config_data.get("telegram", {}).get("notify_on_synth", True)))
        sc_layout.addWidget(self.cb_notify_synth)

        hb_row = QtWidgets.QHBoxLayout()
        hb_row.addWidget(QtWidgets.QLabel("Periodic Health Ping:", settings_card))
        self.combo_tg_heartbeat = QtWidgets.QComboBox(settings_card)
        self.combo_tg_heartbeat.addItems(["Disabled", "Every 30 mins", "Every 60 mins", "Every 120 mins"])
        curr_hb = int(self.config_data.get("telegram", {}).get("periodic_heartbeat_minutes", 0))
        hb_map = {0: "Disabled", 30: "Every 30 mins", 60: "Every 60 mins", 120: "Every 120 mins"}
        self.combo_tg_heartbeat.setCurrentText(hb_map.get(curr_hb, "Disabled"))
        hb_row.addWidget(self.combo_tg_heartbeat)
        hb_row.addStretch()
        sc_layout.addLayout(hb_row)

        btn_save_settings = QtWidgets.QPushButton("💾 Save Watchdog Settings", settings_card)
        btn_save_settings.setProperty("role", "success")
        btn_save_settings.clicked.connect(self.save_telegram_settings_action)
        sc_layout.addWidget(btn_save_settings)

        right_col.addWidget(settings_card)

        # Remote Commands Card
        cmd_card = QtWidgets.QFrame(self.tab_telegram)
        cmd_card.setProperty("card", True)
        cmd_layout = QtWidgets.QVBoxLayout(cmd_card)
        cmd_layout.setContentsMargins(12, 8, 12, 8)
        cmd_layout.setSpacing(4)

        lbl_cmd_title = QtWidgets.QLabel("📱 PHONE COMMANDS & INLINE BUTTONS", cmd_card)
        lbl_cmd_title.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 9.5pt;")
        cmd_layout.addWidget(lbl_cmd_title)

        lbl_cmd_list = QtWidgets.QLabel(
            "Send commands directly or tap buttons on Telegram (auto-cleaned in-place):<br>"
            "• <code>/stats</code> — Live session uptime, loops & cube syntheses count<br>"
            "• <code>/timer</code> — View loop countdown, toggle auto-loop, or run now<br>"
            "• <code>/chest</code> — Chest Cam visual snapshot & floor state check<br>"
            "• <code>/stashcam</code> — Stash Grid photo snapshot (ROI view)<br>"
            "• <code>/stash</code> — Inspect Stash 1 (L50), Stash 2 & Materials<br>"
            "• <code>/inv</code> — Full top-to-bottom scan & breakdown of Lv. 65 & 80 gear<br>"
            "• <code>/screenshot</code> — Snaps instant live screenshot of the game<br>"
            "• <code>/unstick</code> — Emergency unstick: presses ESC and resets focus<br>"
            "• <code>/autofill</code> — Trigger native Auto-Fill Synthesis (Lv. 80~90)<br>"
            "• <code>/pause</code> / <code>/resume</code> — Remotely pause or resume bot cycle<br>"
            "• <code>/lvl50</code> — Toggle Low-Level (Lv. 50) stashing on/off",
            cmd_card
        )
        lbl_cmd_list.setTextFormat(Qt.RichText)
        lbl_cmd_list.setStyleSheet("color: #d0d5e2; font-size: 8.5pt;")
        cmd_layout.addWidget(lbl_cmd_list)

        right_col.addWidget(cmd_card)
        content_layout.addLayout(right_col, stretch=1)

        layout.addLayout(content_layout, stretch=1)
        self.refresh_telegram_tab_status()

    def refresh_telegram_tab_status(self):
        tg_cfg = self.config_data.get("telegram", {})
        enabled = bool(tg_cfg.get("enabled", False))
        token = tg_cfg.get("bot_token", "").strip()
        cid = str(tg_cfg.get("chat_id", "")).strip()

        if not enabled:
            self.lbl_tg_status.setText("Status: ⚪ Telegram Watchdog Disabled")
            self.lbl_tg_status.setStyleSheet("color: #8892b0; font-weight: bold;")
        elif not token or not cid:
            self.lbl_tg_status.setText("Status: 🔴 Incomplete (Token or Chat ID Missing)")
            self.lbl_tg_status.setStyleSheet("color: #ff5555; font-weight: bold;")
        else:
            self.lbl_tg_status.setText("Status: 🟢 Active (Listening for Commands & Monitoring Loop)")
            self.lbl_tg_status.setStyleSheet("color: #38ef7d; font-weight: bold;")

    def toggle_token_visibility_action(self):
        if self.entry_tg_token.echoMode() == QtWidgets.QLineEdit.Password:
            self.entry_tg_token.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.btn_toggle_token.setText("🙈 Hide")
        else:
            self.entry_tg_token.setEchoMode(QtWidgets.QLineEdit.Password)
            self.btn_toggle_token.setText("👁 Show")

    def save_telegram_credentials_action(self):
        token = self.entry_tg_token.text().strip()
        chat_id = self.entry_tg_chat_id.text().strip()

        if "telegram" not in self.config_data:
            self.config_data["telegram"] = {}
        self.config_data["telegram"]["bot_token"] = token
        self.config_data["telegram"]["chat_id"] = chat_id

        self.save_config(show_dialog=False)
        self.bot.reload_config()
        self.refresh_telegram_tab_status()
        self.append_log("Telegram credentials saved to config.json.", "success")
        QtWidgets.QMessageBox.information(
            self,
            "Credentials Saved",
            "Telegram Bot Token & Chat ID saved successfully!\nClick 'Ping Phone' to test."
        )

    def save_telegram_settings_action(self):
        if "telegram" not in self.config_data:
            self.config_data["telegram"] = {}

        self.config_data["telegram"]["stuck_timeout_seconds"] = self.spin_tg_timeout.value()
        self.config_data["telegram"]["notify_on_stuck"] = self.cb_notify_stuck.isChecked()
        self.config_data["telegram"]["send_screenshot_on_stuck"] = self.cb_send_stuck_screen.isChecked()
        self.config_data["telegram"]["notify_on_synth"] = self.cb_notify_synth.isChecked()

        hb_text = self.combo_tg_heartbeat.currentText()
        hb_val = 0
        if "30" in hb_text:
            hb_val = 30
        elif "60" in hb_text:
            hb_val = 60
        elif "120" in hb_text:
            hb_val = 120
        self.config_data["telegram"]["periodic_heartbeat_minutes"] = hb_val

        self.save_config(show_dialog=False)
        self.bot.reload_config()
        self.append_log("Telegram Watchdog alert settings saved.", "success")
        QtWidgets.QMessageBox.information(self, "Settings Saved", "Watchdog alert settings saved successfully!")

    def test_telegram_connection_action(self):
        token = self.entry_tg_token.text().strip()
        chat_id = self.entry_tg_chat_id.text().strip()

        if not token or not chat_id:
            QtWidgets.QMessageBox.warning(self, "Missing Credentials", "Please enter both Bot Token and Chat ID first.")
            return

        def _worker():
            self.append_log("Testing Telegram bot connection...", "info")
            from core.telegram_watchdog import TelegramClient
            client = TelegramClient(token, chat_id)
            ok, res = client.get_me()
            if not ok:
                err_msg = res.get("error", "Unknown error") if isinstance(res, dict) else str(res)
                self.append_log(f"Telegram connection failed: {err_msg}", "error")
                return

            bot_name = res.get("first_name", "Bot")
            username = res.get("username", "")
            self.append_log(f"Telegram verified: Connected to @{username} ({bot_name})", "success")

            # Send test message to chat_id
            test_msg = (
                f"👋 <b>TaskBar Hero Bot Connected!</b>\n\n"
                f"Connection test was successful from your PC/laptop.\n"
                f"• <b>Bot:</b> @{username}\n"
                f"• <b>Time:</b> {time.strftime('%H:%M:%S')}\n\n"
                f"Tap below to test quick commands:"
            )
            markup = self.bot.telegram.get_main_inline_keyboard()
            sent_ok, sent_err = client.send_message(test_msg, reply_markup=markup)
            if sent_ok:
                self.append_log(f"Test ping sent to your phone (Chat ID {chat_id})!", "success")
            else:
                self.append_log(f"Failed to deliver message to Chat ID {chat_id}: {sent_err}", "warning")

        threading.Thread(target=_worker, daemon=True).start()

    def send_test_telegram_screenshot_action(self):
        token = self.entry_tg_token.text().strip()
        chat_id = self.entry_tg_chat_id.text().strip()

        if not token or not chat_id:
            QtWidgets.QMessageBox.warning(self, "Missing Credentials", "Please enter both Bot Token and Chat ID first.")
            return

        def _worker():
            self.append_log("Capturing live game screen for Telegram test...", "info")
            from core.telegram_watchdog import TelegramClient
            client = TelegramClient(token, chat_id)
            try:
                img = self.bot.telegram._capture_screen_with_banner("Manual Test Screenshot")
                markup = self.bot.telegram.get_main_inline_keyboard()
                ok, err = client.send_photo(
                    img,
                    caption=f"📸 <b>Manual Test Screenshot</b>\nCaptured at: {time.strftime('%H:%M:%S')}",
                    reply_markup=markup
                )
                if ok:
                    self.append_log("Test screenshot delivered to your phone successfully!", "success")
                else:
                    self.append_log(f"Failed to send screenshot: {err}", "warning")
            except Exception as e:
                self.append_log(f"Error capturing test screenshot: {e}", "error")

        threading.Thread(target=_worker, daemon=True).start()

    def toggle_telegram_service_action(self, checked: bool):
        if "telegram" not in self.config_data:
            self.config_data["telegram"] = {}
        self.config_data["telegram"]["enabled"] = checked
        if hasattr(self, "cb_dash_telegram") and self.cb_dash_telegram.isChecked() != checked:
            self.cb_dash_telegram.blockSignals(True)
            self.cb_dash_telegram.setChecked(checked)
            self.cb_dash_telegram.blockSignals(False)
        if hasattr(self, "cb_tg_enabled") and self.cb_tg_enabled.isChecked() != checked:
            self.cb_tg_enabled.blockSignals(True)
            self.cb_tg_enabled.setChecked(checked)
            self.cb_tg_enabled.blockSignals(False)
        self.save_config(show_dialog=False)
        self.bot.reload_config()
        self.refresh_telegram_tab_status()
        self.append_log(f"Telegram Watchdog service: {'ENABLED' if checked else 'DISABLED'}", "info")

    def closeEvent(self, event: QtGui.QCloseEvent):
        # Gracefully stop bot on close
        self.bot.trigger_emergency_stop()
        if hasattr(self.bot, "telegram"):
            self.bot.telegram.stop()
        if self.debugger_window:
            self.debugger_window.close()
        super().closeEvent(event)

    def mainloop(self):
        """Compatibility method for standard execution."""
        import sys
        self.show()
        if hasattr(self, "_qt_app") and self._qt_app is not None:
            self._qt_app.exec()
