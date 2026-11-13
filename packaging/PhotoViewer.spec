# -*- mode: python ; coding: utf-8 -*-
# Build:  python -m PyInstaller packaging/PhotoViewer.spec --noconfirm --distpath dist --workpath build
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
ICON = os.path.join(ROOT, 'assets', 'app.ico')

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[(ICON, 'assets')],
    hiddenimports=[],
    excludes=['tkinter', '_tkinter', 'PyInstaller', 'setuptools', 'pip',
              'PySide6.QtNetwork', 'ssl', '_ssl', '_hashlib', 'PIL._avif', 'PIL.AvifImagePlugin'],
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

a.binaries = [b for b in a.binaries if _keep(b[0])]
a.datas = [d for d in a.datas if _keep(d[0])]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PhotoViewer',
    console=False,
    icon=ICON,
    version=os.path.join(SPECPATH, 'version_info.txt'),
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='PhotoViewer',
    upx=False,
)
