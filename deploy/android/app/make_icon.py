"""生成 App 图标（一次性脚本，生成后即可删除）。"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "res", "mipmap-xxxhdpi")
os.makedirs(OUT, exist_ok=True)

SIZE = 192
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角矩形渐变底
radius = 42
for y in range(SIZE):
    t = y / (SIZE - 1)
    r = int(76 + (123 - 76) * t)
    g = int(141 + (92 - 141) * t)
    b = int(255 + (255 - 255) * t)
    d.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius, fill=255)
img.putalpha(mask)

# 中间画「¥」符号
d = ImageDraw.Draw(img)
font = None
for path in (
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
):
    if os.path.exists(path):
        try:
            font = ImageFont.truetype(path, 108)
            break
        except Exception:
            continue

if font:
    text = "¥"
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((SIZE - w) / 2 - box[0], (SIZE - h) / 2 - box[1] - 4),
           text, font=font, fill=(255, 255, 255, 255))
else:
    d.rectangle([78, 60, 114, 132], fill=(255, 255, 255, 255))

img.save(os.path.join(OUT, "ic_launcher.png"))
print("saved", os.path.join(OUT, "ic_launcher.png"))
