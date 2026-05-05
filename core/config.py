"""設定持久化管理"""
import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".desktop_recorder" / "config.json"

DEFAULT_CONFIG = {
    "output_dir": str(Path.home() / "Videos" / "DesktopRecorder"),
    "filename_prefix": "錄影",
    "region_mode": "fullscreen",  # fullscreen / window / custom
    "monitor_index": 0,
    "custom_region": None,  # [x, y, w, h]
    "window_title": "",
    "resolution": "原始",  # 原始 / 1080p / 720p / 480p
    "fps": 30,
    "encoder": "auto",  # auto / libx264 / libx265 / h264_nvenc / hevc_nvenc / h264_qsv / h264_amf
    "quality_mode": "CRF",  # CRF / VBR / CBR
    "crf": 23,
    "bitrate": "5M",
    "container": "mp4",  # mp4 / mkv
    "audio_system": False,
    "audio_mic": False,
    "audio_system_device": "",
    "audio_mic_device": "",
    "show_cursor": True,
    "use_mini_toolbar": True,
    "use_countdown": True,
    "countdown_seconds": 3,
    "hotkey_start": "f9",
    "hotkey_pause": "f10",
    "hotkey_stop": "f11",
    "annotation_enabled": True,
    "annotation_hotkey_toggle": "ctrl+shift+d",
    "annotation_hotkey_pen": "1",
    "annotation_hotkey_highlighter": "2",
    "annotation_hotkey_arrow": "3",
    "annotation_hotkey_rect": "4",
    "annotation_hotkey_eraser": "e",
    "annotation_hotkey_clear": "ctrl+shift+c",
    "annotation_hotkey_color": "c",
    "annotation_hotkey_undo": "ctrl+z",
    "annotation_hotkey_redo": "ctrl+y",
    "annotation_default_color": "#FF3B30",
    "annotation_pen_width": 4,
    "annotation_auto_fade_seconds": 0,  # 0 = 不消失
    "ffmpeg_path": "ffmpeg",
}


def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(data)
            return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
