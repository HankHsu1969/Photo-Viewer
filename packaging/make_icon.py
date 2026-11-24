"""Render the app icon (same artwork as pv.common.app_icon) to assets/app.ico."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PIL import Image  # noqa: E402
import io  # noqa: E402


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841
    from pv.common import app_icon_image, ICON_SIZES
    images = []
    for s in sorted(ICON_SIZES, reverse=True):   # 256 ... 16, each drawn natively (not downscaled)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        app_icon_image(s).save(buf, 'PNG')
        buf.close()
        images.append(Image.open(io.BytesIO(bytes(ba))).convert('RGBA'))
    out_dir = os.path.join(ROOT, 'assets')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'app.ico')
    images[0].save(out, format='ICO', sizes=[(im.width, im.height) for im in images], append_images=images[1:])
    images[0].save(os.path.join(out_dir, 'app.png'))
    print('wrote', out)


if __name__ == '__main__':
    main()
