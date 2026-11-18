# -*- mode: python ; coding: utf-8 -*-
# Build:  python -m PyInstaller packaging/PhotoViewer.spec --noconfirm --distpath dist --workpath build
#
# Produces one folder with two executables sharing the same libraries:
#   PhotoViewer.exe  full manager / viewer / editor
#   QuickViewer.exe  Quick Viewer: lightweight fast viewer for double-clicked images (QtGui only)
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
ICON = os.path.join(ROOT, 'assets', 'app.ico')
COMMON_EXCLUDES = ['tkinter', '_tkinter', 'PyInstaller', 'setuptools', 'pip',
                   'PySide6.QtNetwork', 'ssl', '_ssl', '_hashlib', 'PIL._avif', 'PIL.AvifImagePlugin']

full = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    datas=[(ICON, 'assets')],
    excludes=COMMON_EXCLUDES,
    noarchive=False,
)
quick = Analysis(
    [os.path.join(ROOT, 'quickviewer.py')],
    pathex=[ROOT],
    excludes=COMMON_EXCLUDES + ['numpy', 'PySide6.QtWidgets'],
    noarchive=False,
)


# Drop pieces the app never uses (software OpenGL, Direct2D platform, non-Chinese Qt translations).
def _keep(name):
    n = name.replace('\\', '/').lower()
    if 'opengl32sw' in n or 'qdirect2d' in n:
        return False
    if '/translations/' in n and not n.endswith(('_zh_tw.qm',)):
        return False
    return True


for a in (full, quick):
    a.binaries = [b for b in a.binaries if _keep(b[0])]
    a.datas = [d for d in a.datas if _keep(d[0])]

full_exe = EXE(
    PYZ(full.pure),
    full.scripts,
    [],
    exclude_binaries=True,
    name='PhotoViewer',
    console=False,
    icon=ICON,
    version=os.path.join(SPECPATH, 'version_info.txt'),
    upx=False,
)
quick_exe = EXE(
    PYZ(quick.pure),
    quick.scripts,
    [],
    exclude_binaries=True,
    name='QuickViewer',
    console=False,
    icon=ICON,
    version=os.path.join(SPECPATH, 'version_info_quick.txt'),
    upx=False,
)

coll = COLLECT(
    full_exe,
    quick_exe,
    full.binaries,
    quick.binaries,
    full.datas,
    quick.datas,
    name='PhotoViewer',
    upx=False,
)
