"""3 秒倒數全螢幕動畫"""
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, Signal
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import QWidget, QApplication


class CountdownOverlay(QWidget):
    finished = Signal()

    def __init__(self, seconds=3):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.total = seconds
        self.current = seconds
        self._scale = 1.0
        self._opacity = 1.0

        self.anim = QPropertyAnimation(self, b"scale")
        self.anim.setDuration(900)
        self.anim.setStartValue(0.4)
        self.anim.setEndValue(1.6)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

        self.fade = QPropertyAnimation(self, b"opacity")
        self.fade.setDuration(900)
        self.fade.setStartValue(1.0)
        self.fade.setEndValue(0.0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def get_scale(self): return self._scale
    def set_scale(self, v):
        self._scale = v
        self.update()
    scale = Property(float, get_scale, set_scale)

    def get_opacity(self): return self._opacity
    def set_opacity(self, v):
        self._opacity = v
        self.update()
    opacity = Property(float, get_opacity, set_opacity)

    def start(self):
        self.show()
        self._begin_step()
        self.timer.start(1000)

    def _begin_step(self):
        self._scale = 0.4
        self._opacity = 1.0
        self.anim.start()
        self.fade.start()

    def _tick(self):
        self.current -= 1
        if self.current <= 0:
            self.timer.stop()
            self.close()
            self.finished.emit()
            return
        self._begin_step()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 140))
        p.setOpacity(self._opacity)
        size = int(220 * self._scale)
        f = QFont("Segoe UI", size, QFont.Black)
        p.setFont(f)
        p.setPen(QColor("#4F8CFF"))
        rect = self.rect()
        p.drawText(rect, Qt.AlignCenter, str(self.current))
