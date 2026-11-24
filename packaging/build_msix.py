"""Build the Microsoft Store package: dist\\msix\\Kirapix-<version>.msix (unsigned; the Store signs it).

Needs the built app in dist\\PhotoViewer (run build.bat first) and the Windows SDK build tools
(makeappx.exe / makepri.exe). They are looked up in tools\\winsdk (the Microsoft.Windows.SDK.BuildTools
NuGet package, extracted), then in the installed Windows Kits.

Store identity values (Partner Center > Product identity) come from packaging\\msix\\identity.local.json,
which is gitignored so the publisher name stays out of the public repo. Without it, the placeholder
values in identity.json are used and the package is only a test build named *-TEST.msix.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import xml.dom.minidom

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
APP = os.path.join(ROOT, 'dist', 'PhotoViewer')
OUT = os.path.join(ROOT, 'dist', 'msix')
LAYOUT = os.path.join(OUT, 'layout')
PRI_ROOT = os.path.join(OUT, 'pri')
FILE_TYPES = ['.jpg', '.jpeg', '.jpe', '.jfif', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff', '.ico', '.tga']
SKIP = {'Register-OpenWith.bat', 'Unregister-OpenWith.bat', 'register_open_with.ps1', 'unregister_open_with.ps1'}


def app_version():
    ns = {}
    with open(os.path.join(ROOT, 'pv', '__init__.py'), encoding='utf-8') as f:
        exec(f.read(), ns)
    parts = (ns['__version__'].split('.') + ['0', '0', '0'])[:3]
    return '.'.join(parts) + '.0'          # the Store requires the 4th part to be 0


def find_tool(name):
    pats = [os.path.join(ROOT, 'tools', 'winsdk', 'bin', '*', 'x64', name),
            os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                         'Windows Kits', '10', 'bin', '*', 'x64', name)]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def make_assets(dest):
    """Tile / logo images in every scale, drawn from the app icon artwork."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    from pv.common import app_icon_image
    os.makedirs(dest, exist_ok=True)

    def tile(w, h, frac):
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        s = max(16, round(min(w, h) * frac))
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage((w - s) // 2, (h - s) // 2, app_icon_image(s))
        p.end()
        return img

    out = []

    def save(img, name):
        img.save(os.path.join(dest, name))
        out.append(name)

    for scale in (100, 200, 400):
        k = scale / 100
        save(tile(round(50 * k), round(50 * k), 1.0), f'StoreLogo.scale-{scale}.png')
        save(tile(round(150 * k), round(150 * k), 0.66), f'Square150x150Logo.scale-{scale}.png')
        save(tile(round(44 * k), round(44 * k), 1.0), f'Square44x44Logo.scale-{scale}.png')
        if scale <= 200:
            save(tile(round(310 * k), round(150 * k), 0.66), f'Wide310x150Logo.scale-{scale}.png')
    for ts in (16, 20, 24, 32, 40, 48, 64, 256):
        save(app_icon_image(ts), f'Square44x44Logo.targetsize-{ts}.png')
        save(app_icon_image(ts), f'Square44x44Logo.targetsize-{ts}_altform-unplated.png')
    # unqualified fallbacks (used if no resources.pri is present)
    for base in ('StoreLogo', 'Square150x150Logo', 'Square44x44Logo', 'Wide310x150Logo'):
        shutil.copyfile(os.path.join(dest, f'{base}.scale-100.png'), os.path.join(dest, f'{base}.png'))
    return out


def manifest_text(ident, version):
    with open(os.path.join(ROOT, 'packaging', 'msix', 'AppxManifest.xml.in'), encoding='utf-8') as f:
        tpl = f.read()
    types = '\n'.join(f'              <uap:FileType>{t}</uap:FileType>' for t in FILE_TYPES)
    text = (tpl.replace('{name}', ident['name']).replace('{publisher}', ident['publisher'])
               .replace('{publisher_display}', ident['publisher_display']).replace('{version}', version)
               .replace('{file_types}', types))
    xml.dom.minidom.parseString(text.encode('utf-8'))      # must be well-formed
    return text


def run(cmd):
    print('>', ' '.join(f'"{c}"' if ' ' in c else c for c in cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit(f'failed: {os.path.basename(cmd[0])} (exit {r.returncode})')
    return r.stdout


def main():
    if not os.path.exists(os.path.join(APP, 'PhotoViewer.exe')):
        sys.exit('dist\\PhotoViewer not found: run build.bat first')
    msix_dir = os.path.join(ROOT, 'packaging', 'msix')
    local = os.path.join(msix_dir, 'identity.local.json')     # real values, kept out of git
    with open(local if os.path.exists(local) else os.path.join(msix_dir, 'identity.json'), encoding='utf-8') as f:
        ident = json.load(f)
    test = 'PLACEHOLDER' in ident['name'] or 'PLACEHOLDER' in ident['publisher_display'] \
        or ident['publisher'].startswith('CN=00000000')
    version = app_version()

    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(APP, LAYOUT, ignore=lambda d, names: [n for n in names if n in SKIP])
    manifest = manifest_text(ident, version)
    with open(os.path.join(LAYOUT, 'AppxManifest.xml'), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(manifest)
    assets = make_assets(os.path.join(LAYOUT, 'Assets'))
    print(f'layout ready: {LAYOUT}  (version {version}, {len(assets)} asset images)')

    makepri, makeappx = find_tool('makepri.exe'), find_tool('makeappx.exe')
    if not (makepri and makeappx):
        print('Windows SDK build tools not found (tools\\winsdk or Windows Kits): layout only, no .msix.')
        return
    # resources.pri lets Windows pick the right scale / target-size images; build it from a small root
    os.makedirs(PRI_ROOT)
    shutil.copytree(os.path.join(LAYOUT, 'Assets'), os.path.join(PRI_ROOT, 'Assets'))
    shutil.copyfile(os.path.join(LAYOUT, 'AppxManifest.xml'), os.path.join(PRI_ROOT, 'AppxManifest.xml'))
    cfg = os.path.join(OUT, 'priconfig.xml')
    run([makepri, 'createconfig', '/cf', cfg, '/dq', 'zh-TW', '/pv', '10.0.0', '/o'])
    run([makepri, 'new', '/pr', PRI_ROOT, '/cf', cfg, '/mn', os.path.join(PRI_ROOT, 'AppxManifest.xml'),
         '/of', os.path.join(LAYOUT, 'resources.pri'), '/o'])
    name = f'Kirapix-{version}' + ('-TEST' if test else '') + '.msix'
    pkg = os.path.join(OUT, name)
    run([makeappx, 'pack', '/o', '/h', 'SHA256', '/d', LAYOUT, '/p', pkg])
    print(f'package: {pkg}  ({os.path.getsize(pkg):,} bytes)')
    if test:
        print('NOTE: no packaging\\msix\\identity.local.json - placeholder identity, test build only, not for upload.')


if __name__ == '__main__':
    main()
