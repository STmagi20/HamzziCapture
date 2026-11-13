"""설정 파일: %APPDATA%\\HamzziCapture\\settings.json

저장하는 값: 언어("lang"), 저장 폴더("save_dir"), 캡처 후 자동 복사/저장("auto_copy", "auto_save").
읽기/쓰기에 실패해도 프로그램은 기본값으로 동작한다.
"""
import json
import os

from drawing import default_save_dir
from i18n import detect_lang


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "HamzziCapture", "settings.json")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def update_settings(**values):
    """기존 설정에 values를 덮어써서 저장한다. 실패해도 조용히 넘어간다."""
    data = load_settings()
    data.update(values)
    path = settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def configured_dir():
    """사용자가 정한 저장 폴더 (정하지 않았으면 빈 문자열)."""
    d = load_settings().get("save_dir")
    return d if isinstance(d, str) else ""


def save_dir():
    """저장 대화상자의 시작 폴더: 정해 둔 폴더가 있으면 그것, 없거나 사라졌으면 기본 폴더."""
    d = configured_dir()
    return d if d and os.path.isdir(d) else default_save_dir()


def auto_actions():
    """(캡처 후 자동 복사, 캡처 후 자동 저장). 기본값은 둘 다 꺼짐."""
    s = load_settings()
    return s.get("auto_copy") is True, s.get("auto_save") is True


def start_lang():
    """시작 언어: 저장한 선택이 있으면 그것, 없으면 Windows 표시 언어."""
    lang = load_settings().get("lang")
    return lang if lang in ("ko", "en") else detect_lang()
