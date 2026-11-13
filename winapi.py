"""Windows 전용 기능: 화면 좌표, 활성 창, 클립보드, 전역 단축키, 중복 실행 방지.

Windows가 아니면 각 함수는 빈 값/False를 돌려주거나 오류를 낸다.
"""
import ctypes
import io
import os
import sys
from ctypes import wintypes

from PIL import Image, ImageGrab

from i18n import tr

IS_WIN = sys.platform == "win32"


def enable_dpi_awareness():
    """고DPI 환경에서 캡처 좌표가 어긋나지 않도록 한다 (창을 만들기 전에 호출)."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def set_app_id(app_id):
    """작업 표시줄에서 python.exe가 아닌 이 앱의 아이콘으로 묶이게 한다."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# 화면 좌표
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
    """모든 모니터를 한 장으로 찍는다. (이미지, 가상 화면 좌상단 좌표)를 돌려준다."""
    img = ImageGrab.grab(all_screens=True).convert("RGB")
    return img, virtual_origin()


def crop_screen(shot, origin, rect):
    """grab_screen() 결과에서 화면 좌표 rect=(l, t, r, b) 부분을 잘라낸다 (화면 밖은 잘라 버림)."""
    l, t, r, b = rect
    ox, oy = origin
    box = (max(0, l - ox), max(0, t - oy), min(shot.width, r - ox), min(shot.height, b - oy))
    return shot.crop(box)


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


# ----------------------------------------------------------------------------
# 클립보드
# ----------------------------------------------------------------------------
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


def clipboard_image():
    """클립보드의 이미지(또는 복사한 이미지 파일)를 PIL 이미지로. 없으면 None."""
    if not IS_WIN:
        return None
    try:
        data = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(data, list):  # 탐색기에서 파일을 복사한 경우: 첫 번째 이미지 파일
        for path in data:
            try:
                with Image.open(path) as im:
                    im.load()
                    return im.copy()
            except Exception:
                continue
        return None
    return data if isinstance(data, Image.Image) else None


# ----------------------------------------------------------------------------
# 전역 단축키 / 중복 실행
# ----------------------------------------------------------------------------
# 단축키 번호: (캡처 모드, Ctrl+Shift와 함께 누르는 키)
HOTKEYS = {1: ("region", "A"), 2: ("full", "F"), 3: ("window", "W"), 4: ("monitor", "M")}


def hotkey_loop(q):
    """RegisterHotKey 메시지 루프 (별도 스레드).

    단축키가 눌리면 q에 (모드, None)을, 등록에 실패한 키가 있으면 ("failed", [키...])를 넣는다.
    """
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


def already_running():
    """같은 프로그램이 이미 켜져 있으면 True (단축키 충돌 방지)."""
    if not IS_WIN:
        return False
    ctypes.windll.kernel32.CreateMutexW(None, False, "HamzziCaptureSingleton")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
