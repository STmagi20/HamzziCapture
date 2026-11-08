"""영역 선택 오버레이: 모니터 하나를 덮고 드래그한 부분을 잘라 돌려준다."""
import tkinter as tk

from PIL import ImageEnhance, ImageTk

from drawing import norm_box
from i18n import tr
from widgets import FONT

MIN_SIZE = 5  # 이보다 작게 드래그하면 취소로 본다(px)


class RegionSelector:
    def __init__(self, root, shot, origin, on_done):
        """shot: 이 모니터의 화면 이미지, origin: 모니터 좌상단 화면 좌표,
        on_done(img 또는 None): 선택이 끝나거나 취소되면 호출."""
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
        self.label_id = self.canvas.create_text(0, 0, anchor="sw", fill="white", font=(FONT, 10, "bold"))
        self.canvas.create_text(w // 2, 30, fill="white", font=(FONT, 12, "bold"), text=tr("region_hint"))

        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Button-3>", lambda e: self.cancel())
        self.top.bind("<Escape>", lambda e: self.cancel())
        self.focus()

    def focus(self):
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
        if r - l < MIN_SIZE or b - t < MIN_SIZE:
            self.on_done(None)
        else:
            self.on_done(self.shot.crop((l, t, r, b)))

    def cancel(self):
        self.on_done(None)

    def destroy(self):
        try:
            self.top.destroy()
        except tk.TclError:
            pass
