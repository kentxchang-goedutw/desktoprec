"""螢幕標註層 - 畫筆 / 螢光筆 / 箭頭 / 矩形 / 橡皮擦"""
import math
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, Signal, QTimer
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                            QPainterPath, QPolygonF, QGuiApplication)
from PySide6.QtWidgets import (QWidget, QApplication, QHBoxLayout, QPushButton,
                                QFrame, QLabel)


COLORS = ["#FF3B30", "#FFD60A", "#34C759", "#0A84FF", "#FFFFFF", "#000000"]


class Stroke:
    def __init__(self, tool, color, width, points=None, start=None, end=None):
        self.tool = tool  # pen / highlighter / arrow / rect
        self.color = color
        self.width = width
        self.points = points or []
        self.start = start
        self.end = end
        self.created_ms = 0


class AnnotationToolbar(QFrame):
    tool_changed = Signal(str)
    color_changed = Signal(str)
    width_changed = Signal(int)
    clear_all = Signal()
    undo_clicked = Signal()
    redo_clicked = Signal()
    close_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("annotBar")
        # 不用 Qt.Tool，避免被同類視窗 (overlay) 覆蓋
        self.setWindowFlags(Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        bar = QFrame()
        bar.setObjectName("annotInner")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        self.tool_buttons = {}
        for tool, icon, tip in [
            ("pen", "✏️", "畫筆 (1)"),
            ("rect", "⬜", "方框 (4)"),
        ]:
            b = QPushButton(icon)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setFixedSize(36, 36)
            b.clicked.connect(lambda _=False, t=tool: self._select_tool(t))
            layout.addWidget(b)
            self.tool_buttons[tool] = b

        sep = QLabel("|")
        sep.setStyleSheet("color:rgba(255,255,255,50);")
        layout.addWidget(sep)

        self.color_buttons = []
        # 只保留紅、黃、藍
        SIMPLE_COLORS = ["#FF3B30", "#FFD60A", "#0A84FF"]
        for c in SIMPLE_COLORS:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setStyleSheet(f"background:{c}; border-radius:11px; border:2px solid rgba(255,255,255,80);")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, col=c: self.color_changed.emit(col))
            layout.addWidget(b)
            self.color_buttons.append(b)

        sep2 = QLabel("|")
        sep2.setStyleSheet("color:rgba(255,255,255,50);")
        layout.addWidget(sep2)

        for icon, sig, tip in [
            ("🗑️", self.clear_all, "清除全部"),
            ("✕", self.close_clicked, "關閉標註"),
        ]:
            b = QPushButton(icon)
            b.setFixedSize(36, 36)
            b.setToolTip(tip)
            b.clicked.connect(sig.emit)
            layout.addWidget(b)

        outer.addWidget(bar)
        self.setStyleSheet("""
            #annotInner {
                background: rgba(28,28,32,235);
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,30);
            }
            QPushButton {
                background: rgba(255,255,255,20);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover { background: rgba(255,255,255,40); }
            QPushButton:checked { background: #4F8CFF; }
        """)

        self._drag_pos = None

        # 持續置頂，避免被 overlay 蓋住造成按鈕無法點擊
        self._raise_timer = QTimer(self)
        self._raise_timer.timeout.connect(self._ensure_top)
        self._raise_timer.start(500)

    def _ensure_top(self):
        if self.isVisible():
            self.raise_()

    def _select_tool(self, tool):
        for k, b in self.tool_buttons.items():
            b.setChecked(k == tool)
        self.tool_changed.emit(tool)

    def set_active_tool(self, tool):
        for k, b in self.tool_buttons.items():
            b.setChecked(k == tool)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


class AnnotationOverlay(QWidget):
    closed = Signal()

    def __init__(self, default_color="#FF3B30", default_width=4, fade_seconds=0):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        screen = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        self.tool = "pen"
        self.color = default_color
        self.width_ = default_width
        self.fade_seconds = fade_seconds

        self.strokes = []
        self.redo_stack = []
        self.current = None
        self.drawing = False

        self._color_idx = 0

        # 工具列
        self.toolbar = AnnotationToolbar()
        self.toolbar.tool_changed.connect(self.set_tool)
        self.toolbar.color_changed.connect(self.set_color)
        self.toolbar.width_changed.connect(self.set_width)
        self.toolbar.clear_all.connect(self.clear_all)
        self.toolbar.undo_clicked.connect(self.undo)
        self.toolbar.redo_clicked.connect(self.redo)
        self.toolbar.close_clicked.connect(self.close_overlay)
        self.toolbar.set_active_tool(self.tool)

        sg = screen
        self.toolbar.adjustSize()
        self.toolbar.move(sg.center().x() - self.toolbar.width() // 2, sg.top() + 20)

        # 自動消失計時器
        if fade_seconds > 0:
            self.fade_timer = QTimer(self)
            self.fade_timer.timeout.connect(self._fade_check)
            self.fade_timer.start(500)
            self._tick = 0
        else:
            self.fade_timer = None

    def show_all(self):
        self.show()
        self.raise_()
        # 工具列必須最後 raise，確保在 overlay 之上以接收點擊
        self.toolbar.show()
        self.toolbar.raise_()

    def close_overlay(self):
        self.toolbar.close()
        self.close()
        self.closed.emit()

    # ---- 工具設定 ----
    def set_tool(self, tool):
        self.tool = tool
        self.toolbar.set_active_tool(tool)

    def set_color(self, c):
        self.color = c

    def cycle_color(self):
        self._color_idx = (self._color_idx + 1) % len(COLORS)
        self.color = COLORS[self._color_idx]

    def set_width(self, w):
        self.width_ = w

    # ---- 操作 ----
    def clear_all(self):
        self.strokes.clear()
        self.redo_stack.clear()
        self.update()

    def undo(self):
        if self.strokes:
            self.redo_stack.append(self.strokes.pop())
            self.update()

    def redo(self):
        if self.redo_stack:
            self.strokes.append(self.redo_stack.pop())
            self.update()

    def _fade_check(self):
        self._tick += 1
        # 簡化：每 fade_seconds 秒清除最舊筆畫
        if self._tick * 0.5 >= self.fade_seconds and self.strokes:
            self.strokes.pop(0)
            self._tick = 0
            self.update()

    # ---- 滑鼠事件 ----
    def _is_over_toolbar(self, global_pos):
        """檢查滑鼠是否在標註工具列上 (避免在工具列上繪圖)"""
        try:
            if self.toolbar.isVisible() and self.toolbar.geometry().contains(global_pos):
                return True
        except Exception:
            pass
        return False

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        gp = e.globalPosition().toPoint()
        if self._is_over_toolbar(gp):
            # 點到工具列範圍 → 把事件交給工具列
            self.toolbar.raise_()
            return
        self.drawing = True
        pos = e.position().toPoint()
        if self.tool == "eraser":
            self._erase_at(pos)
            return
        if self.tool in ("pen", "highlighter"):
            self.current = Stroke(self.tool, self.color, self.width_, points=[pos])
        else:  # arrow / rect
            self.current = Stroke(self.tool, self.color, self.width_, start=pos, end=pos)
        self.update()

    def mouseMoveEvent(self, e):
        if not self.drawing:
            return
        pos = e.position().toPoint()
        if self.tool == "eraser":
            self._erase_at(pos)
        elif self.tool in ("pen", "highlighter") and self.current:
            self.current.points.append(pos)
        elif self.current:
            self.current.end = pos
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self.drawing = False
        if self.current:
            self.strokes.append(self.current)
            self.redo_stack.clear()
            self.current = None
        self.update()

    def _erase_at(self, pos):
        # 移除位置附近的筆畫
        radius = 20
        new_strokes = []
        for s in self.strokes:
            hit = False
            if s.tool in ("pen", "highlighter"):
                for pt in s.points:
                    if (pt - pos).manhattanLength() < radius:
                        hit = True
                        break
            else:
                r = QRect(s.start, s.end).normalized().adjusted(-5, -5, 5, 5)
                if r.contains(pos):
                    hit = True
            if not hit:
                new_strokes.append(s)
        self.strokes = new_strokes

    # ---- 繪製 ----
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 透明背景，但需有可點擊區
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        for s in self.strokes:
            self._draw_stroke(p, s)
        if self.current:
            self._draw_stroke(p, self.current)

    def _draw_stroke(self, p, s):
        col = QColor(s.color)
        if s.tool == "highlighter":
            col.setAlpha(90)
            pen = QPen(col, max(s.width * 4, 14), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        else:
            pen = QPen(col, s.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if s.tool in ("pen", "highlighter"):
            if len(s.points) > 1:
                path = QPainterPath(QPointF(s.points[0]))
                for pt in s.points[1:]:
                    path.lineTo(QPointF(pt))
                p.drawPath(path)
            elif s.points:
                p.drawPoint(s.points[0])
        elif s.tool == "rect":
            r = QRect(s.start, s.end).normalized()
            p.drawRect(r)
        elif s.tool == "arrow":
            self._draw_arrow(p, s.start, s.end, s.width)

    def _draw_arrow(self, p, start, end, width):
        p.drawLine(start, end)
        # 箭頭頭部
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        size = 10 + width * 2
        a1 = angle + math.radians(150)
        a2 = angle - math.radians(150)
        p1 = QPointF(end.x() + size * math.cos(a1), end.y() + size * math.sin(a1))
        p2 = QPointF(end.x() + size * math.cos(a2), end.y() + size * math.sin(a2))
        poly = QPolygonF([QPointF(end), p1, p2])
        p.setBrush(QBrush(p.pen().color()))
        p.drawPolygon(poly)
