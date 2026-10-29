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
from i18n import detect_lang, set_lang, tr
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageGrab, ImageOps, ImageTk

IS_WIN = sys.platform == "win32"

# 앱 정보 (정보 창에 표시)
VERSION = "1.1.0"
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
        raise RuntimeError(tr("err_win_only"))
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
        raise RuntimeError(tr("err_clip_open"))
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            raise RuntimeError(tr("err_mem_alloc"))
        p = kernel32.GlobalLock(h)
        if not p:
            kernel32.GlobalFree(h)
            raise RuntimeError(tr("err_mem_lock"))
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_DIB, h):
            kernel32.GlobalFree(h)  # 클립보드가 가져가지 않았으므로 직접 해제
            raise RuntimeError(tr("err_clip_set"))
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
        raise ValueError(tr("err_ext"))


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
            text=tr("region_hint"),
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
FONT_KO = "Malgun Gothic" if IS_WIN else "DejaVu Sans"
FONT_EN = FONT_KO  # 영문도 맑은 고딕으로 통일 (한글이 섞여도 글꼴이 달라 보이지 않게)
FONT = FONT_KO


def apply_language(lang):
    """언어와 글꼴을 함께 바꾼다 (위젯은 만들 때의 FONT를 쓰므로 화면을 다시 만들어야 반영된다)."""
    global FONT
    set_lang(lang)
    FONT = FONT_KO if lang == "ko" else FONT_EN
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
        longest = (tr("delay_none"), tr("delay_n", n=30))
        n = math.ceil(max(f.measure(txt) for txt in longest) / f.measure("0")) + 2
        self.val = tk.Label(self, bg=T["card"], fg=T["text"], font=(FONT, 9, "bold"), width=n)
        self.val.pack(side="left")
        mk("+", lambda: self.step(1)).pack(side="left")
        self._tid = var.trace_add("write", lambda *a: self.refresh())
        # 화면을 다시 만들 때 낡은 위젯이 변수 변경을 계속 듣지 않도록 해제
        self.bind("<Destroy>", lambda e: var.trace_remove("write", self._tid) if e.widget is self else None)
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
        try:
            self.val.config(text=tr("delay_n", n=v) if v else tr("delay_none"))
        except tk.TclError:  # 위젯이 이미 사라진 경우
            pass


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
    ("pen", "tool_pen"), ("highlight", "tool_highlight"), ("line", "tool_line"), ("arrow", "tool_arrow"),
    ("rect", "tool_rect"), ("ellipse", "tool_ellipse"), ("text", "tool_text"), ("mosaic", "tool_mosaic"),
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
        self.win.title(tr("editor_title"))
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
            l = tk.Label(seg, text=tr(label), font=(FONT, 9), padx=px(9), pady=px(4), cursor="hand2",
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
        tk.Label(bar, text=tr("width_label"), bg=T["card"], fg=T["sub"], font=(FONT, 9)).pack(side="left")
        tk.Scale(bar, from_=1, to=20, orient="horizontal", variable=self.width, length=px(90), showvalue=False,
                 bg=T["card"], troughcolor=T["line"], highlightthickness=0, bd=0, sliderrelief="flat",
                 activebackground=T["accent"], sliderlength=px(14), width=px(8)).pack(side="left", padx=px(4))

        # 우측 버튼
        Btn(bar, tr("btn_save"), self.save, "save", "primary", 84, 32, T["card"]).pack(side="right", padx=(px(6), 0))
        Btn(bar, tr("btn_copy"), self.copy, "copy", "secondary", 84, 32, T["card"]).pack(side="right", padx=px(3))
        Btn(bar, tr("btn_undo"), self.undo, "undo", "secondary", 84, 32, T["card"]).pack(side="right", padx=px(3))

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
        self.status.config(text=tr("editor_status", w=self.img.width, h=self.img.height))

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
            text = simpledialog.askstring(tr("text_dialog_title"), tr("text_dialog_prompt"), parent=self.win)
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
            self.status.config(text=tr("editor_copied"))
        except Exception as ex:
            messagebox.showerror(tr("err_copy_title"), str(ex), parent=self.win)

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
            messagebox.showerror(tr("err_save_title"), str(ex), parent=self.win)
            return
        self.status.config(text=tr("editor_saved", path=path))


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

        self.lang = detect_lang()
        apply_language(self.lang)
        self.about = None
        self.hotkey_failed = None
        self.build_ui()

        if IS_WIN:
            threading.Thread(target=hotkey_loop, args=(self.q,), daemon=True).start()
        self.root.after(100, self.poll)

    def build_ui(self):
        """메인 창 화면을 (다시) 만든다. 언어를 바꾸면 이 함수를 다시 호출한다."""
        old = getattr(self, "main_frame", None)
        if old is not None:
            old.destroy()
        self.x_hover = None
        self.root.title(tr("app_name"))
        f = tk.Frame(self.root, bg=T["bg"], padx=px(26), pady=px(18))
        f.pack()
        self.main_frame = f

        # 헤더: 햄스터 + 이름 / 지연 시간
        head = tk.Frame(f, bg=T["bg"])
        head.pack(fill="x")
        tk.Label(head, image=hamster("face", 44), bg=T["bg"]).pack(side="left", padx=(0, px(10)))
        titles = tk.Frame(head, bg=T["bg"])
        titles.pack(side="left")
        tk.Label(titles, text=tr("app_name"), bg=T["bg"], fg=T["text"], font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(titles, text=tr("subtitle"), bg=T["bg"], fg=T["sub"], font=(FONT, 9)).pack(anchor="w")
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
            ("region", tr("tile_region"), "Ctrl+Shift+A", "region"),
            ("monitor", tr("tile_monitor"), "Ctrl+Shift+M", "monitor"),
            ("window", tr("tile_window"), "Ctrl+Shift+W", "window"),
            ("monitors", tr("tile_all"), "Ctrl+Shift+F", "full"),
        ]
        for i, (ic, title, hint, mode) in enumerate(tiles):
            Tile(grid, ic, title, hint, lambda m=mode: self.start(m), w=176).grid(
                row=i // 2, column=i % 2, padx=px(4), pady=px(4))
        self.build_strip(left)
        self.note = tk.Label(left, text=tr("note_hotkeys"), bg=T["bg"], fg=T["sub"],
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
            Btn(brow, tr("btn_edit"), self.edit_last, "edit", "primary", 116, 40),
            Btn(brow, tr("btn_copy"), self.copy_last, "copy", "secondary", 116, 40),
            Btn(brow, tr("btn_save"), self.save_last, "save", "secondary", 116, 40),
        ]
        for i, b_ in enumerate(self.action_btns):
            b_.pack(side="left", expand=True, padx=(0 if i == 0 else px(4), 0))
            b_.set_enabled(False)
        self.update_note()
        self.refresh_all()

    def update_note(self):
        """하단 안내 문구. 단축키 등록에 실패했다면 경고를 보여준다."""
        if self.hotkey_failed:
            keys = "Ctrl+Shift+" + ", ".join(self.hotkey_failed)
            self.note.config(fg=T["warn"], text=tr("hotkey_failed", keys=keys))

    def set_language(self, lang):
        """언어 전환: 화면을 새 언어로 다시 만든다 (캡처 기록은 그대로)."""
        if lang == self.lang:
            return
        pos = None
        if self.about is not None and self.about.winfo_exists():
            pos = (self.about.winfo_x(), self.about.winfo_y())
            self.about.destroy()
        self.lang = lang
        apply_language(lang)
        self.build_ui()
        if pos is not None:
            self.show_about(pos)

    def show_about(self, pos=None):
        """제작 정보 창. pos=(x, y)를 주면 그 위치에 연다(언어 전환 직후)."""
        if self.about is not None and self.about.winfo_exists():
            self.about.lift()
            return
        top = self.about = tk.Toplevel(self.root)
        top.title(tr("about_title", app=tr("app_name")))
        top.configure(bg=T["bg"])
        top.resizable(False, False)
        top.transient(self.root)
        body = tk.Frame(top, bg=T["bg"], padx=px(28), pady=px(22))
        body.pack()
        tk.Label(body, image=hamster("body", 120), bg=T["bg"]).pack()
        tk.Label(body, text=tr("app_name"), bg=T["bg"], fg=T["text"], font=(FONT, 16, "bold")).pack(pady=(px(6), 0))
        tk.Label(body, text=tr("about_version", v=VERSION), bg=T["bg"], fg=T["sub"], font=(FONT, 9)).pack()

        rows = [(tr("about_author"), AUTHOR), (tr("about_help"), "Claude (Anthropic)"),
                (tr("about_images"), tr("about_ai")), (tr("about_license"), tr("about_license_val"))]
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
            cv.create_text(px(92), y, text=v, anchor="w", fill=T["text"], font=(FONT, 9, "bold"))

        # 언어 선택 (한국어 | English)
        lrow = tk.Frame(body, bg=T["bg"])
        lrow.pack(pady=(px(14), 0))
        tk.Label(lrow, text=tr("about_lang"), bg=T["bg"], fg=T["sub"], font=(FONT, 9)).pack(side="left", padx=(0, px(10)))
        seg = tk.Frame(lrow, bg=T["line"], padx=px(2), pady=px(2))
        seg.pack(side="left")
        for code, label in (("ko", "한국어"), ("en", "English")):
            on = code == self.lang
            lb = tk.Label(seg, text=label, font=(FONT, 9, "bold" if on else "normal"), padx=px(14), pady=px(4),
                          bg=T["card"] if on else T["line"], fg=T["accent_text"] if on else T["sub"],
                          cursor="arrow" if on else "hand2")
            lb.pack(side="left")
            if not on:
                lb.bind("<Button-1>", lambda e, c=code: self.set_language(c))

        Btn(body, tr("btn_close"), top.destroy, None, "primary", 140, 38).pack(pady=(px(14), 0))
        top.bind("<Escape>", lambda e: top.destroy())
        top.update_idletasks()
        if pos is None:
            x = self.root.winfo_x() + (self.root.winfo_width() - top.winfo_width()) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - top.winfo_height()) // 2
        else:
            x, y = pos
        top.geometry(f"+{max(0, x)}+{max(0, y)}")
        top.focus_force()

    def poll(self):
        try:
            while True:
                kind, extra = self.q.get_nowait()
                if kind == "failed":
                    self.hotkey_failed = extra
                    self.update_note()
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
                    raise RuntimeError(tr("err_no_window"))
                l, t, r, b = rect
                box = (max(0, l - origin[0]), max(0, t - origin[1]),
                       min(shot.width, r - origin[0]), min(shot.height, b - origin[1]))
                self.finish(shot.crop(box))
            else:
                self.select_region(shot, origin, mons)
        except Exception as ex:
            self.busy = False
            self.root.deiconify()
            messagebox.showerror(tr("err_capture_title"), str(ex))

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
            cv.create_text(W / 2, H / 2 + px(70), text=tr("preview_empty"), fill=T["sub"], font=(FONT, 9))
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
        tk.Label(hd, text=tr("recent"), bg=T["bg"], fg=T["sub"], font=(FONT, 9, "bold")).pack(side="left")
        tk.Label(hd, text=tr("recent_hint", n=MAX_HISTORY), bg=T["bg"], fg=T["sub"],
                 font=(FONT, 8)).pack(side="right")
        self.strip = tk.Canvas(parent, width=px(STRIP_W), height=px(54), bg=T["bg"], highlightthickness=0)
        self.strip.pack()
        self.x_hover = None  # 마우스가 올라간 삭제(X) 버튼의 칸 번호
        self.strip.bind("<Button-1>", self.on_strip_click)
        self.strip.bind("<Motion>", self.on_strip_move)
        self.strip.bind("<Leave>", lambda e: self.set_x_hover(None))

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

    def x_center(self, i):
        """칸 i의 삭제(X) 버튼 중심 좌표 (썸네일 안쪽 오른쪽 위)."""
        x0, w = self.slot_box(i)
        return x0 + w - px(13), px(3) + px(12)

    def x_hit(self, i, x, y):
        cx, cy = self.x_center(i)
        return (x - cx) ** 2 + (y - cy) ** 2 <= px(10) ** 2

    def x_at(self, x, y):
        i = self.slot_at(x)
        return i if i is not None and self.x_hit(i, x, y) else None

    def set_x_hover(self, i):
        if i != self.x_hover:
            self.x_hover = i
            self.draw_strip()

    def on_strip_move(self, e):
        xi = self.x_at(e.x, e.y)
        self.strip.config(cursor="hand2" if self.slot_at(e.x) is not None else "arrow")
        self.set_x_hover(xi)

    def on_strip_click(self, e):
        i = self.slot_at(e.x)
        if i is None:
            return
        if self.x_hit(i, e.x, e.y):
            self.delete_capture(i)
        else:
            self.sel = i
            self.refresh_all()

    def delete_capture(self, i):
        """최근 캡처 i번을 삭제한다. 보던 캡처를 지우면 다음(없으면 이전) 캡처를 선택."""
        if not 0 <= i < len(self.history):
            return
        del self.history[i]
        if not self.history:
            self.sel = None
        elif self.sel == i:
            self.sel = min(i, len(self.history) - 1)
        elif self.sel is not None and self.sel > i:
            self.sel -= 1
        self.x_hover = None
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
                cv.create_text(x1 - px(19), H - px(14.5), text=tr("tag_new"), fill="#FFFFFF", font=(FONT, 7, "bold"))
            # 삭제(X) 버튼
            cx, cy = self.x_center(i)
            r = px(9)
            hv = self.x_hover == i
            cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=T["accent"] if hv else T["card"],
                           outline=T["accent"] if hv else T["line"])
            k = px(3.5)
            xc = "#FFFFFF" if hv else T["sub"]
            cv.create_line(cx - k, cy - k, cx + k, cy + k, fill=xc, width=2, capstyle="round")
            cv.create_line(cx - k, cy + k, cx + k, cy - k, fill=xc, width=2, capstyle="round")

    def refresh_all(self):
        self.show_preview()
        self.draw_strip()
        img = self.last
        if img is not None:
            self.info.config(text=tr("info_capture", n=self.sel + 1, w=img.width, h=img.height))
        else:
            self.info.config(text="")
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
            self.info.config(text=tr("copied"))
        except Exception as ex:
            messagebox.showerror(tr("err_copy_title"), str(ex))

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
                messagebox.showerror(tr("err_save_title"), str(ex))
                return
            self.info.config(text=tr("saved", name=os.path.basename(path)))

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
        apply_language(detect_lang())
        messagebox.showinfo(tr("app_name"), tr("already_running"))
        sys.exit(0)
    App().run()
