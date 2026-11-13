"""편집기 창: 펜, 형광펜, 선, 화살표, 사각형, 원, 텍스트, 모자이크, 자르기, 실행 취소, 복사, 저장."""
import tkinter as tk
from tkinter import colorchooser, simpledialog

from PIL import Image, ImageTk

from drawing import apply_shape, apply_text, crop_image
from i18n import tr
from widgets import FONT, T, Btn, ask_save_path, bind_ctrl_keys, copy_or_warn, px, save_or_warn
from winapi import IS_WIN

# (도구 키, 문자열 키)
TOOLS = [
    ("pen", "tool_pen"), ("highlight", "tool_highlight"), ("line", "tool_line"), ("arrow", "tool_arrow"),
    ("rect", "tool_rect"), ("ellipse", "tool_ellipse"), ("text", "tool_text"), ("mosaic", "tool_mosaic"),
    ("crop", "tool_crop"),
]
COLORS = ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#0a84ff", "#af52de", "#000000", "#ffffff"]
BOX_TOOLS = ("highlight", "mosaic", "crop")  # 드래그하는 동안 점선 상자로만 미리 보여주는 도구


class Editor:
    def __init__(self, root, image, on_close=None):
        """on_close(img): 창을 닫을 때 편집한 이미지를 넘겨준다."""
        self.root = root
        self.on_close = on_close
        self.img = image.convert("RGBA")
        self.history = []  # 실행 취소용 이전 이미지들
        self.tool = "pen"
        self.width = tk.IntVar(value=4)
        self.color = COLORS[0]
        self.pts = []   # 드래그 중인 점 (이미지 좌표)
        self.cpts = []  # 같은 점 (캔버스 좌표, 미리보기용)

        self.win = tk.Toplevel(root)
        self.win.title(tr("editor_title"))
        self.win.configure(bg=T["bg"])
        self.fit_scale()

        self.build_toolbar()
        self.canvas = tk.Canvas(self.win, highlightthickness=0, bg=T["bg"], cursor="crosshair")
        self.canvas.pack(expand=True, padx=px(14), pady=px(14))
        self.status = tk.Label(self.win, anchor="w", bg=T["bg"], fg=T["sub"], font=(FONT, 9), padx=px(12), pady=px(5))
        self.status.pack(fill="x")

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        bind_ctrl_keys(self.win, {"z": self.undo, "c": self.copy, "s": self.save})
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
        self.select_tool(self.tool)

        self._separator(bar)

        # 색상
        self.sw_cv = {}
        for c in COLORS + ["custom"]:
            cv = tk.Canvas(bar, width=px(24), height=px(24), bg=T["card"], highlightthickness=0, cursor="hand2")
            cv.pack(side="left", padx=px(1))
            cv.bind("<Button-1>", (lambda e: self.pick_color()) if c == "custom" else (lambda e, c=c: self.set_color(c)))
            self.sw_cv[c] = cv
        self.redraw_swatches()

        self._separator(bar)

        # 굵기
        tk.Label(bar, text=tr("width_label"), bg=T["card"], fg=T["sub"], font=(FONT, 9)).pack(side="left")
        tk.Scale(bar, from_=1, to=20, orient="horizontal", variable=self.width, length=px(90), showvalue=False,
                 bg=T["card"], troughcolor=T["line"], highlightthickness=0, bd=0, sliderrelief="flat",
                 activebackground=T["accent"], sliderlength=px(14), width=px(8)).pack(side="left", padx=px(4))

        # 우측 버튼
        Btn(bar, tr("btn_save"), self.save, "save", "primary", 84, 32, T["card"]).pack(side="right", padx=(px(6), 0))
        Btn(bar, tr("btn_copy"), self.copy, "copy", "secondary", 84, 32, T["card"]).pack(side="right", padx=px(3))
        Btn(bar, tr("btn_undo"), self.undo, "undo", "secondary", 84, 32, T["card"]).pack(side="right", padx=px(3))

    @staticmethod
    def _separator(bar):
        tk.Frame(bar, bg=T["line"], width=1).pack(side="left", fill="y", padx=px(10))

    def select_tool(self, key):
        self.tool = key
        for k, l in self.tool_lbls.items():
            l.config(bg=T["card"] if k == key else T["bg"], fg=T["accent_text"] if k == key else T["sub"])

    def redraw_swatches(self):
        W = px(24)

        def ring(cv):  # 선택 표시 테두리
            cv.create_oval(px(1), px(1), W - px(1), W - px(1), outline=T["accent"], width=2)

        for c, cv in self.sw_cv.items():
            cv.delete("all")
            if c == "custom":
                if self.color not in COLORS:
                    ring(cv)
                    cv.create_oval(px(5), px(5), W - px(5), W - px(5), fill=self.color, outline=T["line"])
                else:
                    cv.create_oval(px(4), px(4), W - px(4), W - px(4), outline=T["dis_fg"], dash=(2, 2))
                    cv.create_text(W / 2, W / 2, text="+", fill=T["sub"], font=(FONT, 9))
            elif c == self.color:
                ring(cv)
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

    def fit_scale(self):
        """화면에 들어오는 표시 배율 (자르기로 이미지 크기가 바뀌면 다시 계산)."""
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.scale = min(1.0, (sw * 0.9) / self.img.width, (sh * 0.75) / self.img.height)

    def refresh(self):
        self.fit_scale()
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
        if self.tool == "text":
            text = simpledialog.askstring(tr("text_dialog_title"), tr("text_dialog_prompt"), parent=self.win)
            if text:
                self.commit(apply_text(self.img, self.pts[0], text, self.color, self.width.get()))
            self.pts = []

    def on_drag(self, e):
        if not self.pts:
            return
        tool = self.tool
        self.canvas.delete("preview")
        self.cpts.append((e.x, e.y))
        self.pts.append(self.to_img(e))
        c0, c1 = self.cpts[0], self.cpts[-1]
        w = max(1, int(self.width.get() * self.scale))
        opts = dict(width=w, tags="preview")
        if tool == "pen":
            flat = [v for p in self.cpts for v in p]
            if len(flat) >= 4:
                self.canvas.create_line(*flat, fill=self.color, capstyle="round", joinstyle="round", **opts)
        elif tool in ("line", "arrow"):
            self.canvas.create_line(*c0, *c1, fill=self.color, arrow="last" if tool == "arrow" else None, **opts)
        elif tool == "ellipse":
            self.canvas.create_oval(*c0, *c1, outline=self.color, **opts)
        elif tool == "rect":
            self.canvas.create_rectangle(*c0, *c1, outline=self.color, **opts)
        elif tool in BOX_TOOLS:
            self.canvas.create_rectangle(*c0, *c1, outline=self.color, dash=(4, 3), width=2, tags="preview")

    def on_release(self, e):
        if not self.pts:
            return
        self.canvas.delete("preview")
        if self.tool == "crop":
            cropped = crop_image(self.img, self.pts[0], self.pts[-1])
            if cropped is not None:  # 너무 작은 영역(그냥 클릭)은 무시
                self.commit(cropped)
        elif len(self.pts) > 1 or self.tool == "pen":
            self.commit(apply_shape(self.img, self.tool, self.pts, self.color, self.width.get()))
        self.pts = []

    # --- 출력 ---
    def copy(self):
        if copy_or_warn(self.img, self.win):
            self.status.config(text=tr("editor_copied"))

    def save(self):
        path = ask_save_path(self.win)
        if path and save_or_warn(self.img, path, self.win):
            self.status.config(text=tr("editor_saved", path=path))
