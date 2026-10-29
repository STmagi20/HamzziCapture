"""한국어 / English 문자열 (Korean / English UI strings).

사용법: from i18n import tr, set_lang, detect_lang
        tr("btn_save")  ->  "저장" 또는 "Save"
"""
import locale
import sys

LANG = "ko"

STRINGS = {
    "app_name": {"ko": "햄찌캡처", "en": "Hamzzi Capture"},
    "subtitle": {"ko": "무엇을 담을까요?", "en": "What would you like to capture?"},
    "tile_region": {"ko": "영역 선택", "en": "Region"},
    "tile_monitor": {"ko": "현재 모니터", "en": "Current Monitor"},
    "tile_window": {"ko": "활성 창", "en": "Active Window"},
    "tile_all": {"ko": "모든 모니터", "en": "All Monitors"},
    "note_hotkeys": {"ko": "단축키는 창을 최소화해도 동작해요", "en": "Hotkeys work even when minimized"},
    "hotkey_failed": {
        "ko": "{keys} 단축키를 쓸 수 없어요. 이미 실행 중인 캡처 프로그램이 있다면 먼저 종료해 주세요.",
        "en": "Hotkey {keys} is unavailable. If another capture program is already running, please close it first.",
    },
    "recent": {"ko": "최근 캡처", "en": "Recent captures"},
    "recent_hint": {"ko": "{n}개까지 보관 · 클릭해서 다시 열기", "en": "Up to {n} kept · click to reopen"},
    "tag_new": {"ko": "방금", "en": "New"},
    "preview_empty": {"ko": "캡처하면 여기에 표시돼요", "en": "Your capture will appear here"},
    "info_capture": {"ko": "{n}번째 캡처 · {w} × {h} px", "en": "Capture #{n} · {w} × {h} px"},
    "btn_edit": {"ko": "편집", "en": "Edit"},
    "btn_copy": {"ko": "복사", "en": "Copy"},
    "btn_save": {"ko": "저장", "en": "Save"},
    "btn_undo": {"ko": "취소", "en": "Undo"},
    "btn_close": {"ko": "닫기", "en": "Close"},
    "copied": {"ko": "클립보드에 복사했어요", "en": "Copied to clipboard"},
    "saved": {"ko": "저장했어요: {name}", "en": "Saved: {name}"},
    "err_copy_title": {"ko": "복사 실패", "en": "Copy failed"},
    "err_save_title": {"ko": "저장 실패", "en": "Save failed"},
    "err_capture_title": {"ko": "캡처 실패", "en": "Capture failed"},
    "err_ext": {"ko": "PNG(.png) 또는 JPG(.jpg) 확장자로 저장해 주세요.", "en": "Please save as .png or .jpg."},
    "err_win_only": {"ko": "클립보드 복사는 Windows에서만 지원합니다.", "en": "Clipboard copy is only supported on Windows."},
    "err_clip_open": {"ko": "클립보드를 열 수 없습니다.", "en": "Could not open the clipboard."},
    "err_mem_alloc": {"ko": "메모리를 확보하지 못했습니다.", "en": "Could not allocate memory."},
    "err_mem_lock": {"ko": "메모리를 잠그지 못했습니다.", "en": "Could not lock memory."},
    "err_clip_set": {"ko": "클립보드에 데이터를 넣지 못했습니다.", "en": "Could not put data on the clipboard."},
    "err_no_window": {"ko": "활성 창을 찾지 못했습니다.", "en": "Could not find the active window."},
    "region_hint": {
        "ko": "드래그하여 영역 선택  |  Esc / 우클릭: 취소",
        "en": "Drag to select a region  |  Esc / right-click: cancel",
    },
    "delay_none": {"ko": "지연 없음", "en": "No delay"},
    "delay_n": {"ko": "지연 {n}초", "en": "Delay {n}s"},
    "tool_pen": {"ko": "펜", "en": "Pen"},
    "tool_highlight": {"ko": "형광펜", "en": "Highlight"},
    "tool_line": {"ko": "선", "en": "Line"},
    "tool_arrow": {"ko": "화살표", "en": "Arrow"},
    "tool_rect": {"ko": "사각형", "en": "Rectangle"},
    "tool_ellipse": {"ko": "원", "en": "Ellipse"},
    "tool_text": {"ko": "텍스트", "en": "Text"},
    "tool_mosaic": {"ko": "모자이크", "en": "Mosaic"},
    "width_label": {"ko": "굵기", "en": "Width"},
    "editor_title": {"ko": "햄찌캡처 편집기", "en": "Hamzzi Capture Editor"},
    "editor_status": {
        "ko": " {w} x {h}px   |   Ctrl+Z 취소 · Ctrl+C 복사 · Ctrl+S 저장 · Esc 닫기",
        "en": " {w} x {h}px   |   Ctrl+Z undo · Ctrl+C copy · Ctrl+S save · Esc close",
    },
    "editor_copied": {"ko": " 클립보드에 복사했어요", "en": " Copied to clipboard"},
    "editor_saved": {"ko": " 저장했어요: {path}", "en": " Saved: {path}"},
    "text_dialog_title": {"ko": "텍스트", "en": "Text"},
    "text_dialog_prompt": {"ko": "입력할 내용:", "en": "Enter text:"},
    "about_title": {"ko": "{app} 정보", "en": "About {app}"},
    "about_version": {"ko": "버전 {v}", "en": "Version {v}"},
    "about_author": {"ko": "제작", "en": "Author"},
    "about_help": {"ko": "도움", "en": "Made with"},
    "about_images": {"ko": "이미지", "en": "Images"},
    "about_license": {"ko": "라이선스", "en": "License"},
    "about_ai": {"ko": "AI 생성", "en": "AI-generated"},
    "about_license_val": {"ko": "MIT License (소스 코드)", "en": "MIT License (source code)"},
    "about_lang": {"ko": "언어", "en": "Language"},
    "already_running": {
        "ko": "이미 실행 중입니다. 작업 표시줄에서 기존 창을 확인해 주세요.",
        "en": "Already running. Please check the existing window in the taskbar.",
    },
}


def detect_lang():
    """Windows 표시 언어가 한국어면 'ko', 아니면 'en'."""
    if sys.platform == "win32":
        try:
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "ko" if (lid & 0x3FF) == 0x12 else "en"  # 0x12 = LANG_KOREAN
        except Exception:
            pass
    try:
        loc = (locale.getlocale()[0] or "").lower()
    except Exception:
        loc = ""
    return "ko" if loc.startswith(("ko", "korean")) else "en"


def set_lang(lang):
    global LANG
    LANG = lang if lang in ("ko", "en") else "en"


def tr(key, **kw):
    s = STRINGS[key][LANG]
    return s.format(**kw) if kw else s
