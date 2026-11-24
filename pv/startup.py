"""Startup helpers shared by both executables (no QtWidgets import here)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback


def install_crash_log(show_error=None):
    """A windowed exe has no console: log uncaught errors to %APPDATA%\\PhotoViewer\\error.log."""
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
        if show_error is not None:
            try:
                show_error(f'發生未預期的錯誤（已記錄到 {log_dir}\\error.log）：\n\n{exc}')
            except Exception:  # noqa: BLE001
                pass

    sys.excepthook = hook


def load_qt_translation(app):
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


def set_app_id(app_id='PhotoViewer.App'):
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:  # noqa: BLE001
            pass


def message_box(text, title='Kirapix', yes_no=False, hwnd=0):
    """Native Windows message box (works without QtWidgets). Returns True for OK/Yes."""
    if sys.platform != 'win32':
        return False
    import ctypes
    MB_OK, MB_YESNO, MB_ICONQUESTION, MB_ICONERROR = 0x0, 0x4, 0x20, 0x10
    flags = (MB_YESNO | MB_ICONQUESTION) if yes_no else (MB_OK | MB_ICONERROR)
    r = ctypes.windll.user32.MessageBoxW(int(hwnd), str(text), str(title), flags)
    return r in (1, 6)  # IDOK, IDYES


def full_app_command(*args):
    """Command line that starts the full manager/editor (PhotoViewer.exe, or main.py when run from source)."""
    if getattr(sys, 'frozen', False):
        exe = os.path.join(os.path.dirname(sys.executable), 'PhotoViewer.exe')
        return [exe, *args]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), 'pythonw.exe')
    if os.path.exists(pyw):
        py = pyw
    return [py, os.path.join(root, 'main.py'), *args]


def launch_full_app(*args):
    cmd = full_app_command(*args)
    flags = 0
    if sys.platform == 'win32':
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(cmd, close_fds=True, creationflags=flags,
                            cwd=os.path.dirname(cmd[0]) if getattr(sys, 'frozen', False) else None)
