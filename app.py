"""햄찌캡처 - 간단 화면 캡처 프로그램 (Windows)

기능
- 영역 선택 캡처 / 전체 화면(모든 모니터) / 현재 모니터 / 활성 창 캡처
- 지연 캡처(초)
- 편집기: 펜, 형광펜, 선, 화살표, 사각형, 원, 텍스트, 모자이크, 실행 취소
- 저장(PNG/JPG) + 클립보드 복사
- 전역 단축키: Ctrl+Shift+A (영역), M (현재 모니터), F (모든 모니터), W (활성 창)

파일 구성
- app.py      메인 창, 캡처 흐름, 최근 캡처 목록 (이 파일, 실행 진입점)
- editor.py   편집기 창
- region.py   영역 선택 오버레이
- widgets.py  테마 색상, 아이콘, 버튼 등 커스텀 위젯, 저장 대화상자
- drawing.py  도형·모자이크 그리기, 이미지 저장 (tkinter 없음)
- winapi.py   Windows API: 화면 좌표, 클립보드, 전역 단축키, 중복 실행 방지
- settings.py 설정 파일(언어, 저장 폴더, 자동 복사/저장) 읽기/쓰기
- prefs.py    설정 창 (저장 폴더, 캡처 직후 자동 복사/저장)
- i18n.py     한국어/영어 문자열, assets.py 내장 햄스터 이미지
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageOps, ImageTk

import assets
from drawing import rounded_image, save_image, unique_path
from editor import Editor
from i18n import set_lang, tr
from prefs import open_settings
from region import RegionSelector
from settings import auto_actions, configured_dir, save_dir, start_lang, update_settings
from widgets import (FONT, T, UI, Btn, InfoBtn, SettingsBtn, Stepper, Tile, ask_save_path,
                     bind_ctrl_keys, hamster, px, round_rect, show_error)
from winapi import (IS_WIN, active_window_rect, already_running, clipboard_image, copy_image_to_clipboard,
                    crop_screen, enable_dpi_awareness, get_monitors, grab_screen, hotkey_loop,
                    own_window_active, set_app_id)

# 앱 정보 (정보 창에 표시)
VERSION = "1.2.1"
AUTHOR = "Studying Hamzzi"

enable_dpi_awareness()  # 창을 만들기 전에 해야 한다

MAX_HISTORY = 5  # 최근 캡처 보관 개수 (실행 중에만 유지)

# 메인 창 레이아웃 (100% 배율 기준, 전체 폭 800px = 좌우 여백 26*2 + 368 + 20 + 360)
LEFT_W, GAP_W, RIGHT_W = 368, 20, 360
PV_W, PV_H = RIGHT_W, 292   # 미리보기 카드
STRIP_W, STRIP_H = LEFT_W, 54  # 최근 캡처 썸네일 줄

# 캡처 타일: (아이콘, 문자열 키, 단축키 표시, 캡처 모드)
TILES = [
    ("region", "tile_region", "Ctrl+Shift+A", "region"),
    ("monitor", "tile_monitor", "Ctrl+Shift+M", "monitor"),
    ("window", "tile_window", "Ctrl+Shift+W", "window"),
    ("monitors", "tile_all", "Ctrl+Shift+F", "full"),
]


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
        self.history = []  # 최근 캡처 목록 (최신이 앞), 최대 MAX_HISTORY개. 항목: {"img": RGBA 이미지}
        self.sel = None    # 현재 선택된 항목 번호

        self.lang = start_lang()
        set_lang(self.lang)
        self.about = None
        self.prefs = None
        self.hotkey_failed = None
        self.build_ui()

        bind_ctrl_keys(self.root, {"c": self.copy_last, "s": self.save_last, "v": self.paste_clipboard})

        if IS_WIN:
            threading.Thread(target=hotkey_loop, args=(self.q,), daemon=True).start()
        self.root.after(100, self.poll)

    def run(self):
        self.root.mainloop()

    # ------------------------------------------------------------------
    # 화면 구성
    # ------------------------------------------------------------------
    def build_ui(self):
        """메인 창 화면을 (다시) 만든다. 언어를 바꾸면 이 함수를 다시 호출한다."""
        old = getattr(self, "main_frame", None)
        if old is not None:
            old.destroy()
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
        SettingsBtn(head, self.show_settings).pack(side="right", padx=(px(10), 0))
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
        for i, (ic, title, hint, mode) in enumerate(TILES):
            Tile(grid, ic, tr(title), hint, lambda m=mode: self.start(m), w=176).grid(
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
        for i, b in enumerate(self.action_btns):
            b.pack(side="left", expand=True, padx=(0 if i == 0 else px(4), 0))
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
        if self.prefs is not None and self.prefs.winfo_exists():
            self.prefs.destroy()  # 낡은 언어로 남지 않게 닫는다
        self.lang = lang
        set_lang(lang)
        update_settings(lang=lang)
        self.build_ui()
        if pos is not None:
            self.show_about(pos)

    def show_settings(self):
        if self.prefs is not None and self.prefs.winfo_exists():
            self.prefs.lift()
            return
        self.prefs = open_settings(self.root)

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

    # ------------------------------------------------------------------
    # 캡처 흐름: start -> (지연) -> capture -> [select_region] -> finish
    # ------------------------------------------------------------------
    def poll(self):
        """단축키 스레드가 넣은 이벤트를 100ms마다 처리한다."""
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

    def delay_ms(self):
        try:
            return max(0, int(self.delay.get())) * 1000
        except (tk.TclError, ValueError):
            return 0

    def start(self, mode, hotkey=False):
        if self.busy:
            return
        self.busy = True
        delay = self.delay_ms()
        if hotkey and mode == "window" and own_window_active():
            # 햄찌캡처 자신의 창(메인/편집기/정보)이 활성 상태면 숨기지 않고 그대로 캡처
            self.root.after(150 + delay, lambda: self.capture(mode))
            return
        self.root.withdraw()
        self.root.after(250 + delay, lambda: self.capture(mode))

    def capture(self, mode):
        try:
            shot, origin = grab_screen()
            mons = get_monitors() or [(origin[0], origin[1], origin[0] + shot.width, origin[1] + shot.height)]
            if mode == "full":
                self.finish(shot)
            elif mode == "monitor":
                mx, my = self.root.winfo_pointerxy()
                self.finish(crop_screen(shot, origin, monitor_at(mons, mx, my) or mons[0]))
            elif mode == "window":
                rect = active_window_rect()
                if not rect:
                    raise RuntimeError(tr("err_no_window"))
                self.finish(crop_screen(shot, origin, rect))
            else:
                self.select_region(shot, origin, mons)
        except Exception as ex:
            self.busy = False
            self.root.deiconify()
            show_error("err_capture_title", ex, self.root)

    def select_region(self, shot, origin, mons):
        """모니터마다 오버레이를 하나씩 띄운다 (한 모니터 안에서 드래그)."""
        overlays = []

        def done(img):
            for o in overlays:
                o.destroy()
            self.finish(img)

        for m in mons:
            overlays.append(RegionSelector(self.root, crop_screen(shot, origin, m), m[:2], done))
        # 마우스가 있는 모니터의 오버레이에 키보드 포커스 (Esc로 취소할 수 있게)
        mx, my = self.root.winfo_pointerxy()
        here = monitor_at(mons, mx, my)
        if here:
            overlays[mons.index(here)].focus()

    def finish(self, image):
        self.busy = False
        self.root.deiconify()
        self.root.lift()
        if image is not None:
            self.add_capture(image)  # 편집기는 자동으로 열지 않고 미리보기만 표시
            self.auto_actions(self.last)

    def auto_actions(self, img):
        """설정에 따라 캡처 직후 클립보드 복사 / 저장 폴더에 저장."""
        want_copy, want_save = auto_actions()
        copied, saved = False, None
        if want_copy:
            try:
                copy_image_to_clipboard(img)
                copied = True
            except Exception as ex:
                show_error("err_copy_title", ex, self.root)
        if want_save:
            try:
                folder = configured_dir() or save_dir()
                os.makedirs(folder, exist_ok=True)
                path = unique_path(folder)
                save_image(img, path)
                saved = os.path.basename(path)
            except Exception as ex:
                show_error("err_save_title", ex, self.root)
        if copied and saved:
            self.info.config(text=tr("auto_both", name=saved))
        elif saved:
            self.info.config(text=tr("auto_saved", name=saved))
        elif copied:
            self.info.config(text=tr("auto_copied"))

    # ------------------------------------------------------------------
    # 미리보기 / 최근 캡처 목록
    # ------------------------------------------------------------------
    @property
    def last(self):
        """현재 선택된 캡처 이미지 (없으면 None)."""
        if self.sel is not None and 0 <= self.sel < len(self.history):
            return self.history[self.sel]["img"]
        return None

    def show_preview(self):
        cv = self.pv
        cv.delete("all")
        W, H = px(PV_W), px(PV_H)
        round_rect(cv, 1, 1, W - 1, H - 1, px(14), fill=T["card"], outline=T["line"])
        if self.last is None:
            self.pv_img = None  # 지운 캡처의 이미지를 메모리에 남기지 않는다
            cv.create_image(W / 2, H / 2 - px(22), image=hamster("body", 130))
            cv.create_text(W / 2, H / 2 + px(70), text=tr("preview_empty"), fill=T["sub"], font=(FONT, 9))
        else:
            pad = px(10)
            thumb = self.last.convert("RGB")
            thumb.thumbnail((W - 2 * pad, H - 2 * pad), Image.LANCZOS)
            self.pv_img = ImageTk.PhotoImage(rounded_image(thumb, px(8)))
            cv.create_image(W / 2, H / 2, image=self.pv_img)

    def build_strip(self, parent):
        hd = tk.Frame(parent, bg=T["bg"])
        hd.pack(fill="x", pady=(px(14), px(4)))
        tk.Label(hd, text=tr("recent"), bg=T["bg"], fg=T["sub"], font=(FONT, 9, "bold")).pack(side="left")
        self.clear_lbl = tk.Label(hd, text=tr("clear_all"), bg=T["bg"], font=(FONT, 8, "bold"))
        self.clear_lbl.pack(side="right", padx=(px(8), 0))
        self.clear_lbl.bind("<Button-1>", lambda e: self.clear_captures())
        tk.Label(hd, text=tr("recent_hint", n=MAX_HISTORY), bg=T["bg"], fg=T["sub"],
                 font=(FONT, 8)).pack(side="right")
        self.strip = tk.Canvas(parent, width=px(STRIP_W), height=px(STRIP_H), bg=T["bg"], highlightthickness=0)
        self.strip.pack()
        self.x_hover = None  # 마우스가 올라간 삭제(X) 버튼의 칸 번호
        self.strip.bind("<Button-1>", self.on_strip_click)
        self.strip.bind("<Motion>", self.on_strip_move)
        self.strip.bind("<Leave>", lambda e: self.set_x_hover(None))

    def slot_box(self, i):
        """칸 i의 (왼쪽 x, 폭)."""
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

    def set_x_hover(self, i):
        if i != self.x_hover:
            self.x_hover = i
            self.draw_strip()

    def on_strip_move(self, e):
        i = self.slot_at(e.x)
        self.strip.config(cursor="hand2" if i is not None else "arrow")
        self.set_x_hover(i if i is not None and self.x_hit(i, e.x, e.y) else None)

    def on_strip_click(self, e):
        i = self.slot_at(e.x)
        if i is None:
            return
        if self.x_hit(i, e.x, e.y):
            self.delete_capture(i)
        else:
            self.sel = i
            self.refresh_all()

    def draw_strip(self):
        cv, H = self.strip, px(STRIP_H)
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
            self.draw_x_button(cv, i)

    def draw_x_button(self, cv, i):
        cx, cy = self.x_center(i)
        r, k = px(9), px(3.5)
        hv = self.x_hover == i
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=T["accent"] if hv else T["card"],
                       outline=T["accent"] if hv else T["line"])
        xc = "#FFFFFF" if hv else T["sub"]
        cv.create_line(cx - k, cy - k, cx + k, cy + k, fill=xc, width=2, capstyle="round")
        cv.create_line(cx - k, cy + k, cx + k, cy - k, fill=xc, width=2, capstyle="round")

    def refresh_all(self):
        """미리보기, 썸네일 줄, 정보 문구, 버튼 상태를 현재 목록에 맞춘다."""
        self.show_preview()
        self.draw_strip()
        img = self.last
        if img is not None:
            self.info.config(text=tr("info_capture", n=self.sel + 1, w=img.width, h=img.height))
        else:
            self.info.config(text="")
        for b in self.action_btns:
            b.set_enabled(img is not None)
        on = bool(self.history)
        self.clear_lbl.config(fg=T["accent_text"] if on else T["dis_fg"], cursor="hand2" if on else "arrow")

    def add_capture(self, image):
        self.history.insert(0, {"img": image.convert("RGBA")})
        del self.history[MAX_HISTORY:]
        self.sel = 0
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

    def clear_captures(self):
        """최근 캡처를 모두 지운다 (확인 후)."""
        if not self.history:
            return
        if not messagebox.askyesno(tr("clear_title"), tr("clear_confirm", n=len(self.history)), parent=self.root):
            return
        self.history.clear()
        self.sel = None
        self.x_hover = None
        self.refresh_all()
        self.info.config(text=tr("cleared"))

    # ------------------------------------------------------------------
    # 편집 / 복사 / 저장
    # ------------------------------------------------------------------
    def edit_last(self):
        if self.last is None:
            return
        entry = self.history[self.sel]

        def on_close(img):  # 편집기에서 돌아오면 그 항목을 편집본으로 교체
            entry["img"] = img.convert("RGBA")
            self.refresh_all()

        Editor(self.root, entry["img"], on_close=on_close)

    def copy_last(self):
        if self.last is None:
            return
        try:
            copy_image_to_clipboard(self.last)
        except Exception as ex:
            show_error("err_copy_title", ex, self.root)
            return
        self.info.config(text=tr("copied"))

    def paste_clipboard(self):
        """Ctrl+V: 클립보드의 이미지를 새 캡처로 불러온다."""
        img = clipboard_image()
        if img is None:
            self.info.config(text=tr("paste_none"))
            return
        self.add_capture(img)
        self.info.config(text=tr("pasted"))

    def save_last(self):
        if self.last is None:
            return
        path = ask_save_path(self.root)
        if not path:
            return
        try:
            save_image(self.last, path)
        except Exception as ex:
            show_error("err_save_title", ex, self.root)
            return
        self.info.config(text=tr("saved", name=os.path.basename(path)))


def monitor_at(mons, x, y):
    """화면 좌표 (x, y)가 들어 있는 모니터 rect (없으면 None)."""
    return next((m for m in mons if m[0] <= x < m[2] and m[1] <= y < m[3]), None)


def main():
    set_app_id("Hamzzi.Capture")
    if already_running():
        r = tk.Tk()
        r.withdraw()
        set_lang(start_lang())
        messagebox.showinfo(tr("app_name"), tr("already_running"))
        sys.exit(0)
    App().run()


if __name__ == "__main__":
    main()
