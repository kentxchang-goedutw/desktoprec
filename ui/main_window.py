"""主視窗 - 極簡介面"""
import os
import shutil
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl, Signal, Slot, QThread
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QStatusBar, QMessageBox,
                                QApplication)

from core.config import load_config, save_config, resource_path
from core.ffmpeg_utils import find_ffmpeg, ensure_ffmpeg
from core.recorder import Recorder
from core.hotkey import HotkeyManager
from .settings_dialog import SettingsDialog
from .countdown import CountdownOverlay
from .mini_toolbar import MiniToolbar
from .annotation import AnnotationOverlay
from .webcam import WebcamOverlay
from .region_border import RegionBorderOverlay


class MainWindow(QMainWindow):
    # 定義信號以處理跨執行緒快速鍵呼叫
    sig_start = Signal()
    sig_pause = Signal()
    sig_stop = Signal()
    sig_toggle_annot = Signal()
    sig_annot_tool = Signal(str)
    sig_annot_clear = Signal()
    sig_annot_color = Signal()
    sig_annot_undo = Signal()
    sig_annot_redo = Signal()
    
    # 新增 ffmpeg 下載信號
    sig_ffmpeg_ready = Signal(str)
    sig_ffmpeg_msg = Signal(str)

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.cfg["ffmpeg_path"] = find_ffmpeg() or "ffmpeg"
        self.recorder = None
        self.mini = None
        self.annot = None
        self.webcam = None
        self.border = None
        self.hotkeys = HotkeyManager()

        # 設定視窗圖示
        icon_path = resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 連接信號
        self.sig_start.connect(self.on_start)
        self.sig_pause.connect(self.on_pause)
        self.sig_stop.connect(self.on_stop)
        self.sig_toggle_annot.connect(self.toggle_annotation)
        self.sig_annot_tool.connect(self._do_annot_set_tool)
        self.sig_annot_clear.connect(self._do_annot_clear)
        self.sig_annot_color.connect(self._do_annot_cycle_color)
        self.sig_annot_undo.connect(self._do_annot_undo)
        self.sig_annot_redo.connect(self._do_annot_redo)
        
        self.sig_ffmpeg_ready.connect(self._on_ffmpeg_ready)
        self.sig_ffmpeg_msg.connect(self._on_ffmpeg_msg)

        self.setWindowTitle("桌面錄影工具")
        self.resize(440, 360)

        cw = QWidget()
        cw.setObjectName("mainWidget")
        self.setCentralWidget(cw)

        v = QVBoxLayout(cw)
        v.setContentsMargins(32, 40, 32, 24)
        v.setSpacing(20)

        # 標題
        title = QLabel("桌面錄影工具")
        title.setObjectName("mainTitle")
        title.setAlignment(Qt.AlignCenter)
        
        sub = QLabel("一鍵錄影 · 硬體加速 · 即時標註")
        sub.setObjectName("subTitle")
        sub.setAlignment(Qt.AlignCenter)
        
        v.addWidget(title)
        v.addWidget(sub)

        v.addSpacing(15)

        # 主錄影鈕
        self.btn_record = QPushButton("●  開始錄影")
        self.btn_record.setObjectName("primaryBtn")
        self.btn_record.setMinimumHeight(80)
        self.btn_record.clicked.connect(self.on_start)
        v.addWidget(self.btn_record)

        # 停止鈕
        self.btn_stop = QPushButton("■  停止錄影")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setMinimumHeight(80)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_stop.hide()
        v.addWidget(self.btn_stop)

        # 次要按鈕
        row = QHBoxLayout()
        row.setSpacing(12)
        self.btn_open = QPushButton("📁  開啟錄影夾")
        self.btn_open.setObjectName("actionBtn")
        self.btn_open.setMinimumHeight(50)
        self.btn_open.clicked.connect(self._open_dir)
        
        self.btn_webcam_toggle = QPushButton("📷  Webcam")
        self.btn_webcam_toggle.setObjectName("actionBtn")
        self.btn_webcam_toggle.setMinimumHeight(50)
        self.btn_webcam_toggle.clicked.connect(self._on_btn_webcam_toggled)
        self._update_webcam_btn_style()

        self.btn_settings = QPushButton("⚙  設定")
        self.btn_settings.setObjectName("actionBtn")
        self.btn_settings.setMinimumHeight(50)
        self.btn_settings.clicked.connect(self.open_settings)
        
        row.addWidget(self.btn_open, 1)
        row.addWidget(self.btn_webcam_toggle, 1)
        row.addWidget(self.btn_settings, 1)
        v.addLayout(row)

        # 快速鍵提示
        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("hintLabel")
        self.lbl_hint.setAlignment(Qt.AlignCenter)
        self._refresh_hint()
        v.addWidget(self.lbl_hint)

        v.addStretch()

        # Footer
        footer = QLabel(
            '<span style="color:#888;">Made by </span>'
            '<a href="https://kentxchang.blogspot.tw" '
            'style="color:#4F8CFF; text-decoration:none; font-weight:600;">阿剛老師</a>'
            '<br>'
            '<span style="color:#666; font-size:11px;">本軟體採 </span>'
            '<a href="https://creativecommons.org/licenses/by-nc/4.0/deed.zh_TW" '
            'style="color:#4F8CFF; text-decoration:none; font-size:11px;">CC BY-NC 4.0</a>'
            '<span style="color:#666; font-size:11px;"> 姓名標示-非商業性 授權</span>'
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setOpenExternalLinks(False)
        footer.linkActivated.connect(lambda u: QDesktopServices.openUrl(QUrl(u)))
        v.addWidget(footer)

        # 狀態列
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        
        # 初始化常駐 Webcam
        self._init_webcam_persistent()
        
        # 初始化常駐錄影區域邊框
        self._update_region_border()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._register_hotkeys()

        # 初始檢查 ffmpeg
        if not find_ffmpeg():
            self.status.showMessage("⚠ 找不到 ffmpeg.exe，準備自動下載...")
        else:
            self.status.showMessage("就緒")

    def _on_ffmpeg_msg(self, msg):
        self.status.showMessage(msg)

    def _on_ffmpeg_ready(self, path):
        if path:
            self.cfg["ffmpeg_path"] = path
            self.status.showMessage("✓ ffmpeg 已就緒", 3000)
        else:
            self.status.showMessage("❌ ffmpeg 下載失敗，請檢查網路")

    def _refresh_hint(self):
        c = self.cfg
        self.lbl_hint.setText(
            f"快速鍵：開始 {c['hotkey_start'].upper()} · "
            f"暫停 {c['hotkey_pause'].upper()} · "
            f"停止 {c['hotkey_stop'].upper()} · "
            f"標註 {c['annotation_hotkey_toggle'].upper()}")
        # 移除這裡的 self.status.showMessage，因為這是在初始化時呼叫的，status 可能還沒準備好
        # 且設定儲存後的訊息應該在 _on_settings_changed 中處理

    def _on_settings_changed(self):
        self._register_hotkeys()
        self._refresh_hint()
        self.status.showMessage("✓ 設定已儲存", 3000)

    # ============ 設定 ============
    def open_settings(self):
        if self.recorder:
            QMessageBox.information(self, "提示", "請先停止錄影再開啟設定")
            return
        dlg = SettingsDialog(self.cfg, self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _on_settings_changed(self):
        self._register_hotkeys()
        self._refresh_hint()
        self._init_webcam_persistent()
        self._update_region_border()
        self.status.showMessage("✓ 設定已儲存", 3000)

    def _update_region_border(self):
        """根據設定更新常駐錄影邊框 (藍色預覽)"""
        if self.cfg.get("region_mode") == "custom" and self.cfg.get("custom_region"):
            # 如果座標沒變且已存在，就不用重開
            if self.border and self.border.rect_list == self.cfg["custom_region"]:
                self.border.set_recording_mode(False)
                self.border.show()
                return
                
            if self.border:
                self.border.close()
            
            self.border = RegionBorderOverlay(self.cfg["custom_region"])
            self.border.set_recording_mode(False)
            self.border.show()
        else:
            if self.border:
                self.border.close()
                self.border = None

    def _init_webcam_persistent(self):
        """根據設定初始化或更新常駐 Webcam"""
        enabled = self.cfg.get("webcam_enabled", False)
        if enabled:
            idx = self.cfg.get("webcam_index", 0)
            size = self.cfg.get("webcam_size", 200)
            pos = self.cfg.get("webcam_pos")

            if not self.webcam:
                self.webcam = WebcamOverlay(idx, size)
                if pos:
                    self.webcam.move(pos[0], pos[1])
                self.webcam.closed.connect(self._on_webcam_manually_closed)
                self.webcam.show()
            else:
                if self.webcam.camera_index != idx:
                    self.webcam.close()
                    self.webcam = WebcamOverlay(idx, size)
                    if pos: self.webcam.move(pos[0], pos[1])
                    self.webcam.closed.connect(self._on_webcam_manually_closed)
                    self.webcam.show()
                else:
                    self.webcam.set_overlay_size(size)
                    self.webcam.show()
        else:
            if self.webcam:
                self.webcam.close()
                self.webcam = None

    def _on_webcam_manually_closed(self):
        self.webcam = None
        self.cfg["webcam_enabled"] = False
        save_config(self.cfg)
        self._update_webcam_btn_style()

    def _on_btn_webcam_toggled(self):
        """主介面按鈕切換 Webcam"""
        is_enabled = self.cfg.get("webcam_enabled", False)
        self.cfg["webcam_enabled"] = not is_enabled
        save_config(self.cfg)
        self._init_webcam_persistent()
        self._update_webcam_btn_style()

    def _update_webcam_btn_style(self):
        """根據狀態更新按鈕外觀"""
        if self.cfg.get("webcam_enabled", False):
            self.btn_webcam_toggle.setText("📷  關閉視訊")
            self.btn_webcam_toggle.setStyleSheet("color: #FF7675; font-weight: bold;")
        else:
            self.btn_webcam_toggle.setText("📷  開啟視訊")
            self.btn_webcam_toggle.setStyleSheet("")

    def _open_dir(self):

        d = self.cfg.get("output_dir")
        Path(d).mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(d)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ============ 快速鍵 ============
    def _register_hotkeys(self):
        self.hotkeys.unregister_all()
        c = self.cfg
        self.hotkeys.register(c["hotkey_start"], self._hk_start)
        self.hotkeys.register(c["hotkey_pause"], self._hk_pause)
        self.hotkeys.register(c["hotkey_stop"], self._hk_stop)
        if c.get("annotation_enabled"):
            self.hotkeys.register(c["annotation_hotkey_toggle"], self._hk_toggle_annot)
            self.hotkeys.register(c["annotation_hotkey_pen"], lambda: self._annot_set_tool("pen"))
            self.hotkeys.register(c["annotation_hotkey_highlighter"], lambda: self._annot_set_tool("highlighter"))
            self.hotkeys.register(c["annotation_hotkey_arrow"], lambda: self._annot_set_tool("arrow"))
            self.hotkeys.register(c["annotation_hotkey_rect"], lambda: self._annot_set_tool("rect"))
            self.hotkeys.register(c["annotation_hotkey_eraser"], lambda: self._annot_set_tool("eraser"))
            self.hotkeys.register(c["annotation_hotkey_clear"], self._annot_clear)
            self.hotkeys.register(c["annotation_hotkey_color"], self._annot_cycle_color)
            self.hotkeys.register(c["annotation_hotkey_undo"], self._annot_undo)
            self.hotkeys.register(c["annotation_hotkey_redo"], self._annot_redo)

    def _hk_start(self): 
        print("[Hotkey] 觸發：開始錄影")
        self.sig_start.emit()
    def _hk_pause(self): 
        print("[Hotkey] 觸發：暫停錄影")
        self.sig_pause.emit()
    def _hk_stop(self): 
        print("[Hotkey] 觸發：停止錄影")
        self.sig_stop.emit()
    def _hk_toggle_annot(self): 
        print("[Hotkey] 觸發：切換標註")
        self.sig_toggle_annot.emit()

    def _annot_set_tool(self, t):
        self.sig_annot_tool.emit(t)

    def _annot_clear(self):
        self.sig_annot_clear.emit()

    def _annot_cycle_color(self):
        self.sig_annot_color.emit()

    def _annot_undo(self):
        self.sig_annot_undo.emit()

    def _annot_redo(self):
        self.sig_annot_redo.emit()

    @Slot(str)
    def _do_annot_set_tool(self, t):
        if self.annot:
            self.annot.set_tool(t)

    @Slot()
    def _do_annot_clear(self):
        if self.annot:
            self.annot.clear_all()

    @Slot()
    def _do_annot_cycle_color(self):
        if self.annot:
            self.annot.cycle_color()

    @Slot()
    def _do_annot_undo(self):
        if self.annot:
            self.annot.undo()

    @Slot()
    def _do_annot_redo(self):
        if self.annot:
            self.annot.redo()

    # ============ 錄影流程 ============
    @Slot()
    def on_start(self):
        print("[MainWindow] 進入 on_start")
        if self.recorder:
            print("[MainWindow] 錄影已在進行中，忽略")
            return

        # 檢查 ffmpeg
        current_ffmpeg = find_ffmpeg()
        if not current_ffmpeg:
            print("[MainWindow] 找不到 ffmpeg，開始背景下載")
            self.status.showMessage("正在背景下載 ffmpeg，請稍候...")
            
            # 使用 Thread 避免 UI 凍結
            class DownloadThread(QThread):
                finished = Signal(str)
                msg = Signal(str)
                def run(self):
                    path = ensure_ffmpeg(self.msg.emit)
                    self.finished.emit(path)
            
            self._dl_thread = DownloadThread()
            self._dl_thread.finished.connect(self.sig_ffmpeg_ready)
            self._dl_thread.msg.connect(self.sig_ffmpeg_msg)
            self._dl_thread.start()
            
            QMessageBox.information(self, "提示", "程式正在下載錄影必要的 ffmpeg 組件 (約 100MB)，下載完成後將自動開始錄影。")
            # 下載完後透過信號觸發 on_start 重新執行即可
            self.sig_ffmpeg_ready.connect(lambda p: QTimer.singleShot(500, self.on_start) if p else None, type=Qt.UniqueConnection)
            return

        self.cfg["ffmpeg_path"] = current_ffmpeg

        if self.cfg.get("region_mode") == "custom" and not self.cfg.get("custom_region"):
            print("[MainWindow] 提示：自訂區域未設定")
            QMessageBox.warning(self, "提示", "請先到「設定 → 錄影區域」框選自訂區域")
            return

        print(f"[MainWindow] 準備開始錄影，倒數模式: {self.cfg.get('use_countdown', True)}")
        if self.cfg.get("use_countdown", True):
            self._countdown = CountdownOverlay(self.cfg.get("countdown_seconds", 3))
            self._countdown.finished.connect(self._do_start_record)
            self.showMinimized()
            self._countdown.start()
            print("[MainWindow] 倒數計時器已啟動")
        else:
            self.showMinimized()
            self._do_start_record()

    def _do_start_record(self):
        print("[MainWindow] 執行 _do_start_record")
        try:
            self.recorder = Recorder(self.cfg)
            path = self.recorder.start()
            print(f"[MainWindow] Recorder 已啟動, 輸出路徑: {path}")
            self.status.showMessage(f"● 錄影中… {path}")
            self.btn_record.hide()
            self.btn_stop.show()
        except Exception as e:
            print(f"[MainWindow] 啟動失敗報錯: {e}")
            QMessageBox.critical(self, "錄影失敗", str(e))
            self.recorder = None
            self.showNormal()
            return

        if self.cfg.get("use_mini_toolbar", True):
            self.mini = MiniToolbar()
            self.mini.pause_clicked.connect(self.on_pause)
            self.mini.stop_clicked.connect(self.on_stop)
            self.mini.annotate_clicked.connect(self.toggle_annotation)
            self.mini.show()

        # 將常駐邊框切換為錄影模式 (紅色虛線)
        if self.border:
            self.border.set_recording_mode(True)

        self._timer.start(500)

    def _on_tick(self):
        if not self.recorder:
            return
        e = self.recorder.elapsed()
        if self.mini:
            self.mini.set_elapsed(e)

    @Slot()
    def on_pause(self):
        if not self.recorder:
            return
        if self.recorder.paused:
            self.recorder.resume()
            self.status.showMessage("● 錄影中…")
        else:
            self.recorder.pause()
            self.status.showMessage("⏸ 暫停（注意：ffmpeg 不真暫停，仍會錄製）")

    @Slot()
    def on_stop(self):
        if not self.recorder:
            return
        path = self.recorder.stop()
        self.recorder = None
        self._timer.stop()
        if self.mini:
            self.mini.close()
            self.mini = None
        if self.annot:
            self.annot.close_overlay()
            self.annot = None
            
        # 將邊框恢復為預覽模式 (藍色實線)
        if self.border:
            self.border.set_recording_mode(False)
            
        self.btn_stop.hide()
        self.btn_record.show()
        self.showNormal()
        self.activateWindow()
        if path and os.path.exists(path):
            self.status.showMessage(f"✓ 已儲存：{path}")
            r = QMessageBox.information(self, "完成", f"錄影已儲存：\n{path}\n\n是否開啟資料夾？",
                                        QMessageBox.Yes | QMessageBox.No)
            if r == QMessageBox.Yes:
                folder = os.path.dirname(path)
                if os.name == "nt":
                    os.startfile(folder)
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            self.status.showMessage("⚠ 錄影檔案未產生，請檢查 ffmpeg 設定")

    # ============ 標註 ============
    @Slot()
    def toggle_annotation(self):
        if self.annot:
            self.annot.close_overlay()
            self.annot = None
            if self.mini:
                self.mini.set_annotation_active(False)
            return
        if not self.cfg.get("annotation_enabled", True):
            return
        self.annot = AnnotationOverlay(
            default_color=self.cfg.get("annotation_default_color", "#FF3B30"),
            default_width=self.cfg.get("annotation_pen_width", 4),
            fade_seconds=self.cfg.get("annotation_auto_fade_seconds", 0))
        self.annot.closed.connect(self._on_annot_closed)
        self.annot.show_all()
        # 確保迷你工具列高於標註層，讓使用者可以點關閉鈕
        if self.mini:
            self.mini.set_annotation_active(True)
            self.mini.raise_()
            QTimer.singleShot(50, self.mini.raise_)
            QTimer.singleShot(200, self.mini.raise_)

    def _on_annot_closed(self):
        self.annot = None
        if self.mini:
            self.mini.set_annotation_active(False)

    def closeEvent(self, e):
        try:
            if self.recorder:
                self.recorder.stop()
        except Exception:
            pass
        self.hotkeys.unregister_all()
        save_config(self.cfg)
        super().closeEvent(e)
