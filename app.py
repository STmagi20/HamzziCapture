"""햄찌캡처 - 간단 화면 캡처 프로그램 (Windows)

기능
- 영역 선택 캡처 / 전체 화면(모든 모니터) / 활성 창 캡처
- 지연 캡처(초)
- 편집기: 펜, 형광펜, 선, 화살표, 사각형, 원, 텍스트, 모자이크, 실행 취소
- 저장(PNG/JPG) + 클립보드 복사
- 전역 단축키: Ctrl+Shift+A (영역), M (현재 모니터), F (모든 모니터), W (활성 창)
"""
import ctypes
import datetime
import io
import math
import os
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from ctypes import wintypes
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

import assets
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageGrab, ImageOps, ImageTk

IS_WIN = sys.platform == "win32"

# 앱 정보 (정보 창에 표시)
APP_NAME = "햄찌캡처"
VERSION = "1.0.0"
AUTHOR = "Studying Hamzzi"

if IS_WIN:  # 고DPI 환경에서 캡처 좌표가 어긋나지 않도록
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ----------------------------------------------------------------------------
# 화면/클립보드 유틸
# ----------------------------------------------------------------------------
def virtual_origin():
    """가상 화면(모든 모니터)의 좌상단 좌표."""
    if IS_WIN:
        u = ctypes.windll.user32
        return u.GetSystemMetrics(76), u.GetSystemMetrics(77)
    return 0, 0


def get_monitors():
    """모니터별 화면 좌표 [(left, top, right, bottom), ...]."""
    if not IS_WIN:
        return []
    mons = []
    PROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    def cb(hmon, hdc, rect, lparam):
        r = rect.contents
        mons.append((r.left, r.top, r.right, r.bottom))
        return True

    u = ctypes.windll.user32
    u.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), PROC, wintypes.LPARAM]
    u.EnumDisplayMonitors(None, None, PROC(cb), 0)
    return sorted(mons)


def grab_screen():
    img = ImageGrab.grab(all_screens=True).convert("RGB")
    return img, virtual_origin()


def active_window_rect():
    """활성 창의 화면 좌표 (left, top, right, bottom)."""
    if not IS_WIN:
        return None
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    rect = wintypes.RECT()
    # 그림자를 제외한 실제 창 영역 (DWMWA_EXTENDED_FRAME_BOUNDS = 9)
    ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    if ok != 0:
        u.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def own_window_active():
    """지금 맨 앞(활성) 창이 이 프로그램(햄찌캡처)의 창이면 True."""
    if not IS_WIN:
        return False
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return pid.value == os.getpid()


def copy_image_to_clipboard(img):
    """PIL 이미지를 Windows 클립보드(DIB)에 복사."""
    if not IS_WIN:
        raise RuntimeError("클립보드 복사는 Windows에서만 지원합니다.")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    data = buf.getvalue()[14:]  # BMP 파일 헤더 제거 -> DIB

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p

    GMEM_MOVEABLE, CF_DIB = 0x0002, 8
    if not user32.OpenClipboard(None):
        raise RuntimeError("클립보드를 열 수 없습니다.")
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            raise RuntimeError("메모리를 확보하지 못했습니다.")
        p = kernel32.GlobalLock(h)
        if not p:
            kernel32.GlobalFree(h)
            raise RuntimeError("메모리를 잠그지 못했습니다.")
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_DIB, h):
            kernel32.GlobalFree(h)  # 클립보드가 가져가지 않았으므로 직접 해제
            raise RuntimeError("클립보드에 데이터를 넣지 못했습니다.")
    finally:
        user32.CloseClipboard()


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


def save_image(img, path):
    """PNG/JPG로만 저장한다. 그 외 확장자는 이해하기 쉬운 오류로 알려준다."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        img.save(path, "PNG")
    elif ext in (".jpg", ".jpeg"):
        img.convert("RGB").save(path, "JPEG", quality=95)
    else:
        raise ValueError("PNG(.png) 또는 JPG(.jpg) 확장자로 저장해 주세요.")


def default_save_dir():
    pics = os.path.join(os.path.expanduser("~"), "Pictures")
    return pics if os.path.isdir(pics) else os.path.expanduser("~")


def timestamp_name(ext="png"):
    return datetime.datetime.now().strftime("capture_%Y%m%d_%H%M%S.") + ext


# ----------------------------------------------------------------------------
# 그리기 (PIL 이미지 위에 직접)
# ----------------------------------------------------------------------------
def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def norm_box(p0, p1):
    return (min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1]))


def draw_arrow(draw, p0, p1, fill, width):
    draw.line([p0, p1], fill=fill, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    head = max(12, width * 4)
    for da in (math.radians(155), -math.radians(155)):
        end = (p1[0] + head * math.cos(ang + da), p1[1] + head * math.sin(ang + da))
        draw.line([p1, end], fill=fill, width=width)


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
        l, t, r, b = [int(v) for v in norm_box(p0, p1)]
        l, t = max(0, l), max(0, t)
        r, b = min(img.width, r), min(img.height, b)
        if r - l < 2 or b - t < 2:
            return img
        region = img.crop((l, t, r, b))
        block = max(6, width * 3)
        small = region.resize(
            (max(1, (r - l) // block), max(1, (b - t) // block)), Image.BILINEAR
        )
        img = img.copy()
        img.paste(small.resize(region.size, Image.NEAREST), (l, t))
        return img

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


def apply_text(img, pos, text, color, width):
    img = img.copy()
    ImageDraw.Draw(img).text(
        pos, text, fill=hex_to_rgb(color) + (255,), font=load_font(max(14, width * 5))
    )
    return img


# ----------------------------------------------------------------------------
# 영역 선택 오버레이
# ----------------------------------------------------------------------------
class RegionSelector:
    def __init__(self, root, shot, origin, on_done):
        self.shot, self.on_done = shot, on_done
        self.start = None
        w, h = shot.size
        ox, oy = origin

        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.geometry(f"{w}x{h}+{ox}+{oy}")  # 음수는 "+-1920" 형태여야 함

        self.canvas = tk.Canvas(self.top, width=w, height=h, highlightthickness=0, cursor="crosshair")
        self.canvas.pack()

        dim = ImageEnhance.Brightness(shot).enhance(0.45)
        self.dim_tk = ImageTk.PhotoImage(dim)
        self.canvas.create_image(0, 0, anchor="nw", image=self.dim_tk)
        self.bright_id = self.canvas.create_image(0, 0, anchor="nw", state="hidden")
        self.rect_id = self.canvas.create_rectangle(0, 0, 0, 0, outline="#FF9F43", width=2)
        self.label_id = self.canvas.create_text(0, 0, anchor="sw", fill="white", font=("Malgun Gothic", 10, "bold"))
        self.canvas.create_text(
            w // 2, 30, fill="white", font=("Malgun Gothic", 12, "bold"),
            text="드래그하여 영역 선택  |  Esc / 우클릭: 취소",
        )

        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Button-3>", lambda e: self.cancel())
        self.top.bind("<Escape>", lambda e: self.cancel())
        self.top.focus_force()
        self.canvas.focus_set()

    def press(self, e):
        self.start = (e.x, e.y)

    def drag(self, e):
        if not self.start:
            return
        l, t, r, b = norm_box(self.start, (e.x, e.y))
        self.canvas.coords(self.rect_id, l, t, r, b)
        if r - l > 1 and b - t > 1:
            self.bright_tk = ImageTk.PhotoImage(self.shot.crop((l, t, r, b)))
            self.canvas.itemconfig(self.bright_id, image=self.bright_tk, state="normal")
            self.canvas.coords(self.bright_id, l, t)
            self.canvas.tag_raise(self.rect_id)
        self.canvas.coords(self.label_id, l, max(t - 4, 14))
        self.canvas.itemconfig(self.label_id, text=f"{r - l} x {b - t}")

    def release(self, e):
        if not self.start:
            return
        l, t, r, b = [int(v) for v in norm_box(self.start, (e.x, e.y))]
        if r - l < 5 or b - t < 5:
            self.on_done(None)
        else:
            self.on_done(self.shot.crop((l, t, r, b)))

    def cancel(self):
        self.on_done(None)



# ----------------------------------------------------------------------------
# 디자인 (라이트 미니멀): 색상 / 아이콘 / 커스텀 위젯
# ----------------------------------------------------------------------------
T = dict(
    bg="#FFF8EE", card="#FFFFFF", line="#F0DFCB", text="#4A2A18", sub="#9A7656",
    accent="#E8A25A", accent_text="#B8661F", tint="#FFEFD9",
    primary="#F4B676", primary_h="#EFA55D", on_primary="#4A2A18",
    dis_bg="#F6EBDD", dis_fg="#CDB59C", warn="#B45309",
)
FONT = "Malgun Gothic" if IS_WIN else "DejaVu Sans"
UI = {"s": 1.0}  # DPI 배율

# 메인 창 레이아웃 (100% 배율 기준, 전체 폭 800px = 좌우 여백 26*2 + 368 + 20 + 360)
LEFT_W, GAP_W, RIGHT_W = 368, 20, 360
PV_W, PV_H = RIGHT_W, 292   # 미리보기 카드
STRIP_W = LEFT_W            # 최근 캡처 썸네일 줄

_HAM = {}


def hamster(which, size):
    """내장 햄스터 이미지("face"/"body")를 size px(DPI 반영)로 변환."""
    key = (which, size, UI["s"])
    if key not in _HAM:
        n = px(size)
        _HAM[key] = ImageTk.PhotoImage(assets.load(which).resize((n, n), Image.LANCZOS))
    return _HAM[key]


def px(n):
    return max(1, int(round(n * UI["s"])))


_ICONS = {}


def icon(name, color, size=18):
    """Pillow로 그린 선(line) 아이콘. 4배 크게 그린 뒤 줄여서 부드럽게."""
    key = (name, color, size, UI["s"])
    if key in _ICONS:
        return _ICONS[key]
    out = px(size)
    S = out * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    u = S / 22
    w = max(2, int(u * 1.7))
    col = hex_to_rgb(color) + (255,)

    def line(*pts):
        p = [(x * u, y * u) for x, y in pts]
        d.line(p, fill=col, width=w, joint="curve")
        r = w / 2
        for x, y in p:
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)

    def rrect(x1, y1, x2, y2, r):
        d.rounded_rectangle((x1 * u, y1 * u, x2 * u, y2 * u), radius=r * u, outline=col, width=w)

    if name == "region":
        line((3, 8), (3, 3), (8, 3))
        line((14, 3), (19, 3), (19, 8))
        line((3, 14), (3, 19), (8, 19))
        line((14, 19), (19, 19), (19, 14))
        d.ellipse((9.6 * u, 9.6 * u, 12.4 * u, 12.4 * u), fill=col)
    elif name == "monitor":
        rrect(3, 4, 19, 15, 2)
        line((11, 15), (11, 18))
        line((7, 18), (15, 18))
    elif name == "monitors":
        rrect(1.5, 5, 10.5, 14, 1.6)
        rrect(11.5, 5, 20.5, 14, 1.6)
        line((6, 14), (6, 17.5))
        line((16, 14), (16, 17.5))
        line((3.5, 17.5), (8.5, 17.5))
        line((13.5, 17.5), (18.5, 17.5))
    elif name == "window":
        rrect(3, 4, 19, 18, 2.2)
        line((3, 8.5), (19, 8.5))
        d.ellipse((5 * u, 5.6 * u, 6.6 * u, 7.2 * u), fill=col)
        d.ellipse((7.6 * u, 5.6 * u, 9.2 * u, 7.2 * u), fill=col)
    elif name == "edit":
        line((4, 18), (5, 14), (15, 4), (18, 7), (8, 17), (4, 18))
        line((13, 6), (16, 9))
    elif name == "copy":
        rrect(8, 8, 18, 18, 2)
        line((4, 14.5), (4, 6), (6, 4), (14.5, 4))
    elif name == "save":
        line((11, 3.5), (11, 13))
        line((6.5, 9), (11, 13.5), (15.5, 9))
        line((4, 14), (4, 18), (18, 18), (18, 14))
    elif name == "undo":
        d.arc((6 * u, 6.5 * u, 19 * u, 19.5 * u), start=-90, end=90, fill=col, width=w)
        line((12.5, 6.5), (6, 6.5))
        line((9, 3.5), (6, 6.5), (9, 9.5))
    elif name == "image":
        rrect(3, 4, 19, 18, 2.5)
        d.ellipse((6.4 * u, 7.4 * u, 9.6 * u, 10.6 * u), outline=col, width=w)
        line((3.5, 16), (8.5, 12.5), (12, 15.5), (15, 12.5), (18.5, 15.5))
    img = ImageTk.PhotoImage(im.resize((out, out), Image.LANCZOS))
    _ICONS[key] = img
    return img


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


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


class Tile(tk.Canvas):
    """아이콘 + 제목 + 단축키가 들어간 카드형 캡처 버튼."""

    def __init__(self, parent, icon_name, title, hint, command, w=170, h=92):
        super().__init__(parent, width=px(w), height=px(h), bg=T["bg"], highlightthickness=0, cursor="hand2")
        self.w, self.h, self.icon_name, self.title, self.hint, self.command = w, h, icon_name, title, hint, command
        self.bind("<Enter>", lambda e: self.draw(True))
        self.bind("<Leave>", lambda e: self.draw(False))
        self.bind("<ButtonRelease-1>", self.on_click)
        self.draw(False)

    def on_click(self, e):
        if 0 <= e.x <= px(self.w) and 0 <= e.y <= px(self.h):
            self.command()

    def draw(self, hover):
        self.delete("all")
        W, H = px(self.w), px(self.h)
        round_rect(self, 1, 1, W - 1, H - 1, px(14),
                   fill=T["tint"] if hover else T["card"],
                   outline=T["accent"] if hover else T["line"])
        self.create_image(W / 2, px(28), image=icon(self.icon_name, T["accent_text"] if hover else T["text"], 22))
        self.create_text(W / 2, px(55), text=self.title, font=(FONT, 10, "bold"), fill=T["text"])
        self.create_text(W / 2, px(73), text=self.hint, font=(FONT, 8), fill=T["accent_text"] if hover else T["sub"])


class Btn(tk.Canvas):
    """둥근 버튼 (primary / secondary), 아이콘 + 글자."""

    def __init__(self, parent, text, command, icon_name=None, kind="secondary", w=110, h=38, bg=None):
        super().__init__(parent, width=px(w), height=px(h), bg=bg or T["bg"], highlightthickness=0, cursor="hand2")
        self.w, self.h, self.text, self.command = w, h, text, command
        self.icon_name, self.kind = icon_name, kind
        self.enabled, self.hover = True, False
        self.font = tkfont.Font(family=FONT, size=10, weight="bold")
        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))
        self.bind("<ButtonRelease-1>", self.on_click)
        self.draw()

    def set_hover(self, v):
        self.hover = v
        self.draw()

    def set_enabled(self, on):
        self.enabled = on
        self.config(cursor="hand2" if on else "arrow")
        self.draw()

    def on_click(self, e):
        if self.enabled and 0 <= e.x <= px(self.w) and 0 <= e.y <= px(self.h):
            self.command()

    def draw(self):
        self.delete("all")
        W, H = px(self.w), px(self.h)
        hv = self.hover and self.enabled
        if not self.enabled:
            fill, outline, fg = T["dis_bg"], T["dis_bg"], T["dis_fg"]
        elif self.kind == "primary":
            fill = T["primary_h"] if hv else T["primary"]
            outline, fg = fill, T["on_primary"]
        else:
            fill = T["tint"] if hv else T["card"]
            outline = T["accent"] if hv else T["line"]
            fg = T["accent_text"] if hv else T["text"]
        round_rect(self, 1, 1, W - 1, H - 1, px(10), fill=fill, outline=outline)
        ic = icon(self.icon_name, fg, 16) if self.icon_name else None
        tw = self.font.measure(self.text)
        gap, isz = px(6), px(16)
        x = (W - (tw + (isz + gap if ic else 0))) / 2
        if ic:
            self.create_image(x, H / 2, image=ic, anchor="w")
            x += isz + gap
        self.create_text(x, H / 2, text=self.text, anchor="w", font=self.font, fill=fg)


class Stepper(tk.Frame):
    """지연 시간 − 0초 + 컨트롤."""

    def __init__(self, parent, var, lo=0, hi=30):
        super().__init__(parent, bg=T["card"], highlightbackground=T["line"], highlightthickness=1)
        self.var, self.lo, self.hi = var, lo, hi
        mk = lambda t, cmd: self._lbl(t, cmd)
        mk("−", lambda: self.step(-1)).pack(side="left")
        # 라벨 폭은 '0' 글자 기준 개수라 한글이 잘린다 -> 가장 긴 문구를 실제로 재서 폭을 정한다
        f = tkfont.Font(family=FONT, size=9, weight="bold")
        n = math.ceil(max(f.measure(t) for t in ("지연 없음", "지연 30초")) / f.measure("0")) + 2
        self.val = tk.Label(self, bg=T["card"], fg=T["text"], font=(FONT, 9, "bold"), width=n)
        self.val.pack(side="left")
        mk("+", lambda: self.step(1)).pack(side="left")
        var.trace_add("write", lambda *a: self.refresh())
        self.refresh()

    def _lbl(self, text, cmd):
        l = tk.Label(self, text=text, bg=T["card"], fg=T["sub"], font=(FONT, 11), width=2, cursor="hand2")
        l.bind("<Button-1>", lambda e: cmd())
        l.bind("<Enter>", lambda e: l.config(fg=T["accent_text"]))
        l.bind("<Leave>", lambda e: l.config(fg=T["sub"]))
        return l

    def step(self, d):
        try:
            v = int(self.var.get())
        except (tk.TclError, ValueError):
            v = 0
        self.var.set(min(self.hi, max(self.lo, v + d)))

    def refresh(self):
        try:
            v = int(self.var.get())
        except (tk.TclError, ValueError):
            v = 0
        self.val.config(text=f"지연 {v}초" if v else "지연 없음")


class InfoBtn(tk.Canvas):
    """헤더 오른쪽의 둥근 ⓘ 버튼."""

    def __init__(self, parent, command):
        s = px(28)
        super().__init__(parent, width=s, height=s, bg=T["bg"], highlightthickness=0, cursor="hand2")
        self.s, self.command = s, command
        self.bind("<Enter>", lambda e: self.draw(True))
        self.bind("<Leave>", lambda e: self.draw(False))
        self.bind("<ButtonRelease-1>", lambda e: self.command())
        self.draw(False)

    def draw(self, hover):
        self.delete("all")
        s = self.s
        self.create_oval(2, 2, s - 2, s - 2, fill=T["tint"] if hover else T["card"],
                         outline=T["accent"] if hover else T["line"], width=2)
        self.create_text(s / 2, s / 2, text="i", font=("Georgia", 12, "italic bold"),
                         fill=T["accent_text"] if hover else T["text"])


# ----------------------------------------------------------------------------
# 편집기
# ----------------------------------------------------------------------------
TOOLS = [
    ("pen", "펜"), ("highlight", "형광펜"), ("line", "선"), ("arrow", "화살표"),
    ("rect", "사각형"), ("ellipse", "원"), ("text", "텍스트"), ("mosaic", "모자이크"),
]
COLORS = ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#0a84ff", "#af52de", "#000000", "#ffffff"]


class Editor:
    def __init__(self, root, image, on_close=None):
        self.root = root
        self.on_close = on_close
        self.img = image.convert("RGBA")
        self.history = []
        self.tool = tk.StringVar(value="pen")
        self.width = tk.IntVar(value=4)
        self.color = "#ff3b30"
        self.pts = []
        self.preview = None

        self.win = tk.Toplevel(root)
        self.win.title("햄찌캡처 편집기")
        self.win.configure(bg=T["bg"])
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.scale = min(1.0, (sw * 0.9) / self.img.width, (sh * 0.75) / self.img.height)

        self.build_toolbar()
        self.canvas = tk.Canvas(self.win, highlightthickness=0, bg=T["bg"], cursor="crosshair")
        self.canvas.pack(expand=True, padx=px(14), pady=px(14))
        self.status = tk.Label(self.win, anchor="w", bg=T["bg"], fg=T["sub"], font=(FONT, 9), padx=px(12), pady=px(5))
        self.status.pack(fill="x")

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.win.bind("<Control-z>", lambda e: self.undo())
        self.win.bind("<Control-c>", lambda e: self.copy())
        self.win.bind("<Control-s>", lambda e: self.save())
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        self.refresh()
        self.win.update_idletasks()
        self.win.minsize(self.bar.winfo_reqwidth(), 240)
        self.win.focus_force()
        if IS_WIN:  # 편집기를 맨 앞으로
            self.win.attributes("-topmost", True)
            self.win.after(300, lambda: self.win.attributes("-topmost", False))

    def close(self):
        if self.on_close:
            self.on_close(self.img)
        self.win.destroy()

    # --- UI ---
    def build_toolbar(self):
        bar = tk.Frame(self.win, bg=T["card"], padx=px(12), pady=px(8))
        bar.pack(fill="x")
        tk.Frame(self.win, bg=T["line"], height=1).pack(fill="x")
        self.bar = bar

        # 도구: 세그먼트 컨트롤
        seg = tk.Frame(bar, bg=T["bg"], padx=px(2), pady=px(2))
        seg.pack(side="left")
        self.tool_lbls = {}
        for key, label in TOOLS:
            l = tk.Label(seg, text=label, font=(FONT, 9), padx=px(9), pady=px(4), cursor="hand2",
                         bg=T["bg"], fg=T["sub"])
            l.pack(side="left")
            l.bind("<Button-1>", lambda e, k=key: self.select_tool(k))
            self.tool_lbls[key] = l
        self.select_tool("pen")

        tk.Frame(bar, bg=T["line"], width=1).pack(side="left", fill="y", padx=px(10))

        # 색상
        self.sw_cv = {}
        for c in COLORS + ["custom"]:
            cv = tk.Canvas(bar, width=px(24), height=px(24), bg=T["card"], highlightthickness=0, cursor="hand2")
            cv.pack(side="left", padx=px(1))
            cv.bind("<Button-1>", (lambda e: self.pick_color()) if c == "custom" else (lambda e, c=c: self.set_color(c)))
            self.sw_cv[c] = cv
        self.redraw_swatches()

        tk.Frame(bar, bg=T["line"], width=1).pack(side="left", fill="y", padx=px(10))

        # 굵기
        tk.Label(bar, text="굵기", bg=T["card"], fg=T["sub"], font=(FONT, 9)).pack(side="left")
        tk.Scale(bar, from_=1, to=20, orient="horizontal", variable=self.width, length=px(90), showvalue=False,
                 bg=T["card"], troughcolor=T["line"], highlightthickness=0, bd=0, sliderrelief="flat",
                 activebackground=T["accent"], sliderlength=px(14), width=px(8)).pack(side="left", padx=px(4))

        # 우측 버튼
        Btn(bar, "저장", self.save, "save", "primary", 84, 32, T["card"]).pack(side="right", padx=(px(6), 0))
        Btn(bar, "복사", self.copy, "copy", "secondary", 84, 32, T["card"]).pack(side="right", padx=px(3))
        Btn(bar, "취소", self.undo, "undo", "secondary", 84, 32, T["card"]).pack(side="right", padx=px(3))

    def select_tool(self, key):
        self.tool.set(key)
        for k, l in self.tool_lbls.items():
            l.config(bg=T["card"] if k == key else T["bg"], fg=T["accent_text"] if k == key else T["sub"])

    def redraw_swatches(self):
        for c, cv in self.sw_cv.items():
            cv.delete("all")
            W = px(24)
            if c == "custom":
                custom = self.color not in COLORS
                if custom:
                    cv.create_oval(px(1), px(1), W - px(1), W - px(1), outline=T["accent"], width=2)
                    cv.create_oval(px(5), px(5), W - px(5), W - px(5), fill=self.color, outline=T["line"])
                else:
                    cv.create_oval(px(4), px(4), W - px(4), W - px(4), outline=T["dis_fg"], dash=(2, 2))
                    cv.create_text(W / 2, W / 2, text="+", fill=T["sub"], font=(FONT, 9))
            elif c == self.color:
                cv.create_oval(px(1), px(1), W - px(1), W - px(1), outline=T["accent"], width=2)
                cv.create_oval(px(5), px(5), W - px(5), W - px(5), fill=c, outline=T["line"])
            else:
                cv.create_oval(px(4), px(4), W - px(4), W - px(4), fill=c, outline=T["line"])

    def set_color(self, c):
        self.color = c
        self.redraw_swatches()

    def pick_color(self):
        c = colorchooser.askcolor(color=self.color, parent=self.win)[1]
        if c:
            self.set_color(c)

    def refresh(self):
        w, h = int(self.img.width * self.scale), int(self.img.height * self.scale)
        disp = self.img.resize((w, h), Image.LANCZOS) if self.scale != 1.0 else self.img
        self.tk_img = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.config(width=w, height=h)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)
        self.status.config(text=f" {self.img.width} x {self.img.height}px   |   Ctrl+Z 취소 · Ctrl+C 복사 · Ctrl+S 저장 · Esc 닫기")

    def commit(self, new_img):
        self.history.append(self.img)
        self.img = new_img
        self.refresh()

    def undo(self):
        if self.history:
            self.img = self.history.pop()
            self.refresh()

    # --- 마우스 ---
    def to_img(self, e):
        return (e.x / self.scale, e.y / self.scale)

    def on_press(self, e):
        self.pts = [self.to_img(e)]
        self.cpts = [(e.x, e.y)]
        if self.tool.get() == "text":
            text = simpledialog.askstring("텍스트", "입력할 내용:", parent=self.win)
            if text:
                self.commit(apply_text(self.img, self.pts[0], text, self.color, self.width.get()))
            self.pts = []

    def on_drag(self, e):
        if not self.pts:
            return
        tool = self.tool.get()
        self.canvas.delete("preview")
        self.cpts.append((e.x, e.y))
        self.pts.append(self.to_img(e))
        c0, c1 = self.cpts[0], self.cpts[-1]
        w = max(1, int(self.width.get() * self.scale))
        if tool == "pen":
            flat = [v for p in self.cpts for v in p]
            if len(flat) >= 4:
                self.canvas.create_line(*flat, fill=self.color, width=w, capstyle="round", joinstyle="round", tags="preview")
        elif tool in ("line", "arrow"):
            self.canvas.create_line(*c0, *c1, fill=self.color, width=w, arrow="last" if tool == "arrow" else None, tags="preview")
        elif tool == "ellipse":
            self.canvas.create_oval(*c0, *c1, outline=self.color, width=w, tags="preview")
        elif tool == "rect":
            self.canvas.create_rectangle(*c0, *c1, outline=self.color, width=w, tags="preview")
        elif tool in ("highlight", "mosaic"):
            self.canvas.create_rectangle(*c0, *c1, outline=self.color, dash=(4, 3), width=2, tags="preview")

    def on_release(self, e):
        if not self.pts:
            return
        tool = self.tool.get()
        self.canvas.delete("preview")
        if len(self.pts) > 1 or tool == "pen":
            self.commit(apply_shape(self.img, tool, self.pts, self.color, self.width.get()))
        self.pts = []

    # --- 출력 ---
    def copy(self):
        try:
            copy_image_to_clipboard(self.img)
            self.status.config(text=" 클립보드에 복사했어요")
        except Exception as ex:
            messagebox.showerror("복사 실패", str(ex), parent=self.win)

    def save(self):
        path = filedialog.asksaveasfilename(
            parent=self.win, defaultextension=".png", initialdir=default_save_dir(),
            initialfile=timestamp_name(), filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
        )
        if not path:
            return
        try:
            save_image(self.img, path)
        except Exception as ex:
            messagebox.showerror("저장 실패", str(ex), parent=self.win)
            return
        self.status.config(text=f" 저장했어요: {path}")


# ----------------------------------------------------------------------------
# 메인 앱 + 전역 단축키
# ----------------------------------------------------------------------------
MAX_HISTORY = 5  # 최근 캡처 보관 개수 (실행 중에만 유지)

HOTKEYS = {1: ("region", "A"), 2: ("full", "F"), 3: ("window", "W"), 4: ("monitor", "M")}


def hotkey_loop(q):
    """RegisterHotKey 메시지 루프 (별도 스레드)."""
    u = ctypes.windll.user32
    MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT, WM_HOTKEY = 0x2, 0x4, 0x4000, 0x0312
    failed = []
    for hid, (_, key) in HOTKEYS.items():
        if not u.RegisterHotKey(None, hid, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, ord(key)):
            failed.append(key)
    if failed:
        q.put(("failed", failed))
    msg = wintypes.MSG()
    while u.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY and msg.wParam in HOTKEYS:
            q.put((HOTKEYS[msg.wParam][0], None))


class App:
    def __init__(self):
        self.root = tk.Tk()
        UI["s"] = self.root.tk.call("tk", "scaling") / (96 / 72)  # DPI 배율
        self.root.title("햄찌캡처")
        self.root.configure(bg=T["bg"])
        self.root.resizable(False, False)
        # 창/작업표시줄 아이콘 (햄스터 얼굴)
        self.app_icon = ImageTk.PhotoImage(assets.load("face").resize((64, 64), Image.LANCZOS))
        self.root.iconphoto(True, self.app_icon)
        self.busy = False
        self.delay = tk.IntVar(value=0)
        self.q = queue.Queue()
        self.history = []  # 최근 캡처 목록 (최신이 앞), 최대 MAX_HISTORY개
        self.sel = None    # 현재 선택된 항목 번호

        f = tk.Frame(self.root, bg=T["bg"], padx=px(26), pady=px(18))
        f.pack()

        # 헤더: 햄스터 + 이름 / 지연 시간
        head = tk.Frame(f, bg=T["bg"])
        head.pack(fill="x")
        tk.Label(head, image=hamster("face", 44), bg=T["bg"]).pack(side="left", padx=(0, px(10)))
        titles = tk.Frame(head, bg=T["bg"])
        titles.pack(side="left")
        tk.Label(titles, text="햄찌캡처", bg=T["bg"], fg=T["text"], font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(titles, text="무엇을 담을까요?", bg=T["bg"], fg=T["sub"], font=(FONT, 9)).pack(anchor="w")
        InfoBtn(head, self.show_about).pack(side="right", padx=(px(10), 0))
        Stepper(head, self.delay).pack(side="right")

        cols = tk.Frame(f, bg=T["bg"])
        cols.pack(fill="x", pady=(px(16), 0))
        left = tk.Frame(cols, bg=T["bg"], width=px(LEFT_W))
        left.pack(side="left", anchor="n")
        right = tk.Frame(cols, bg=T["bg"], width=px(RIGHT_W))
        right.pack(side="left", anchor="n", padx=(px(GAP_W), 0))

        # --- 왼쪽: 캡처 타일 2 x 2 + 최근 캡처 ---
        grid = tk.Frame(left, bg=T["bg"])
        grid.pack()
        tiles = [
            ("region", "영역 선택", "Ctrl+Shift+A", "region"),
            ("monitor", "현재 모니터", "Ctrl+Shift+M", "monitor"),
            ("window", "활성 창", "Ctrl+Shift+W", "window"),
            ("monitors", "모든 모니터", "Ctrl+Shift+F", "full"),
        ]
        for i, (ic, title, hint, mode) in enumerate(tiles):
            Tile(grid, ic, title, hint, lambda m=mode: self.start(m), w=176).grid(
                row=i // 2, column=i % 2, padx=px(4), pady=px(4))
        self.build_strip(left)
        self.note = tk.Label(left, text="단축키는 창을 최소화해도 동작해요", bg=T["bg"], fg=T["sub"],
                             font=(FONT, 8), wraplength=px(LEFT_W), justify="left", anchor="w")
        self.note.pack(fill="x", pady=(px(16), 0))

        # --- 오른쪽: 미리보기 + 정보 + 버튼 ---
        self.pv = tk.Canvas(right, width=px(PV_W), height=px(PV_H), bg=T["bg"], highlightthickness=0)
        self.pv.pack()
        self.info = tk.Label(right, text="", bg=T["bg"], fg=T["sub"], font=(FONT, 9), anchor="w")
        self.info.pack(fill="x", pady=(px(10), px(8)))

        brow = tk.Frame(right, bg=T["bg"])
        brow.pack(fill="x")
        self.action_btns = [
            Btn(brow, "편집", self.edit_last, "edit", "primary", 116, 40),
            Btn(brow, "복사", self.copy_last, "copy", "secondary", 116, 40),
            Btn(brow, "저장", self.save_last, "save", "secondary", 116, 40),
        ]
        for i, b_ in enumerate(self.action_btns):
            b_.pack(side="left", expand=True, padx=(0 if i == 0 else px(4), 0))
            b_.set_enabled(False)
        self.refresh_all()

        if IS_WIN:
            threading.Thread(target=hotkey_loop, args=(self.q,), daemon=True).start()
        self.root.after(100, self.poll)

    def show_about(self):
        """제작 정보 창."""
        if getattr(self, "about", None) is not None and self.about.winfo_exists():
            self.about.lift()
            return
        top = self.about = tk.Toplevel(self.root)
        top.title(f"{APP_NAME} 정보")
        top.configure(bg=T["bg"])
        top.resizable(False, False)
        top.transient(self.root)
        body = tk.Frame(top, bg=T["bg"], padx=px(28), pady=px(22))
        body.pack()
        tk.Label(body, image=hamster("body", 120), bg=T["bg"]).pack()
        tk.Label(body, text=APP_NAME, bg=T["bg"], fg=T["text"], font=(FONT, 16, "bold")).pack(pady=(px(6), 0))
        tk.Label(body, text=f"버전 {VERSION}", bg=T["bg"], fg=T["sub"], font=(FONT, 9)).pack()

        rows = [("제작", AUTHOR), ("도움", "Claude (Anthropic)"), ("이미지", "AI 생성"),
                ("라이선스", "MIT License (소스 코드)")]
        W, rh = px(300), px(32)
        H = rh * len(rows) + px(12)
        cv = tk.Canvas(body, width=W, height=H, bg=T["bg"], highlightthickness=0)
        cv.pack(pady=(px(16), 0))
        round_rect(cv, 1, 1, W - 1, H - 1, px(12), fill=T["card"], outline=T["line"])
        for i, (k, v) in enumerate(rows):
            y = px(6) + rh * i + rh / 2
            if i:
                cv.create_line(px(14), y - rh / 2, W - px(14), y - rh / 2, fill=T["line"])
            cv.create_text(px(16), y, text=k, anchor="w", fill=T["sub"], font=(FONT, 9))
            cv.create_text(px(78), y, text=v, anchor="w", fill=T["text"], font=(FONT, 9, "bold"))

        Btn(body, "닫기", top.destroy, None, "primary", 140, 38).pack(pady=(px(16), 0))
        top.bind("<Escape>", lambda e: top.destroy())
        top.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - top.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - top.winfo_height()) // 2
        top.geometry(f"+{max(0, x)}+{max(0, y)}")
        top.focus_force()

    def poll(self):
        try:
            while True:
                kind, extra = self.q.get_nowait()
                if kind == "failed":
                    self.note.config(fg=T["warn"], text="Ctrl+Shift+" + ", ".join(extra) + " 단축키를 쓸 수 없어요. 이미 실행 중인 캡처 프로그램이 있다면 먼저 종료해 주세요.")
                else:
                    self.start(kind, hotkey=True)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def start(self, mode, hotkey=False):
        if self.busy:
            return
        self.busy = True
        try:
            delay = max(0, int(self.delay.get()))
        except (tk.TclError, ValueError):
            delay = 0
        if hotkey and mode == "window" and own_window_active():
            # 햄찌캡처 자신의 창(메인/편집기/정보)이 활성 상태면 숨기지 않고 그대로 캡처
            self.root.after(150 + delay * 1000, lambda: self.capture(mode))
            return
        self.root.withdraw()
        self.root.after(250 + delay * 1000, lambda: self.capture(mode))

    def capture(self, mode):
        try:
            shot, origin = grab_screen()
            mons = get_monitors() or [(origin[0], origin[1], origin[0] + shot.width, origin[1] + shot.height)]
            if mode == "full":
                self.finish(shot)
            elif mode == "monitor":
                px, py = self.root.winfo_pointerxy()
                l, t, r, b = next((m for m in mons if m[0] <= px < m[2] and m[1] <= py < m[3]), mons[0])
                self.finish(shot.crop((l - origin[0], t - origin[1], r - origin[0], b - origin[1])))
            elif mode == "window":
                rect = active_window_rect()
                if not rect:
                    raise RuntimeError("활성 창을 찾지 못했습니다.")
                l, t, r, b = rect
                box = (max(0, l - origin[0]), max(0, t - origin[1]),
                       min(shot.width, r - origin[0]), min(shot.height, b - origin[1]))
                self.finish(shot.crop(box))
            else:
                self.select_region(shot, origin, mons)
        except Exception as ex:
            self.busy = False
            self.root.deiconify()
            messagebox.showerror("캡처 실패", str(ex))

    def select_region(self, shot, origin, mons):
        """모니터마다 오버레이를 하나씩 띄운다 (한 모니터 안에서 드래그)."""
        overlays = []

        def done(img):
            for o in overlays:
                try:
                    o.top.destroy()
                except tk.TclError:
                    pass
            self.finish(img)

        px, py = self.root.winfo_pointerxy()
        focus = None
        for (l, t, r, b) in mons:
            sub = shot.crop((l - origin[0], t - origin[1], r - origin[0], b - origin[1]))
            o = RegionSelector(self.root, sub, (l, t), done)
            overlays.append(o)
            if l <= px < r and t <= py < b:
                focus = o
        if focus:
            focus.top.focus_force()
            focus.canvas.focus_set()

    def finish(self, image):
        self.busy = False
        self.root.deiconify()
        self.root.lift()
        if image is not None:
            self.add_capture(image)  # 편집기는 자동으로 열지 않고 미리보기만 표시

    def show_preview(self):
        cv = self.pv
        cv.delete("all")
        W, H = px(PV_W), px(PV_H)
        round_rect(cv, 1, 1, W - 1, H - 1, px(14), fill=T["card"], outline=T["line"])
        if self.last is None:
            cv.create_image(W / 2, H / 2 - px(22), image=hamster("body", 130))
            cv.create_text(W / 2, H / 2 + px(70), text="캡처하면 여기에 표시돼요", fill=T["sub"], font=(FONT, 9))
        else:
            pad = px(10)
            thumb = self.last.convert("RGB")
            thumb.thumbnail((W - 2 * pad, H - 2 * pad), Image.LANCZOS)
            self.pv_img = ImageTk.PhotoImage(rounded_image(thumb, px(8)))
            cv.create_image(W / 2, H / 2, image=self.pv_img)

    # --- 최근 캡처 목록 ---
    @property
    def last(self):
        """현재 선택된 캡처 이미지 (없으면 None)."""
        if self.sel is not None and 0 <= self.sel < len(self.history):
            return self.history[self.sel]["img"]
        return None

    def build_strip(self, parent):
        hd = tk.Frame(parent, bg=T["bg"])
        hd.pack(fill="x", pady=(px(14), px(4)))
        tk.Label(hd, text="최근 캡처", bg=T["bg"], fg=T["sub"], font=(FONT, 9, "bold")).pack(side="left")
        tk.Label(hd, text=f"{MAX_HISTORY}개까지 보관 · 클릭해서 다시 열기", bg=T["bg"], fg=T["sub"],
                 font=(FONT, 8)).pack(side="right")
        self.strip = tk.Canvas(parent, width=px(STRIP_W), height=px(54), bg=T["bg"], highlightthickness=0)
        self.strip.pack()
        self.strip.bind("<Button-1>", self.on_strip_click)
        self.strip.bind("<Motion>", lambda e: self.strip.config(
            cursor="hand2" if self.slot_at(e.x) is not None else "arrow"))

    def slot_box(self, i):
        W, gap = px(STRIP_W), px(6)
        w = (W - gap * (MAX_HISTORY - 1)) / MAX_HISTORY
        return i * (w + gap), w

    def slot_at(self, x):
        for i in range(len(self.history)):
            x0, w = self.slot_box(i)
            if x0 <= x <= x0 + w:
                return i
        return None

    def on_strip_click(self, e):
        i = self.slot_at(e.x)
        if i is not None:
            self.sel = i
            self.refresh_all()

    def draw_strip(self):
        cv, H = self.strip, px(54)
        cv.delete("all")
        self.strip_imgs = []
        for i in range(MAX_HISTORY):
            x0, w = self.slot_box(i)
            x1 = x0 + w
            if i >= len(self.history):  # 빈 칸
                round_rect(cv, x0 + 1, px(3), x1 - 1, H - px(3), px(10), fill=T["bg"], outline=T["line"], dash=(3, 3))
                continue
            sel = i == self.sel
            round_rect(cv, x0 + 1, px(3), x1 - 1, H - px(3), px(10), fill=T["card"],
                       outline=T["accent"] if sel else T["line"], width=2 if sel else 1)
            th = ImageOps.fit(self.history[i]["img"].convert("RGB"),
                              (max(8, int(w) - px(10)), H - px(14)), Image.LANCZOS)
            ph = ImageTk.PhotoImage(rounded_image(th, px(6)))
            self.strip_imgs.append(ph)
            cv.create_image((x0 + x1) / 2, H / 2, image=ph)
            if i == 0:  # 가장 최근
                round_rect(cv, x1 - px(32), H - px(21), x1 - px(6), H - px(8), px(5), fill=T["text"], outline=T["text"])
                cv.create_text(x1 - px(19), H - px(14.5), text="방금", fill="#FFFFFF", font=(FONT, 7, "bold"))

    def refresh_all(self):
        self.show_preview()
        self.draw_strip()
        img = self.last
        if img is not None:
            self.info.config(text=f"{self.sel + 1}번째 캡처 · {img.width} × {img.height} px")
        for b in self.action_btns:
            b.set_enabled(img is not None)

    def add_capture(self, image):
        self.history.insert(0, {"img": image.convert("RGBA")})
        del self.history[MAX_HISTORY:]
        self.sel = 0
        self.refresh_all()

    def update_entry(self, entry, image):
        """편집기에서 돌아왔을 때 해당 항목을 편집본으로 교체."""
        entry["img"] = image.convert("RGBA")
        self.refresh_all()

    def edit_last(self):
        if self.last is not None:
            entry = self.history[self.sel]
            Editor(self.root, entry["img"], on_close=lambda img, e=entry: self.update_entry(e, img))

    def copy_last(self):
        if self.last is None:
            return
        try:
            copy_image_to_clipboard(self.last)
            self.info.config(text="클립보드에 복사했어요")
        except Exception as ex:
            messagebox.showerror("복사 실패", str(ex))

    def save_last(self):
        if self.last is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", initialdir=default_save_dir(),
            initialfile=timestamp_name(), filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
        )
        if path:
            try:
                save_image(self.last, path)
            except Exception as ex:
                messagebox.showerror("저장 실패", str(ex))
                return
            self.info.config(text=f"저장했어요: {os.path.basename(path)}")

    def run(self):
        self.root.mainloop()


def already_running():
    """같은 프로그램이 이미 켜져 있으면 True (단축키 충돌 방지)."""
    if not IS_WIN:
        return False
    ctypes.windll.kernel32.CreateMutexW(None, False, "HamzziCaptureSingleton")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if IS_WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hamzzi.Capture")
        except Exception:
            pass
    if already_running():
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo("햄찌캡처", "이미 실행 중입니다. 작업 표시줄에서 기존 창을 확인해 주세요.")
        sys.exit(0)
    App().run()
