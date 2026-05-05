"""錄影中迷你工具列 - 文字+圖示，更易辨識"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QPushButton, QLabel,
                                QFrame, QApplication)


class MiniToolbar(QWidget):
    pause_clicked = Signal()
    stop_clicked = Signal()
    annotate_clicked = Signal()

    def __init__(self):
        super().__init__()
        # 不使用 Qt.Tool，避免被其他 Tool 視窗 (annotation) 覆蓋
        self.setWindowFlags(Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._drag_pos = None
        self._paused = False
        self._elapsed = 0
        self._annot_active = False

        self.container = QFrame(self)
        self.container.setObjectName("miniBar")
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # 紅點 (錄影指示)
        self.dot = QLabel("●")
        self.dot.setObjectName("recDot")

        # 時間
        self.time_label = QLabel("00:00")
        self.time_label.setObjectName("recTime")

        # 分隔線
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: rgba(255,255,255,40);")
        sep.setFixedHeight(16)

        # 標註鈕（圖示 + 文字）
        self.btn_annot = QPushButton("✏ 標註")
        self.btn_annot.setObjectName("miniBtn")
        self.btn_annot.setCheckable(True)
        self.btn_annot.setToolTip("開啟/關閉螢幕標註")
        self.btn_annot.clicked.connect(self.annotate_clicked.emit)

        # 暫停鈕
        self.btn_pause = QPushButton("⏸ 暫停")
        self.btn_pause.setObjectName("miniBtn")
        self.btn_pause.setToolTip("暫停 / 繼續錄影")
        self.btn_pause.clicked.connect(self._on_pause)

        # 停止鈕（紅）
        self.btn_stop = QPushButton("■ 停止")
        self.btn_stop.setObjectName("miniStop")
        self.btn_stop.setToolTip("停止錄影並儲存")
        self.btn_stop.clicked.connect(self.stop_clicked.emit)

        for b in (self.btn_annot, self.btn_pause, self.btn_stop):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(24)

        layout.addWidget(self.dot)
        layout.addWidget(self.time_label)
        layout.addWidget(sep)
        layout.addWidget(self.btn_annot)
        layout.addWidget(self.btn_pause)
        layout.addWidget(self.btn_stop)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.container)

        self.setStyleSheet("""
            #miniBar {
                background: rgba(28,28,32,235);
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,40);
            }
            #recDot {
                color: #FF3B30;
                font-size: 14px;
            }
            #recTime {
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 700;
                font-family: "Consolas", "Segoe UI", sans-serif;
                min-width: 42px;
            }
            QPushButton#miniBtn {
                background: rgba(255,255,255,28);
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#miniBtn:hover {
                background: rgba(255,255,255,55);
            }
            QPushButton#miniBtn:checked {
                background: #4F8CFF;
                color: #FFFFFF;
            }
            QPushButton#miniStop {
                background: #FF3B30;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#miniStop:hover {
                background: #FF5040;
            }
        """)

        # 紅點閃爍
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._blink)
        self.blink_timer.start(600)
        self._dot_on = True

        # 持續置頂計時器（避免標註層蓋過）
        self._raise_timer = QTimer(self)
        self._raise_timer.timeout.connect(self._ensure_top)
        self._raise_timer.start(800)

        # 預設右上角
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.right() - self.width() - 30, screen.top() + 30)

    def _on_pause(self):
        self._paused = not self._paused
        self.btn_pause.setText("▶  繼續" if self._paused else "⏸  暫停")
        self.pause_clicked.emit()

    def set_annotation_active(self, active):
        self._annot_active = active
        self.btn_annot.setChecked(active)
        self.btn_annot.setText("✕  關閉標註" if active else "✏  標註")

    def set_elapsed(self, seconds):
        self._elapsed = int(seconds)
        m, s = divmod(self._elapsed, 60)
        h, m = divmod(m, 60)
        if h:
            self.time_label.setText(f"{h:02d}:{m:02d}:{s:02d}")
        else:
            self.time_label.setText(f"{m:02d}:{s:02d}")

    def _blink(self):
        if self._paused:
            self.dot.setStyleSheet("color: #FFD60A; font-size: 18px;")
            return
        self._dot_on = not self._dot_on
        self.dot.setStyleSheet(
            f"color: {'#FF3B30' if self._dot_on else 'rgba(255,59,48,80)'}; font-size: 18px;")

    def _ensure_top(self):
        """持續確保在最上層，避免被標註層蓋住"""
        if self.isVisible():
            self.raise_()

    # 拖曳
    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
