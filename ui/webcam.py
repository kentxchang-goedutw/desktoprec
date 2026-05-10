"""Webcam 圓形懸浮視窗"""
import cv2
import sys
from PySide6.QtCore import Qt, QTimer, QPoint, QRect, Signal
from PySide6.QtGui import QImage, QPixmap, QPainter, QBrush, QColor, QPen, QRegion, QPainterPath, QAction
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMenu

class WebcamOverlay(QWidget):
    closed = Signal() # 當視窗被關閉時發送信號

    def __init__(self, camera_index=0, size=200, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.target_size = size
        
        # 設定視窗屬性：無邊框、最上層、工具視窗
        # 關鍵：加上 Qt.Window 讓它即使有 parent 也能作為獨立視窗移動，且能繞過 parent 的模態鎖定
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setFixedSize(size, size)
        
        self.lbl_video = QLabel(self)
        self.lbl_video.setFixedSize(size, size)
        
        # OpenCV 設定
        if sys.platform == "win32":
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(self.camera_index)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        
        # 拖曳功能
        self._dragging = False
        self._drag_pos = QPoint()

    def set_overlay_size(self, size):
        self.target_size = size
        self.setFixedSize(size, size)
        self.lbl_video.setFixedSize(size, size)
        self.update_mask()

    def update_mask(self):
        # 建立圓形遮罩
        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    def showEvent(self, event):
        super().showEvent(event)
        self.update_mask()
        self.timer.start(33) # ~30 FPS

    def closeEvent(self, event):
        self.timer.stop()
        if self.cap:
            self.cap.release()
        self.closed.emit()
        super().closeEvent(event)

    def contextMenuEvent(self, event):
        """右鍵選單以利關閉"""
        menu = QMenu(self)
        close_action = QAction("關閉預覽", self)
        close_action.triggered.connect(self.close)
        menu.addAction(close_action)
        menu.exec(event.globalPos())

    def _update_frame(self):
        ret, frame = self.cap.read()
        if ret:
            # 轉換為 RGB 並縮放成正方形（取中間）
            h, w = frame.shape[:2]
            min_dim = min(h, w)
            start_x = (w - min_dim) // 2
            start_y = (h - min_dim) // 2
            crop = frame[start_y:start_y+min_dim, start_x:start_x+min_dim]
            
            # 轉換顏色空間 OpenCV (BGR) -> Qt (RGB)
            frame_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            
            # 縮放影像
            frame_resized = cv2.resize(frame_rgb, (self.target_size, self.target_size))
            
            img = QImage(frame_resized.data, self.target_size, self.target_size, 
                         self.target_size * 3, QImage.Format_RGB888)
            self.lbl_video.setPixmap(QPixmap.fromImage(img))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
