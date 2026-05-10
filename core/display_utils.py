"""Display geometry helpers for screen capture coordinates."""
import sys


def _union_rect(rects):
    if not rects:
        return [0, 0, 0, 0]
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[0] + r[2] for r in rects)
    bottom = max(r[1] + r[3] for r in rects)
    return [left, top, right - left, bottom - top]


def _windows_monitor_rects():
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        rects = []

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        monitor_enum_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(RECT),
            wintypes.LPARAM,
        )

        def callback(_monitor, _dc, rect, _data):
            r = rect.contents
            rects.append([r.left, r.top, r.right - r.left, r.bottom - r.top])
            return True

        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, monitor_enum_proc(callback), 0
        )
        return rects
    except Exception:
        return []


def qt_monitor_rects():
    try:
        from PySide6.QtWidgets import QApplication

        rects = []
        for screen in QApplication.screens():
            g = screen.geometry()
            ratio = screen.devicePixelRatio()
            rects.append([
                int(round(g.x() * ratio)),
                int(round(g.y() * ratio)),
                int(round(g.width() * ratio)),
                int(round(g.height() * ratio)),
            ])
        return rects
    except Exception:
        return []


def monitor_rects():
    """Return monitor rectangles in physical desktop pixels."""
    return _windows_monitor_rects() or qt_monitor_rects()


def virtual_rect():
    """Return the full virtual desktop rectangle in physical pixels."""
    rects = monitor_rects()
    if rects:
        return _union_rect(rects)
    return [0, 0, 0, 0]


def normalize_capture_region(region):
    """Clamp a capture region to the virtual desktop and keep even dimensions."""
    if not region:
        return None
    x, y, w, h = [int(round(v)) for v in region]
    if w < 0:
        x += w
        w = -w
    if h < 0:
        y += h
        h = -h

    vx, vy, vw, vh = virtual_rect()
    if vw > 0 and vh > 0:
        left = max(x, vx)
        top = max(y, vy)
        right = min(x + w, vx + vw)
        bottom = min(y + h, vy + vh)
        if right <= left or bottom <= top:
            return [vx, vy, 2, 2]
        x, y = left, top
        w, h = right - left, bottom - top

    w = max(2, (w // 2) * 2)
    h = max(2, (h // 2) * 2)
    return [x, y, w, h]


def qt_rect_to_physical(x, y, w, h):
    """Convert a Qt logical selection rectangle to physical desktop pixels."""
    try:
        from PySide6.QtCore import QRect, QPoint
        from PySide6.QtWidgets import QApplication

        logical = QRect(int(x), int(y), int(w), int(h)).normalized()
        screens = QApplication.screens()
        physical_monitors = monitor_rects()

        # Preserve monitor order: Qt screens and EnumDisplayMonitors are normally
        # reported in the same desktop order. If a selection is inside one screen,
        # convert from that screen's local logical coordinates to its physical rect.
        for idx, screen in enumerate(screens):
            sg = screen.geometry()
            if sg.contains(logical.topLeft()) and sg.contains(logical.bottomRight()):
                ratio = screen.devicePixelRatio()
                if idx < len(physical_monitors):
                    px, py, _, _ = physical_monitors[idx]
                else:
                    px = int(round(sg.x() * ratio))
                    py = int(round(sg.y() * ratio))
                return normalize_capture_region([
                    px + int(round((logical.x() - sg.x()) * ratio)),
                    py + int(round((logical.y() - sg.y()) * ratio)),
                    int(round(logical.width() * ratio)),
                    int(round(logical.height() * ratio)),
                ])

        center_screen = QApplication.screenAt(QPoint(logical.center()))
        ratio = center_screen.devicePixelRatio() if center_screen else 1
        return normalize_capture_region([
            int(round(logical.x() * ratio)),
            int(round(logical.y() * ratio)),
            int(round(logical.width() * ratio)),
            int(round(logical.height() * ratio)),
        ])
    except Exception:
        return normalize_capture_region([x, y, w, h])


def physical_rect_to_qt(region):
    """Convert a physical capture rectangle back to Qt logical coordinates."""
    x, y, w, h = normalize_capture_region(region)
    try:
        from PySide6.QtWidgets import QApplication

        screens = QApplication.screens()
        physical_monitors = monitor_rects()
        for idx, mon in enumerate(physical_monitors):
            mx, my, mw, mh = mon
            if x >= mx and y >= my and x + w <= mx + mw and y + h <= my + mh:
                if idx < len(screens):
                    sg = screens[idx].geometry()
                    ratio = screens[idx].devicePixelRatio()
                    return [
                        sg.x() + int(round((x - mx) / ratio)),
                        sg.y() + int(round((y - my) / ratio)),
                        int(round(w / ratio)),
                        int(round(h / ratio)),
                    ]

        ratio = QApplication.primaryScreen().devicePixelRatio()
        return [
            int(round(x / ratio)),
            int(round(y / ratio)),
            int(round(w / ratio)),
            int(round(h / ratio)),
        ]
    except Exception:
        return [x, y, w, h]
