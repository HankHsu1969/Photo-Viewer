"""Refresh licenses/ from the build environment: third-party license texts + THIRD-PARTY-NOTICES.txt.

Run by build.bat before PyInstaller; build.bat then copies licenses/ next to the executables.
LGPL-3.0.txt and GPL-3.0.txt are fixed texts kept in the repository (the PySide6 wheels do not ship them).
"""
import importlib.metadata as md
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'licenses')


def version(dist):
    return md.version(dist)


def dist_license_files(dist):
    d = md.distribution(dist)
    files = [f for f in (d.files or []) if '/licenses/' in str(f).replace('\\', '/')]
    return [(str(f).replace('\\', '/').split('/licenses/', 1)[1], d.locate_file(f)) for f in files]


def write_concat(name, dist):
    """All license files of a distribution in one text file, each under its own heading."""
    parts = []
    for rel, path in sorted(dist_license_files(dist), key=lambda t: (t[0].count('/'), t[0])):
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read().strip('\n')
        parts.append(f"{'=' * 78}\n{dist} {version(dist)} : {rel}\n{'=' * 78}\n\n{text}\n")
    if not parts:
        sys.exit(f'no license files found for {dist}')
    with open(os.path.join(OUT, name), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n\n'.join(parts))


NOTICES = """Kirapix / Kirapix Quick — 第三方元件授權聲明（Third-party notices）

本程式（Kirapix 與 Kirapix Quick）使用下列開放原始碼元件，各元件依其授權條款散布。
完整授權條文都放在這個 licenses 資料夾中。
This software uses the open-source components listed below. Each is distributed under its own
license; the full license texts are in this "licenses" folder.


1. Qt 6 / Qt for Python（PySide6 {pyside}、Shiboken6 {shiboken}）
   授權 License : GNU Lesser General Public License v3（LGPL-3.0.txt；LGPL v3 引用 GPL-3.0.txt 的條文）
   著作權 Copyright : The Qt Company Ltd. 及其他貢獻者 and other contributors
   原始碼 Source : https://download.qt.io/official_releases/qt/
                   https://code.qt.io/cgit/pyside/pyside-setup.git/
   Qt 隨附的第三方元件 Third-party code in Qt : https://doc.qt.io/qt-6/licenses-used-in-qt.html

   本程式以動態連結方式使用未經修改的 Qt 與 PySide6：Qt 函式庫是程式資料夾內獨立的 DLL 檔案
   （_internal\\PySide6），可以用相容的版本自行替換。
   Qt and PySide6 are used unmodified and linked dynamically: the Qt libraries are separate DLL
   files in the program folder (_internal\\PySide6) and can be replaced with compatible versions.

2. Python {python}
   授權 License : Python Software Foundation License Version 2（Python-LICENSE.txt，含 Python 隨附元件的授權）
   著作權 Copyright : Python Software Foundation

3. NumPy {numpy}
   授權 License : BSD 3-Clause，及 NumPy 隨附元件的授權（NumPy-LICENSE.txt）
   著作權 Copyright : NumPy Developers

4. Pillow {pillow}
   授權 License : MIT-CMU（HPND），及 Pillow 隨附影像函式庫的授權（Pillow-LICENSE.txt）
   著作權 Copyright : Jeffrey A. Clark and contributors; Secret Labs AB; Fredrik Lundh

5. PyInstaller {pyinstaller}（程式啟動器 bootloader）
   授權 License : GNU GPL v2 或更新版本，附 bootloader 例外條款：允許以任何條款散布用 PyInstaller
                  打包的程式（PyInstaller-COPYING.txt）
   GPL 2.0 or later with a bootloader exception that allows distributing bundled programs under any terms.
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    for fixed in ('LGPL-3.0.txt', 'GPL-3.0.txt'):
        if not os.path.exists(os.path.join(OUT, fixed)):
            sys.exit(f'missing licenses/{fixed}')
    shutil.copyfile(os.path.join(sys.base_prefix, 'LICENSE.txt'), os.path.join(OUT, 'Python-LICENSE.txt'))
    write_concat('NumPy-LICENSE.txt', 'numpy')
    write_concat('Pillow-LICENSE.txt', 'pillow')
    write_concat('PyInstaller-COPYING.txt', 'pyinstaller')
    text = NOTICES.format(pyside=version('PySide6-Essentials'), shiboken=version('shiboken6'),
                          python=sys.version.split()[0], numpy=version('numpy'), pillow=version('pillow'),
                          pyinstaller=version('pyinstaller'))
    with open(os.path.join(OUT, 'THIRD-PARTY-NOTICES.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(text)
    print('licenses/ updated:', ', '.join(sorted(os.listdir(OUT))))


if __name__ == '__main__':
    main()
