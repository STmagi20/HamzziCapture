"""이미지 처리: 편집기 도형 그리기, 모자이크, 둥근 모서리, 파일 저장.

tkinter를 쓰지 않으므로 화면 없이도 테스트할 수 있다.
"""
import datetime
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont

from i18n import tr

MOSAIC_MIN_BLOCK = 12  # 모자이크 칸 최소 크기(px)
MOSAIC_NOISE = 24      # 칸마다 더하는 밝기 흔들림(±)


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def norm_box(p0, p1):
    return (min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1]))


def load_font(size):
    for name in ("malgun.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


# ----------------------------------------------------------------------------
# 편집기 도형
# ----------------------------------------------------------------------------
def draw_arrow(draw, p0, p1, fill, width):
    draw.line([p0, p1], fill=fill, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    head = max(12, width * 4)
    for da in (math.radians(155), -math.radians(155)):
        end = (p1[0] + head * math.cos(ang + da), p1[1] + head * math.sin(ang + da))
        draw.line([p1, end], fill=fill, width=width)


def mosaic_block(width):
    """굵기에 따른 모자이크 칸 크기."""
    return max(MOSAIC_MIN_BLOCK, width * 3)


def apply_mosaic(img, box, width):
    """img의 box 영역을 모자이크한 새 이미지를 반환 (영역이 너무 작으면 그대로)."""
    l, t, r, b = [int(v) for v in box]
    l, t = max(0, l), max(0, t)
    r, b = min(img.width, r), min(img.height, b)
    if r - l < 2 or b - t < 2:
        return img
    region = img.crop((l, t, r, b))
    block = mosaic_block(width)
    small = region.resize((max(1, (r - l) // block), max(1, (b - t) // block)), Image.BILINEAR)
    # 칸마다 밝기를 무작위로 흔든다. 평균색만 남기면 글꼴을 아는 사람이 후보 글자를
    # 똑같이 모자이크해 비교하는 방식으로 숫자·글자를 되살릴 수 있다.
    pix = small.load()
    for y in range(small.height):
        for x in range(small.width):
            cr, cg, cb, ca = pix[x, y]
            n = random.randint(-MOSAIC_NOISE, MOSAIC_NOISE)
            pix[x, y] = (_clamp(cr + n), _clamp(cg + n), _clamp(cb + n), ca)
    img = img.copy()
    img.paste(small.resize(region.size, Image.NEAREST), (l, t))
    return img


def _clamp(v):
    return min(255, max(0, v))


def apply_shape(img, tool, pts, color, width):
    """img(RGBA)에 도형을 그려 새 이미지를 반환."""
    rgb = hex_to_rgb(color)
    fill = rgb + (255,)
    p0, p1 = pts[0], pts[-1]

    if tool == "highlight":
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle(norm_box(p0, p1), fill=rgb + (90,))
        return Image.alpha_composite(img, overlay)

    if tool == "mosaic":
        return apply_mosaic(img, norm_box(p0, p1), width)

    img = img.copy()
    d = ImageDraw.Draw(img)
    if tool == "pen":
        if len(pts) == 1:
            pts = pts * 2
        d.line(pts, fill=fill, width=width, joint="curve")
        r = width / 2
        for x, y in (pts[0], pts[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=fill)
    elif tool == "line":
        d.line([p0, p1], fill=fill, width=width)
    elif tool == "arrow":
        draw_arrow(d, p0, p1, fill, width)
    elif tool == "rect":
        d.rectangle(norm_box(p0, p1), outline=fill, width=width)
    elif tool == "ellipse":
        d.ellipse(norm_box(p0, p1), outline=fill, width=width)
    return img


def crop_image(img, p0, p1, min_size=8):
    """두 점으로 잡은 영역만 남긴 새 이미지. 이미지 밖은 잘라내고, 너무 작으면 None."""
    l, t, r, b = norm_box(p0, p1)
    l, t = max(0, int(round(l))), max(0, int(round(t)))
    r, b = min(img.width, int(round(r))), min(img.height, int(round(b)))
    if r - l < min_size or b - t < min_size:
        return None
    return img.crop((l, t, r, b))


def apply_text(img, pos, text, color, width):
    img = img.copy()
    ImageDraw.Draw(img).text(
        pos, text, fill=hex_to_rgb(color) + (255,), font=load_font(max(14, width * 5))
    )
    return img


def rounded_image(img, radius):
    """이미지 모서리를 둥글게 (투명 마스크)."""
    img = img.convert("RGBA")
    k = 4
    mask = Image.new("L", (img.width * k, img.height * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, img.width * k - 1, img.height * k - 1), radius=radius * k, fill=255
    )
    img.putalpha(mask.resize(img.size, Image.LANCZOS))
    return img


# ----------------------------------------------------------------------------
# 파일 저장
# ----------------------------------------------------------------------------
def to_rgb(img, bg=(255, 255, 255)):
    """투명도를 흰 배경에 합성해 RGB로 만든다 (그냥 convert하면 투명한 곳이 검게 나온다)."""
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        out = Image.new("RGB", rgba.size, bg)
        out.paste(rgba, mask=rgba.getchannel("A"))
        return out
    return img.convert("RGB")


def save_image(img, path):
    """PNG/JPG로만 저장한다. 그 외 확장자는 이해하기 쉬운 오류로 알려준다. 폴더가 없으면 만든다."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        raise ValueError(tr("err_ext"))
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    if ext == ".png":
        img.save(path, "PNG")
    else:
        to_rgb(img).save(path, "JPEG", quality=95)


def default_save_dir():
    pics = os.path.join(os.path.expanduser("~"), "Pictures")
    return pics if os.path.isdir(pics) else os.path.expanduser("~")


def timestamp_name(ext="png"):
    return datetime.datetime.now().strftime("capture_%Y%m%d_%H%M%S.") + ext


def unique_path(folder, ext="png"):
    """folder 안에서 겹치지 않는 캡처 파일 경로 (같은 초에 두 번 찍어도 덮어쓰지 않는다)."""
    base, ext = os.path.splitext(timestamp_name(ext))
    path = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base}_{n}{ext}")
        n += 1
    return path
