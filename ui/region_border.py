"""錄影區域邊框顯示"""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget, QApplication

class RegionBorderOverlay(QWidget):
    def __init__(self, rect_list):
        """rect_list: [x, y, w, h] (此時為物理像素)"""
        super().__init__()
        self.rect_list = rect_list
        self.is_recording = False
        
        # 考慮高 DPI：將物理像素轉回 Qt 的邏輯單位以設定視窗位置
        ratio = QApplication.primaryScreen().devicePixelRatio()
        lx, ly = rect_list[0] / ratio, rect_list[1] / ratio
        lw, lh = rect_list[2] / ratio, rect_list[3] / ratio
        
        # 邊框稍微往外擴一點
        self.offset = 2
        self.setGeometry(lx - self.offset, ly - self.offset, lw + self.offset * 2, lh + self.offset * 2)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_recording_mode(self, is_recording):
        """切換藍色預覽或紅色錄影模式"""
        self.is_recording = is_recording
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.is_recording:
            # 錄影中：紅色粗虛線
            pen = QPen(QColor(255, 71, 87, 220)) 
            pen.setWidth(4)
            pen.setStyle(Qt.DashLine)
        else:
            # 預覽中：藍色實線
            pen = QPen(QColor(72, 52, 212, 180)) 
            pen.setWidth(3)
            pen.setStyle(Qt.SolidLine)
            
        painter.setPen(pen)
        # 畫在邊框內部
        painter.drawRect(self.rect().adjusted(2, 2, -2, -2))
