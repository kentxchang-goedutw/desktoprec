"""自訂區塊框選"""
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget, QApplication


class RegionSelector(QWidget):
    region_selected = Signal(int, int, int, int)  # x, y, w, h
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        screen = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(screen)
        self.start = None
        self.end = None
        self.selecting = False

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if self.start and self.end:
            r = QRect(self.start, self.end).normalized()
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(r, Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor("#4F8CFF"), 2)
            p.setPen(pen)
            p.drawRect(r)
            # 尺寸文字
            txt = f"{r.width()} × {r.height()}"
            p.setFont(QFont("Segoe UI", 12, QFont.Bold))
            p.setPen(QColor("white"))
            p.fillRect(r.x(), r.y() - 26, 120, 22, QColor(0, 0, 0, 180))
            p.drawText(r.x() + 6, r.y() - 10, txt)
        # 提示
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 14))
        p.drawText(self.rect().center().x() - 200, 40,
                   "拖曳選擇錄影區域 — Enter 確認 / Esc 取消")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.start = e.pos()
            self.end = e.pos()
            self.selecting = True
            self.update()

    def mouseMoveEvent(self, e):
        if self.selecting:
            self.end = e.pos()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.selecting:
            self.end = e.pos()
            self.selecting = False
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.start and self.end:
                r = QRect(self.start, self.end).normalized()
                if r.width() > 10 and r.height() > 10:
                    g = self.geometry()
                    self.region_selected.emit(
                        r.x() + g.x(), r.y() + g.y(),
                        r.width(), r.height())
                    self.close()
