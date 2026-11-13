"""디자인(라이트 미니멀): 테마 색상, DPI 배율, 아이콘, 커스텀 위젯, 공용 대화상자."""
import math
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

from PIL import Image, ImageDraw, ImageTk

import assets
from drawing import hex_to_rgb, save_image, timestamp_name
from i18n import tr
from settings import save_dir
from winapi import IS_WIN, copy_image_to_clipboard

# 테마 색상 (키별 쓰임새는 개발 문서의 테마 색상 표 참고)
T = dict(
    bg="#FFF8EE", card="#FFFFFF", line="#F0DFCB", text="#4A2A18", sub="#9A7656",
    accent="#E8A25A", accent_text="#B8661F", tint="#FFEFD9",
    primary="#F4B676", primary_h="#EFA55D", on_primary="#4A2A18",
    dis_bg="#F6EBDD", dis_fg="#CDB59C", warn="#B45309",
)
# 한국어/영어 모두 맑은 고딕 (한글이 섞여도 글꼴이 달라 보이지 않게)
FONT = "Malgun Gothic" if IS_WIN else "DejaVu Sans"

UI = {"s": 1.0}  # DPI 배율 (App이 시작할 때 정한다)


def px(n):
    """100% 배율 기준 크기 n을 현재 DPI 배율에 맞춘 픽셀 수로."""
    return max(1, int(round(n * UI["s"])))


# ----------------------------------------------------------------------------
# 이미지 (DPI 배율별로 한 번만 만들어 둔다)
# ----------------------------------------------------------------------------
_HAM = {}


def hamster(which, size):
    """내장 햄스터 이미지("face"/"body")를 size px(DPI 반영)로 변환."""
    key = (which, size, UI["s"])
    if key not in _HAM:
        n = px(size)
        _HAM[key] = ImageTk.PhotoImage(assets.load(which).resize((n, n), Image.LANCZOS))
    return _HAM[key]


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

    def dot(x1, y1, x2, y2):
        d.ellipse((x1 * u, y1 * u, x2 * u, y2 * u), fill=col)

    if name == "region":
        line((3, 8), (3, 3), (8, 3))
        line((14, 3), (19, 3), (19, 8))
        line((3, 14), (3, 19), (8, 19))
        line((14, 19), (19, 19), (19, 14))
        dot(9.6, 9.6, 12.4, 12.4)
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
        dot(5, 5.6, 6.6, 7.2)
        dot(7.6, 5.6, 9.2, 7.2)
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
    elif name == "gear":
        d.ellipse((5.5 * u, 5.5 * u, 16.5 * u, 16.5 * u), outline=col, width=w)
        d.ellipse((8.6 * u, 8.6 * u, 13.4 * u, 13.4 * u), outline=col, width=w)
        for k in range(8):
            a = math.radians(k * 45)
            line((11 + 5.5 * math.cos(a), 11 + 5.5 * math.sin(a)), (11 + 8.6 * math.cos(a), 11 + 8.6 * math.sin(a)))
    elif name == "image":
        rrect(3, 4, 19, 18, 2.5)
        d.ellipse((6.4 * u, 7.4 * u, 9.6 * u, 10.6 * u), outline=col, width=w)
        line((3.5, 16), (8.5, 12.5), (12, 15.5), (15, 12.5), (18.5, 15.5))
    img = ImageTk.PhotoImage(im.resize((out, out), Image.LANCZOS))
    _ICONS[key] = img
    return img


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    """캔버스에 둥근 사각형을 그린다."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


# ----------------------------------------------------------------------------
# 커스텀 위젯
# ----------------------------------------------------------------------------
class HoverCanvas(tk.Canvas):
    """마우스를 올리면 다시 그려지고, 안에서 클릭을 놓으면 command를 부르는 캔버스 버튼.

    하위 클래스는 self.hover / self.enabled를 보고 draw()를 구현한다.
    """

    def __init__(self, parent, w, h, command, bg=None):
        super().__init__(parent, width=px(w), height=px(h), bg=bg or T["bg"], highlightthickness=0, cursor="hand2")
        self.w, self.h, self.command = w, h, command
        self.hover, self.enabled = False, True
        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))
        self.bind("<ButtonRelease-1>", self.on_click)

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
        raise NotImplementedError


class Tile(HoverCanvas):
    """아이콘 + 제목 + 단축키가 들어간 카드형 캡처 버튼."""

    def __init__(self, parent, icon_name, title, hint, command, w=170, h=92):
        super().__init__(parent, w, h, command)
        self.icon_name, self.title, self.hint = icon_name, title, hint
        self.draw()

    def draw(self):
        self.delete("all")
        W, H, hv = px(self.w), px(self.h), self.hover
        round_rect(self, 1, 1, W - 1, H - 1, px(14),
                   fill=T["tint"] if hv else T["card"], outline=T["accent"] if hv else T["line"])
        self.create_image(W / 2, px(28), image=icon(self.icon_name, T["accent_text"] if hv else T["text"], 22))
        self.create_text(W / 2, px(55), text=self.title, font=(FONT, 10, "bold"), fill=T["text"])
        self.create_text(W / 2, px(73), text=self.hint, font=(FONT, 8), fill=T["accent_text"] if hv else T["sub"])


class Btn(HoverCanvas):
    """둥근 버튼 (primary / secondary), 아이콘 + 글자."""

    def __init__(self, parent, text, command, icon_name=None, kind="secondary", w=110, h=38, bg=None):
        super().__init__(parent, w, h, command, bg)
        self.text, self.icon_name, self.kind = text, icon_name, kind
        self.font = tkfont.Font(family=FONT, size=10, weight="bold")
        self.draw()

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


class RoundBtn(HoverCanvas):
    """헤더의 작은 원형 버튼. 하위 클래스가 draw_mark(중심, 색)로 가운데 표시를 그린다."""

    def __init__(self, parent, command):
        super().__init__(parent, 28, 28, command)
        self.draw()

    def draw(self):
        self.delete("all")
        s, hv = px(self.w), self.hover
        self.create_oval(2, 2, s - 2, s - 2, fill=T["tint"] if hv else T["card"],
                         outline=T["accent"] if hv else T["line"], width=2)
        self.draw_mark(s / 2, T["accent_text"] if hv else T["text"])

    def draw_mark(self, c, color):
        raise NotImplementedError


class InfoBtn(RoundBtn):
    """ⓘ (제작 정보) 버튼."""

    def draw_mark(self, c, color):
        self.create_text(c, c, text="i", font=("Georgia", 12, "italic bold"), fill=color)


class SettingsBtn(RoundBtn):
    """톱니 (설정) 버튼."""

    def draw_mark(self, c, color):
        self.create_image(c, c, image=icon("gear", color, 16))


class Stepper(tk.Frame):
    """지연 시간 − 0초 + 컨트롤."""

    def __init__(self, parent, var, lo=0, hi=30):
        super().__init__(parent, bg=T["card"], highlightbackground=T["line"], highlightthickness=1)
        self.var, self.lo, self.hi = var, lo, hi
        self._lbl("−", lambda: self.step(-1)).pack(side="left")
        # 라벨 폭은 '0' 글자 기준 개수라 한글이 잘린다 -> 가장 긴 문구를 실제로 재서 폭을 정한다
        f = tkfont.Font(family=FONT, size=9, weight="bold")
        longest = (tr("delay_none"), tr("delay_n", n=hi))
        n = math.ceil(max(f.measure(txt) for txt in longest) / f.measure("0")) + 2
        self.val = tk.Label(self, bg=T["card"], fg=T["text"], font=(FONT, 9, "bold"), width=n)
        self.val.pack(side="left")
        self._lbl("+", lambda: self.step(1)).pack(side="left")
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

    def value(self):
        try:
            return int(self.var.get())
        except (tk.TclError, ValueError):
            return 0

    def step(self, d):
        self.var.set(min(self.hi, max(self.lo, self.value() + d)))

    def refresh(self):
        v = self.value()
        try:
            self.val.config(text=tr("delay_n", n=v) if v else tr("delay_none"))
        except tk.TclError:  # 위젯이 이미 사라진 경우
            pass


# ----------------------------------------------------------------------------
# 작은 창 (정보 창, 설정 창)
# ----------------------------------------------------------------------------
def open_dialog(root, title, padx, pady):
    """크기 고정 보조 창을 만든다. (창, 내용을 담을 프레임)을 돌려준다."""
    top = tk.Toplevel(root)
    top.title(title)
    top.configure(bg=T["bg"])
    top.resizable(False, False)
    top.transient(root)
    body = tk.Frame(top, bg=T["bg"], padx=px(padx), pady=px(pady))
    body.pack()
    return top, body


def finish_dialog(top, body, root, pos=None):
    """닫기 버튼과 Esc를 달고, pos=(x, y) 또는 root 가운데에 띄운다."""
    Btn(body, tr("btn_close"), top.destroy, None, "primary", 140, 38).pack(pady=(px(14), 0))
    top.bind("<Escape>", lambda e: top.destroy())
    top.update_idletasks()
    if pos is None:
        x = root.winfo_x() + (root.winfo_width() - top.winfo_width()) // 2
        y = root.winfo_y() + (root.winfo_height() - top.winfo_height()) // 2
    else:
        x, y = pos
    top.geometry(f"+{max(0, x)}+{max(0, y)}")
    top.focus_force()


def alive(win):
    """창이 있고 아직 닫히지 않았는지."""
    return win is not None and win.winfo_exists()


# ----------------------------------------------------------------------------
# 복사 / 저장 (메인 창과 편집기가 함께 쓴다)
# ----------------------------------------------------------------------------
def copy_or_warn(img, parent):
    """클립보드에 복사한다. 실패하면 오류 창을 띄우고 False."""
    try:
        copy_image_to_clipboard(img)
    except Exception as ex:
        show_error("err_copy_title", ex, parent)
        return False
    return True


def save_or_warn(img, path, parent):
    """path에 저장한다. 실패하면 오류 창을 띄우고 False."""
    try:
        save_image(img, path)
    except Exception as ex:
        show_error("err_save_title", ex, parent)
        return False
    return True


def ask_save_path(parent):
    """PNG/JPG 저장 위치를 묻는다. 취소하면 빈 문자열."""
    return filedialog.asksaveasfilename(
        parent=parent, defaultextension=".png", initialdir=save_dir(),
        initialfile=timestamp_name(), filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
    )


def bind_ctrl_keys(win, keys):
    """Ctrl+글자 단축키를 건다. keys = {"c": 함수, ...}.

    한글 입력 상태에서는 Ctrl+C가 'c'가 아닌 한글 글자로 들어와 <Control-c> 바인딩이 안 먹는다.
    그래서 Windows에서는 글자가 아니라 키 자체의 번호(가상 키 코드)로 판별한다.
    """
    def on_key(e):
        if e.state & 0x1:  # Shift가 같이 눌렸으면 다른 단축키
            return None
        ch = chr(e.keycode).lower() if IS_WIN and 65 <= e.keycode <= 90 else (e.keysym or "").lower()
        fn = keys.get(ch)
        if fn is None:
            return None
        fn()
        return "break"

    win.bind("<Control-KeyPress>", on_key)


def show_error(title_key, ex, parent):
    messagebox.showerror(tr(title_key), str(ex), parent=parent)
