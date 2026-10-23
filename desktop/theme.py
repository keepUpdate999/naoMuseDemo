"""sRGB equivalents of GuDuu OS client/styles/tokens.css (CosMac 2A).

Platform source is read-only reference; no runtime dependency on another repo.
"""
from pathlib import Path
BG = '#f9fafb'
INK = '#181b1e'
MUTED = '#5a5e63'
BORDER = '#dfe1e5'
ACCENT = '#182541'
SOFT = '#e4efff'

STYLES = '''
QWidget { color:#181b1e; font-family:"Microsoft YaHei UI"; font-size:12px; }
QWidget#assistant { background:#f9fafb; }
QLabel { background:transparent; }
QLabel#brand {font-size:19px;font-weight:600;color:#182541;}
QLabel#subtitle {font-size:11px;color:#777e88;}
QLabel#notice {color:#6a7280;font-size:11px;padding:0 2px;}
QLabel#status {background:#edf2fb;color:#344c75;border-radius:8px;padding:7px 10px;font-size:11px;}
QLabel#sectionTitle {font-size:12px;font-weight:600;color:#29354a;}
QLabel#liveBadge {color:#526b9a;font-size:10px;}
QLabel#summary {background:#edf2fb;border:1px solid #dbe4f4;border-radius:10px;padding:10px;color:#344c75;}
QWidget#taskCard, QWidget#recordCard {background:#fff;border:1px solid #dfe1e5;border-radius:12px;}
QPushButton {border:1px solid #dfe1e5;border-radius:8px;padding:8px 10px;background:#fff;color:#3b4658;}
QPushButton:hover {background:#f3f5f9;border-color:#b9c7db;}
QPushButton:pressed {background:#e4efff;}
QPushButton:disabled {color:#a1a8b4;background:#f7f8fa;border-color:#edf0f4;}
QPushButton#primary {background:#182541;color:#fff;border:1px solid #182541;font-weight:600;}
QPushButton#primary:hover {background:#243757;}
QPushButton#primary:pressed {background:#101a2d;}
QPushButton#primary:disabled {background:#a5afc0;border-color:#a5afc0;}
QPushButton#quiet {padding:4px 6px;font-size:10px;border:none;background:transparent;color:#62718a;}
QPushButton#quiet:hover {background:#edf2fb;}
QPlainTextEdit {background:#f9fafc;border:1px solid #e5e9f0;border-radius:8px;padding:8px;selection-background-color:#d6e4fc;}
QPlainTextEdit:focus {border:1px solid #8fa7cd;background:#fff;}
QPlainTextEdit:disabled {color:#858e9e;}
QComboBox {background:#fff;border:1px solid #dfe1e5;border-radius:8px;padding:7px 9px;min-height:16px;}
QComboBox:hover {border-color:#a5b5cd;}
QComboBox::drop-down {border:none;width:23px;}
QComboBox::down-arrow {image:url("__CHEVRON__");width:12px;height:8px;}
QComboBox QAbstractItemView {background:#fff;border:1px solid #dfe1e5;selection-background-color:#e4efff;selection-color:#182541;padding:4px;}
QListWidget {background:transparent;border:none;outline:none;padding:0;}
QScrollBar:vertical {background:transparent;width:6px;margin:2px;}
QScrollBar::handle:vertical {background:#d5dce7;border-radius:2px;min-height:24px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}
QMenu {background:#fff;border:1px solid #dfe1e5;padding:5px;}
QMenu::item {padding:8px 16px;}
QMenu::item:selected {background:#e4efff;border-radius:5px;}
'''.replace('__CHEVRON__',Path(__file__).with_name('chevron.svg').as_posix())
