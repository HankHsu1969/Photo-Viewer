"""Photo Viewer 看圖 - entry point.

Usage:
    python main.py                 open the manager at the last folder
    python main.py <image file>    open the image in view mode (←/→ to browse the folder)
    python main.py <folder>        open the manager at that folder
"""
import os
import sys


def _install_crash_log():
    """A windowed exe has no console: log uncaught errors to %APPDATA%\\PhotoViewer\\error.log and show them."""
    import time
    import traceback
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    log_dir = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'PhotoViewer')

    def hook(exc_type, exc, tb):
        text = ''.join(traceback.format_exception(exc_type, exc, tb))
        try:
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, 'error.log'), 'a', encoding='utf-8') as f:
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n{text}")
        except OSError:
            pass
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(None, 'Photo Viewer 錯誤',
                                     f'發生未預期的錯誤（已記錄到 {log_dir}\\error.log）：\n\n{exc}')
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def _load_qt_translation(app):
    """Show Qt's built-in dialog buttons (Yes/No/OK/Cancel...) in Traditional Chinese."""
    from PySide6.QtCore import QTranslator, QLibraryInfo
    import PySide6
    dirs = [QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
            os.path.join(os.path.dirname(PySide6.__file__), 'translations')]
    tr = QTranslator(app)
    for d in dirs:
        if d and tr.load('qtbase_zh_TW', d):
            app.installTranslator(tr)
            app._qt_translator = tr
            return True
    return False


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    _install_crash_log()
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('PhotoViewer.App')
        except Exception:  # noqa: BLE001
            pass

    from PySide6.QtWidgets import QApplication
    from pv.theme import apply_theme
    from pv.mainwindow import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName('PhotoViewer')
    app.setOrganizationName('PhotoViewer')
    _load_qt_translation(app)
    apply_theme(app)
    start = sys.argv[1] if len(sys.argv) > 1 else None
    win = MainWindow(start)
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
