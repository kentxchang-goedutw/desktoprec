"""全域快速鍵管理"""
import threading

try:
    import keyboard
    HAS_KEYBOARD = True
except Exception:
    HAS_KEYBOARD = False


class HotkeyManager:
    def __init__(self):
        self._handles = []

    def register(self, hotkey, callback):
        if not HAS_KEYBOARD or not hotkey:
            return None
        try:
            print(f"[Hotkey] 嘗試註冊: {hotkey}")
            h = keyboard.add_hotkey(hotkey, callback, suppress=False)
            self._handles.append(h)
            print(f"[Hotkey] 註冊成功: {hotkey}")
            return h
        except Exception as e:
            print(f"[Hotkey] 註冊失敗 {hotkey}: {e}")
            return None

    def unregister_all(self):
        if not HAS_KEYBOARD:
            return
        for h in self._handles:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self._handles.clear()
