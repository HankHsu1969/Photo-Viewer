"""Kirapix - photo manager / viewer / editor (entry point for PhotoViewer.exe).

Usage:
    python main.py                       open the manager at the last folder
    python main.py <image file>          open the image in view mode (←/→ to browse the folder)
    python main.py <folder>              open the manager at that folder
    python main.py --manage <image>      open the manager with that image selected (used by Kirapix Quick)
    python main.py --edit <image>        open that image in the editor (used by Kirapix Quick)
"""
import os
import sys


def _show_error(msg):
    from PySide6.QtWidgets import QApplication, QMessageBox
    if QApplication.instance() is not None:
        QMessageBox.critical(None, 'Kirapix 錯誤', msg)


def parse_args(argv):
    mode, path = None, None
    for a in argv:
        if a in ('--manage', '--edit', '--view'):
            mode = a[2:]
        elif not a.startswith('--') and path is None:
            path = a.strip('"')
    return mode, path


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from pv import startup
    startup.install_crash_log(_show_error)
    startup.set_app_id('PhotoViewer.App')

    from PySide6.QtWidgets import QApplication
    from pv.theme import apply_theme
    from pv.mainwindow import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName('PhotoViewer')
    app.setOrganizationName('PhotoViewer')
    startup.load_qt_translation(app)
    from pv.common import Settings
    from pv.theme import DEFAULT_FONT_PT
    apply_theme(app, Settings().get('ui/font_size', DEFAULT_FONT_PT, float))
    mode, path = parse_args(sys.argv[1:])
    win = MainWindow(path, mode)
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
