"""桌面錄影工具 — 入口
Made by 阿剛老師  https://kentxchang.blogspot.tw
授權：CC BY-NC 4.0
"""
import sys
import os
from pathlib import Path

# 確保模組可被匯入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from core.config import load_config, save_config, resource_path
from core.ffmpeg_utils import find_ffmpeg, ensure_ffmpeg
from ui.main_window import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    font_family = "PingFang TC" if sys.platform == "darwin" else "Microsoft JhengHei UI"
    app.setFont(QFont(font_family, 10))

    qss_path = resource_path(os.path.join("ui", "styles.qss"))
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    w = MainWindow()

    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
