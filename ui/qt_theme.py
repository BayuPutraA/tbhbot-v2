"""
qt_theme.py - Dark-mode cyber theme and stylesheet for Task Bar Hero Qt 6 interface.
Provides modern, hardware-accelerated styling with high-contrast readouts and minimal GPU/CPU overhead.
"""

DARK_THEME_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #10121c;
    color: #e2e8f0;
    font-family: "Segoe UI", sans-serif;
    font-size: 10pt;
}

/* Tab Widget Styling */
QTabWidget::pane {
    border: 1px solid #202538;
    background-color: #10121c;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: #181c2e;
    color: #8892b0;
    padding: 7px 14px;
    font-weight: bold;
    font-size: 9.5pt;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
    border: 1px solid #202538;
}
QTabBar::tab:selected {
    background: #202538;
    color: #00e5ff;
    border: 1px solid #202538;
    border-bottom: 2px solid #00e5ff;
}
QTabBar::tab:hover:!selected {
    color: #ffffff;
    background: #262c45;
    border-color: #384260;
}

/* Scroll Area */
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}
QWidget#calibrator_container {
    background-color: transparent;
}

/* Card Frames */
QFrame[card="true"] {
    background-color: #181c2e;
    border-radius: 6px;
    border: 1px solid #202538;
}
QFrame[inner_card="true"] {
    background-color: #131625;
    border-radius: 4px;
    border: 1px solid #1e2438;
}

/* Standard Buttons */
QPushButton {
    background-color: #23283b;
    color: #e2e8f0;
    border-radius: 4px;
    font-weight: bold;
    font-size: 9pt;
    padding: 4px 10px;
    border: 1px solid #384260;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #323b56;
    border: 1px solid #00e5ff;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #1a1e2d;
    border: 1px solid #00b4d8;
}
QPushButton:disabled {
    background-color: #161924;
    color: #555c70;
    border: 1px solid #252a3a;
}

/* Accent Buttons */
QPushButton[role="primary"] {
    background-color: #1d4ed8;
    color: #ffffff;
    border: 1px solid #3b82f6;
}
QPushButton[role="primary"]:hover {
    background-color: #2563eb;
    border: 1px solid #93c5fd;
    color: #ffffff;
}
QPushButton[role="primary"]:pressed {
    background-color: #1e40af;
    border: 1px solid #1d4ed8;
}

QPushButton[role="success"] {
    background-color: #15803d;
    color: #ffffff;
    border: 1px solid #22c55e;
}
QPushButton[role="success"]:hover {
    background-color: #16a34a;
    border: 1px solid #86efac;
    color: #ffffff;
}
QPushButton[role="success"]:pressed {
    background-color: #14532d;
    border: 1px solid #15803d;
}

QPushButton[role="danger"] {
    background-color: #991b1b;
    color: #ffffff;
    border: 1px solid #ef4444;
}
QPushButton[role="danger"]:hover {
    background-color: #dc2626;
    border: 1px solid #fca5a5;
    color: #ffffff;
}
QPushButton[role="danger"]:pressed {
    background-color: #7f1d1d;
    border: 1px solid #991b1b;
}

QPushButton[role="warning"] {
    background-color: #b45309;
    color: #ffffff;
    border: 1px solid #f59e0b;
}
QPushButton[role="warning"]:hover {
    background-color: #d97706;
    border: 1px solid #fde68a;
    color: #ffffff;
}
QPushButton[role="warning"]:pressed {
    background-color: #78350f;
    border: 1px solid #b45309;
}

QPushButton[role="indigo"] {
    background-color: #4338ca;
    color: #ffffff;
    border: 1px solid #6366f1;
}
QPushButton[role="indigo"]:hover {
    background-color: #4f46e5;
    border: 1px solid #a5b4fc;
    color: #ffffff;
}
QPushButton[role="indigo"]:pressed {
    background-color: #3730a3;
    border: 1px solid #4338ca;
}

QPushButton[role="teal"] {
    background-color: #0f766e;
    color: #ffffff;
    border: 1px solid #14b8a6;
}
QPushButton[role="teal"]:hover {
    background-color: #0d9488;
    border: 1px solid #5eead4;
    color: #ffffff;
}
QPushButton[role="teal"]:pressed {
    background-color: #134e4a;
    border: 1px solid #0f766e;
}

QPushButton[role="purple"] {
    background-color: #6d28d9;
    color: #ffffff;
    border: 1px solid #8b5cf6;
}
QPushButton[role="purple"]:hover {
    background-color: #7c3aed;
    border: 1px solid #c4b5fd;
    color: #ffffff;
}
QPushButton[role="purple"]:pressed {
    background-color: #4c1d95;
    border: 1px solid #6d28d9;
}

/* Line Edits (Inputs) */
QLineEdit {
    background-color: #1a1d2e;
    color: #ffffff;
    border: 1px solid #303548;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 9.5pt;
    selection-background-color: #00e5ff;
    selection-color: #000000;
}
QLineEdit:focus {
    border: 1px solid #00e5ff;
}

/* Dropdowns / ComboBoxes */
QComboBox {
    background-color: #1a1d2e;
    color: #e2e8f0;
    border: 1px solid #303548;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 9.5pt;
    min-height: 20px;
}
QComboBox:hover {
    border: 1px solid #404660;
}
QComboBox:focus {
    border: 1px solid #00e5ff;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #303548;
}
QComboBox QAbstractItemView {
    background-color: #181c2e;
    color: #e2e8f0;
    selection-background-color: #1f538d;
    selection-color: #ffffff;
    border: 1px solid #303548;
    padding: 2px;
}

/* CheckBoxes */
QCheckBox {
    color: #d0d5e2;
    font-size: 9.5pt;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 3px;
    border: 1px solid #404660;
    background-color: #1a1d2e;
}
QCheckBox::indicator:hover {
    border: 1px solid #00e5ff;
}
QCheckBox::indicator:checked {
    background-color: #1f538d;
    border: 1px solid #00e5ff;
    image: none;
}

/* Tables & TreeViews */
QTableWidget, QTreeView {
    background-color: #141724;
    color: #e0e6ed;
    gridline-color: #1e2438;
    border: 1px solid #1e2438;
    border-radius: 4px;
    selection-background-color: #1f538d;
    selection-color: #ffffff;
    font-size: 9.5pt;
    outline: none;
}
QTableWidget::item, QTreeView::item {
    padding: 4px 6px;
}
QTableWidget::item:selected, QTreeView::item:selected {
    background-color: #1f538d;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #1e2438;
    color: #00e5ff;
    font-weight: bold;
    font-size: 9pt;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid #28304c;
    border-bottom: 1px solid #28304c;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #10121c;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #303548;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #00e5ff;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #10121c;
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #303548;
    min-width: 24px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #00e5ff;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Text Edit (Logs) */
QTextEdit, QPlainTextEdit {
    background-color: #0b0c13;
    color: #d0d5e2;
    border: 1px solid #1e2438;
    border-radius: 4px;
    font-family: "Consolas", monospace;
    font-size: 9pt;
    padding: 4px;
}

/* Progress Bar */
QProgressBar {
    background-color: #1a1d2e;
    border: 1px solid #303548;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    font-size: 9pt;
    height: 16px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f538d, stop:1 #00e5ff);
    border-radius: 3px;
}

/* Tooltip */
QToolTip {
    background-color: #1e2438;
    color: #ffffff;
    border: 1px solid #00e5ff;
    border-radius: 4px;
    padding: 4px;
    font-size: 9pt;
}
"""
