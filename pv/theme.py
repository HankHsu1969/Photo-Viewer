"""Dark theme."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

ACCENT = '#3794ff'
DEFAULT_FONT_PT = 9.5
MIN_FONT_PT, MAX_FONT_PT = 8.0, 18.0


class _Style(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_Slider_AbsoluteSetButtons:
            return int(Qt.MouseButton.LeftButton.value)
        return super().styleHint(hint, option, widget, returnData)

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PixelMetric.PM_ToolBarExtensionExtent:
            return 24     # room for a visible "more tools" chevron when a toolbar overflows
        return super().pixelMetric(metric, option, widget)


QSS = """
* { font-family: "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei"; font-size: @BASE@pt; }
QWidget { color: #e3e3e3; }
QMainWindow, QDialog { background: #252527; }
QToolTip { color: #eeeeee; background: #333336; border: 1px solid #555; padding: 3px; }
QMenuBar { background: #252527; color: #dddddd; }
QMenuBar::item { padding: 4px 10px; background: transparent; }
QMenuBar::item:selected { background: #3a3a3f; }
QMenu { background: #2b2b2e; border: 1px solid #45454a; padding: 4px 0; }
QMenu::item { padding: 5px 28px 5px 24px; }
QMenu::item:selected { background: #2f6fd1; color: white; }
QMenu::item:disabled { color: #6c6c70; }
QMenu::separator { height: 1px; background: #444448; margin: 4px 8px; }
QToolBar { background: #2b2b2e; border: none; border-bottom: 1px solid #1a1a1c; spacing: 2px; padding: 3px 4px; }
QToolBar::separator { background: #45454a; width: 1px; margin: 4px 6px; }
QToolButton { color: #e0e0e0; border: 1px solid transparent; border-radius: 4px; padding: 3px 5px; background: transparent; }
QToolButton:hover { background: #3c3c42; border-color: #4a4a50; }
QToolButton:pressed { background: #2f2f34; }
QToolButton:checked { background: #2d5fa8; border-color: #3794ff; }
QToolButton::menu-indicator { image: none; width: 0; }
QToolButton#qt_toolbar_ext_button { padding: 0; border: none; }
QToolButton#qt_toolbar_ext_button:hover { background: #3c3c42; }
#ModeBar { background: #1d1d20; border-bottom: 1px solid #111113; }
#ModeBar QPushButton { color: #b8b8bc; background: transparent; border: none; border-radius: 0;
    padding: 7px 20px; font-size: @BIG@pt; border-bottom: 2px solid transparent; }
#ModeBar QPushButton:hover { color: #ffffff; background: #29292d; }
#ModeBar QPushButton:checked { color: #ffffff; border-bottom: 2px solid #3794ff; background: #26262a; }
#AppTitle { color: #e6e6e6; font-weight: 600; font-size: @BIG@pt; padding-left: 12px; }
#StatusBar { background: #1f1f22; border-top: 1px solid #141416; }
#StatusBar QLabel { color: #a8a8ae; padding: 0 6px; }
#PanelTitle { color: #9a9aa0; font-weight: 600; padding: 6px 8px 3px 8px; background: transparent; }
QListView, QTreeView, QTreeWidget, QListWidget { background: #1e1e20; border: none; outline: 0; }
QTreeView::item, QListWidget::item { padding: 3px 2px; }
QTreeView::item:hover, QListWidget::item:hover { background: #2c2c30; }
QTreeView::item:selected, QListWidget::item:selected { background: #2d5fa8; color: white; }
QHeaderView::section { background: #2a2a2d; color: #bbbbbf; border: none; border-right: 1px solid #1b1b1d; padding: 4px; }
QSplitter::handle { background: #131315; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #1e1e20; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #48484e; min-height: 30px; border-radius: 5px; margin: 1px; }
QScrollBar::handle:vertical:hover { background: #5c5c63; }
QScrollBar:horizontal { background: #1e1e20; height: 11px; margin: 0; }
QScrollBar::handle:horizontal { background: #48484e; min-width: 30px; border-radius: 5px; margin: 1px; }
QScrollBar::handle:horizontal:hover { background: #5c5c63; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #1a1a1c; border: 1px solid #3d3d42;
    border-radius: 3px; padding: 3px 5px; color: #e6e6e6; selection-background-color: #2f6fd1; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #3794ff; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 0px; border: none; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #2b2b2e; border: 1px solid #45454a; selection-background-color: #2f6fd1; }
QPushButton { background: #3a3a3f; border: 1px solid #4a4a50; border-radius: 4px; padding: 4px 12px; color: #eeeeee; }
QPushButton:hover { background: #45454b; }
QPushButton:pressed { background: #2f2f34; }
QPushButton:checked { background: #2d5fa8; border-color: #3794ff; }
QPushButton:disabled { color: #6c6c70; background: #2e2e32; }
QPushButton#Primary { background: #2f6fd1; border-color: #3794ff; color: white; }
QPushButton#Primary:hover { background: #3a7ee0; }
QPushButton#Primary:disabled { background: #2e2e32; border-color: #3a3a3f; color: #6c6c70; }
QCheckBox, QRadioButton { spacing: 6px; }
QSlider::groove:horizontal { height: 4px; background: #4a4a50; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4a4a50; border-radius: 2px; }
QSlider::handle:horizontal { background: #d8d8dc; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
QSlider::handle:horizontal:hover { background: #ffffff; }
QTabWidget::pane { border: 1px solid #38383d; border-radius: 3px; top: -1px; }
QTabBar::tab { background: #2a2a2d; color: #bdbdc2; padding: 5px 12px; border: 1px solid #38383d; border-bottom: none;
    border-top-left-radius: 3px; border-top-right-radius: 3px; margin-right: 1px; }
QTabBar::tab:selected { background: #36363b; color: #ffffff; }
QToolButton#SectionHeader { text-align: left; background: #2f2f33; color: #ececec; border: none; border-radius: 0;
    padding: 7px 6px; font-weight: 600; }
QToolButton#SectionHeader:hover { background: #38383d; }
QToolButton#SectionReset { color: #9c9ca2; background: #2f2f33; border: none; border-radius: 0; padding: 4px 8px; }
QToolButton#SectionReset:hover { color: white; background: #3a3a3f; }
QProgressDialog QLabel { padding: 6px; }
QGroupBox { border: 1px solid #3a3a3f; border-radius: 4px; margin-top: 10px; padding-top: 6px; }
QLabel#Hint { color: #8a8a90; font-size: @SMALL@pt; }
QLabel#SmallLabel { color: #9a9aa0; font-size: @SMALL@pt; }
QDoubleSpinBox#ParamSpin { min-width: 4.6em; max-width: 4.6em; }
QLineEdit#Search { min-width: 11em; max-width: 11em; }
QWidget#EditPanel { min-width: 27em; max-width: 42em; }
QLabel#ToolTitle { color: #f2f2f2; font-weight: 600; font-size: @BIG@pt; padding: 2px 0; }
QPlainTextEdit { background: #1a1a1c; border: 1px solid #3d3d42; border-radius: 3px; color: #e6e6e6;
    selection-background-color: #2f6fd1; }
QPlainTextEdit:focus { border-color: #3794ff; }
QPlainTextEdit#TextContent { min-height: 3.8em; max-height: 5.2em; }
QListWidget#TextLayers { min-height: 3.2em; max-height: 5.6em; border: 1px solid #333338; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #b5b5ba; }
"""


def build_qss(font_pt=DEFAULT_FONT_PT):
    """Stylesheet with every font size (and em-based width) derived from one base size."""
    pt = max(MIN_FONT_PT, min(MAX_FONT_PT, float(font_pt)))
    return (QSS.replace('@BASE@', f'{pt:g}')
               .replace('@BIG@', f'{round(pt * 1.1, 1):g}')
               .replace('@SMALL@', f'{round(pt * 0.9, 1):g}'))


def set_font_size(app, font_pt):
    """Change the UI font size of a running app (all widgets restyle immediately)."""
    pt = max(MIN_FONT_PT, min(MAX_FONT_PT, float(font_pt)))
    f = QFont(app.font())
    f.setFamilies(['Segoe UI', 'Microsoft JhengHei UI', 'Microsoft JhengHei'])
    f.setPointSizeF(pt)
    app.setFont(f)
    app.setStyleSheet(build_qss(pt))
    return pt


def icon_scale(font_pt):
    """Icons grow and shrink with the UI font (1.0 at the default 9.5 pt)."""
    return max(0.85, float(font_pt) / DEFAULT_FONT_PT)


def scale_icons(root, font_pt):
    """Resize toolbar / button / list icons under `root` to match the font size.

    Each widget's original icon size is remembered (Qt property 'pvBaseIcon') the first time it is
    seen, so repeated calls always scale from the design size instead of compounding.
    """
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import (QWidget, QToolBar, QToolButton, QAbstractButton, QListView,
                                   QTreeView, QListWidget)
    s = icon_scale(font_pt)
    from .common import glyph_icon
    for tb in ([root] if isinstance(root, QToolBar) else []) + root.findChildren(QToolBar):
        # Qt's overflow button draws a dark arrow that is invisible on this theme: use a light chevron
        ext = tb.findChild(QToolButton, 'qt_toolbar_ext_button')
        if ext is not None:
            ext.setIcon(glyph_icon(''))
            ext.setIconSize(QSize(max(12, round(14 * s)), max(12, round(14 * s))))
            ext.setToolTip('更多工具')
    for w in [root] + root.findChildren(QWidget):
        if isinstance(w, QToolButton) and isinstance(w.parentWidget(), QToolBar):
            continue                      # sized by its toolbar
        if isinstance(w, QListView) and not isinstance(w, QListWidget) and w.viewMode() == QListView.IconMode:
            continue                      # thumbnail grids size themselves (thumbnail size slider)
        if not isinstance(w, (QToolBar, QAbstractButton, QTreeView, QListWidget)):
            continue
        base = w.property('pvBaseIcon')
        if base is None:
            base = w.iconSize()
            if base.width() <= 0 or base.height() <= 0:   # "unset" (-1): use the style's small-icon size
                px = w.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, None, w)
                base = QSize(px, px)
            w.setProperty('pvBaseIcon', base)
        w.setIconSize(QSize(max(8, round(base.width() * s)), max(8, round(base.height() * s))))


def apply_theme(app, font_pt=DEFAULT_FONT_PT):
    app.setStyle(_Style(QStyleFactory.create('Fusion')))
    pal = QPalette()
    c = QColor
    pal.setColor(QPalette.Window, c(37, 37, 39))
    pal.setColor(QPalette.WindowText, c(227, 227, 227))
    pal.setColor(QPalette.Base, c(30, 30, 32))
    pal.setColor(QPalette.AlternateBase, c(42, 42, 45))
    pal.setColor(QPalette.ToolTipBase, c(51, 51, 54))
    pal.setColor(QPalette.ToolTipText, c(238, 238, 238))
    pal.setColor(QPalette.Text, c(227, 227, 227))
    pal.setColor(QPalette.Button, c(52, 52, 56))
    pal.setColor(QPalette.ButtonText, c(227, 227, 227))
    pal.setColor(QPalette.BrightText, c(255, 80, 80))
    pal.setColor(QPalette.Highlight, c(47, 111, 209))
    pal.setColor(QPalette.HighlightedText, c(255, 255, 255))
    pal.setColor(QPalette.Link, c(90, 160, 255))
    pal.setColor(QPalette.PlaceholderText, c(120, 120, 126))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, c(110, 110, 115))
    app.setPalette(pal)
    set_font_size(app, font_pt)
