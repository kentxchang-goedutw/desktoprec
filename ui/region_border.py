"""錄影區域邊框顯示"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget
from core.display_utils import physical_rect_to_qt

class RegionBorderOverlay(QWidget):
    def __init__(self, rect_list):
        """rect_list: [x, y, w, h] (此時為物理像素)"""
        super().__init__()
        self.rect_list = rect_list
        self.is_recording = False
        
        lx, ly, lw, lh = physical_rect_to_qt(rect_list)
        
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
