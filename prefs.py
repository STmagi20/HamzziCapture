"""설정 창: 저장 폴더, 캡처 직후 자동 복사/저장. 값은 settings.json에 바로 저장된다."""
import os
import tkinter as tk
from tkinter import filedialog

from i18n import tr
from settings import configured_dir, load_settings, save_dir, update_settings
from widgets import FONT, T, Btn, finish_dialog, open_dialog, px


def open_settings(root):
    """설정 창을 만들어 돌려준다."""
    top, body = open_dialog(root, tr("settings_title"), 26, 20)

    # --- 저장 폴더 ---
    tk.Label(body, text=tr("set_save_dir"), bg=T["bg"], fg=T["text"], font=(FONT, 10, "bold")).pack(anchor="w")
    row = tk.Frame(body, bg=T["bg"])
    row.pack(fill="x", pady=(px(6), 0))
    path_lbl = tk.Label(row, bg=T["card"], fg=T["text"], font=(FONT, 9), anchor="w", justify="left",
                        wraplength=px(280), padx=px(10), pady=px(6),
                        highlightbackground=T["line"], highlightthickness=1)
    path_lbl.pack(side="left", fill="x", expand=True)
    reset = Btn(row, tr("set_reset"), lambda: set_dir(""), None, "secondary", 64, 32)
    reset.pack(side="right", padx=(px(4), 0))
    Btn(row, tr("set_change"), lambda: choose(), None, "secondary", 64, 32).pack(side="right", padx=(px(6), 0))

    def refresh():
        custom = configured_dir()
        # 정한 폴더가 아직 없어도 그대로 보여 준다 (자동 저장 때 만들어진다)
        path_lbl.config(text=custom or f"{save_dir()} {tr('set_default_tag')}")
        reset.set_enabled(bool(custom))

    def set_dir(d):
        update_settings(save_dir=d)
        refresh()

    def choose():
        d = filedialog.askdirectory(parent=top, initialdir=save_dir(), mustexist=True, title=tr("set_pick_dir"))
        if d:
            set_dir(os.path.normpath(d))

    # --- 캡처 직후 동작 ---
    tk.Label(body, text=tr("set_after_capture"), bg=T["bg"], fg=T["text"], font=(FONT, 10, "bold")).pack(
        anchor="w", pady=(px(16), 0))
    s = load_settings()
    copy_var = tk.BooleanVar(value=s.get("auto_copy") is True)
    save_var = tk.BooleanVar(value=s.get("auto_save") is True)
    for var, key, text in ((copy_var, "auto_copy", tr("set_auto_copy")), (save_var, "auto_save", tr("set_auto_save"))):
        tk.Checkbutton(body, text=text, variable=var, command=lambda v=var, k=key: update_settings(**{k: v.get()}),
                       bg=T["bg"], activebackground=T["bg"], fg=T["text"], activeforeground=T["text"],
                       selectcolor=T["card"], font=(FONT, 9), anchor="w", cursor="hand2",
                       highlightthickness=0, bd=0).pack(anchor="w", pady=(px(4), 0))

    tk.Label(body, text=tr("set_note"), bg=T["bg"], fg=T["sub"], font=(FONT, 8), wraplength=px(360),
             justify="left", anchor="w").pack(anchor="w", pady=(px(14), 0))

    refresh()
    finish_dialog(top, body, root)
    return top
