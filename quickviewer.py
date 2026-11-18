"""Quick Viewer - fast, lightweight image viewer (entry point for QuickViewer.exe).

Usage:
    QuickViewer.exe <image file>   view it; ←/→ browse the folder; double-click / Enter opens Photo Viewer
    QuickViewer.exe <folder>       view the first image of the folder
    QuickViewer.exe                starts Photo Viewer instead
"""
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from pv import startup
    startup.install_crash_log(lambda msg: startup.message_box(msg, 'Quick Viewer 錯誤'))
    startup.set_app_id('PhotoViewer.QuickViewer')

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    target = os.path.abspath(args[0].strip('"')) if args else None
    if not target or not os.path.exists(target):
        startup.launch_full_app()
        return

    from pv.common import list_images
    if os.path.isdir(target):
        files = list_images(target)
        if not files:
            startup.launch_full_app(target)
            return
        target = files[0]

    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication(sys.argv)
    app.setApplicationName('PhotoViewer')
    app.setOrganizationName('PhotoViewer')
    from pv.quick import QuickWindow
    win = QuickWindow(target)
    win.start()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
