"""설정 파일: %APPDATA%\\HamzziCapture\\settings.json

지금은 언어 선택("lang")만 저장한다. 읽기/쓰기에 실패해도 프로그램은 기본값으로 동작한다.
"""
import json
import os

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


def start_lang():
    """시작 언어: 저장한 선택이 있으면 그것, 없으면 Windows 표시 언어."""
    lang = load_settings().get("lang")
    return lang if lang in ("ko", "en") else detect_lang()
