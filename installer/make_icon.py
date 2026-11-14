"""Generate partseek.ico — a magnifier over a document in ETS blue.

Run from the project root:  .venv\\Scripts\\python installer\\make_icon.py
"""
import os

from PIL import Image, ImageDraw

BLUE = (31, 95, 191, 255)
BLUE_DARK = (20, 64, 130, 255)
PAPER = (247, 249, 252, 255)
INK = (120, 140, 165, 255)
WHITE = (255, 255, 255, 255)

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Rounded blue tile background.
d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=48, fill=BLUE)

# Document sheet.
doc = [66, 52, 168, 196]
d.rounded_rectangle(doc, radius=12, fill=PAPER)
for i, y in enumerate(range(80, 150, 18)):
    w = 150 if i % 2 == 0 else 134
    d.rounded_rectangle([84, y, 84 + (w - 84) + 0, y + 7], radius=3, fill=INK)
    d.rounded_rectangle([84, y, w, y + 7], radius=3, fill=INK)

# Magnifier: ring + handle.
cx, cy, r = 168, 168, 44
d.ellipse([cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10], fill=BLUE_DARK)
d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
d.ellipse([cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12], fill=BLUE)
d.line([cx + 30, cy + 30, cx + 70, cy + 70], fill=BLUE_DARK, width=22)
d.line([cx + 30, cy + 30, cx + 70, cy + 70], fill=WHITE, width=6)

out = os.path.join(os.path.dirname(__file__), "..", "partseek.ico")
out = os.path.abspath(out)
img.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Wrote", out)
