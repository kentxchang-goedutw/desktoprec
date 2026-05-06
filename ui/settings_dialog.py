"""設定對話框 - 分頁式"""
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (QDialog, QTabWidget, QVBoxLayout, QHBoxLayout,
                                QGridLayout, QWidget, QLabel, QPushButton,
                                QComboBox, QCheckBox, QRadioButton, QSlider,
                                QSpinBox, QLineEdit, QButtonGroup, QFileDialog,
                                QFrame, QMessageBox, QApplication)

from core.config import save_config, DEFAULT_CONFIG
from core.ffmpeg_utils import (detect_encoders, list_audio_devices,
                                list_audio_via_sounddevice, diagnose_audio_devices)
from core.hotkey import HAS_KEYBOARD
import sys
from .region_selector import RegionSelector

try:
    import pygetwindow as gw
    HAS_GW = True
except Exception:
    HAS_GW = False

try:
    import cv2
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

try:
    from pygrabber.dshow_graph import FilterGraph
    HAS_PYGRABBER = True
except Exception:
    HAS_PYGRABBER = False

# 自定義快速鍵錄製元件
class HotkeyLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self.setPlaceholderText("請按下快速鍵組合...")
        self.setStyleSheet("background-color: #f0f0f0; font-weight: bold; color: #333;")

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        
        # 忽略單獨的修飾鍵
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.ControlModifier: parts.append("ctrl")
        if modifiers & Qt.ShiftModifier: parts.append("shift")
        if modifiers & Qt.AltModifier: parts.append("alt")
        if modifiers & Qt.MetaModifier: parts.append("windows")

        # 獲取主要按鍵名稱
        key_name = QKeySequence(key).toString().lower()
        
        # 修正某些按鍵名稱以符合 keyboard 庫
        mapping = {
            "backspace": "backspace",
            "return": "enter",
            "enter": "enter",
            "esc": "esc",
            "ins": "insert",
            "del": "delete",
            "pgup": "page up",
            "pgdown": "page down",
            "left": "left",
            "right": "right",
            "up": "up",
            "down": "down",
        }
        key_name = mapping.get(key_name, key_name)
        
        if key_name:
            parts.append(key_name)
            self.setText("+".join(parts))

def make_card(title, parent=None):
    f = QFrame(parent)
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(10)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        v.addWidget(lbl)
    return f, v


class SettingsDialog(QDialog):
    settings_changed = Signal()  # 通知主視窗重新註冊快速鍵等

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("設定")
        self.setFixedWidth(560)
        self.setMinimumHeight(620)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_region(), "錄影區域")
        self.tabs.addTab(self._tab_video(), "畫質/編碼")
        self.tabs.addTab(self._tab_audio(), "音訊")
        self.tabs.addTab(self._tab_webcam(), "Webcam")
        self.tabs.addTab(self._tab_hotkey(), "快速鍵")
        self.tabs.addTab(self._tab_annot(), "標註")
        self.tabs.addTab(self._tab_output(), "輸出")
        
        # 監聽分頁切換，實現延遲載入以加速啟動
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        outer.addWidget(self.tabs, 1)

        # 底部按鈕
        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton("儲存")
        ok.setObjectName("primaryBtn")
        ok.clicked.connect(self.accept_and_save)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        outer.addLayout(btns)

        self._load_audio_devices()

    def _on_tab_changed(self, index):
        """當切換到特定分頁時才載入耗時資源"""
        title = self.tabs.tabText(index)
        if title == "Webcam":
            if self.cb_cam_dev.count() <= 1: # 只有預設或空才更新
                self._refresh_cams()

    # ============ 錄影區域 ============
    def _tab_region(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        card, cv = make_card("區域類型")
        self.rb_full = QRadioButton("全螢幕")
        self.rb_custom = QRadioButton("自訂區塊")
        bg = QButtonGroup(self)
        for b in (self.rb_full, self.rb_custom):
            bg.addButton(b)
        m = self.cfg.get("region_mode", "fullscreen")
        if m == "window": m = "fullscreen" # 修正舊設定
        {"fullscreen": self.rb_full, "custom": self.rb_custom}[m].setChecked(True)
        cv.addWidget(self.rb_full)

        h_cus = QHBoxLayout()
        h_cus.addWidget(self.rb_custom)
        self.lbl_region = QLabel(self._region_text())
        bp = QPushButton("框選區域")
        bp.clicked.connect(self._pick_region)
        h_cus.addWidget(self.lbl_region, 1)
        h_cus.addWidget(bp)
        cv.addLayout(h_cus)

        self.cb_cursor = QCheckBox("錄影時顯示滑鼠游標")
        self.cb_cursor.setChecked(self.cfg.get("show_cursor", True))
        cv.addWidget(self.cb_cursor)

        v.addWidget(card)
        v.addStretch()
        return w

    def _refresh_windows(self):
        self.cb_window.clear()
        if not HAS_GW:
            self.cb_window.addItem("(未安裝 pygetwindow)")
            return
        try:
            seen = set()
            for win in gw.getAllWindows():
                if win.title and win.visible and win.width > 100 and win.title not in seen:
                    self.cb_window.addItem(win.title)
                    seen.add(win.title)
        except Exception:
            pass
        cur = self.cfg.get("window_title", "")
        if cur:
            i = self.cb_window.findText(cur)
            if i >= 0:
                self.cb_window.setCurrentIndex(i)

    def _region_text(self):
        r = self.cfg.get("custom_region")
        return f"已選: {r[0]},{r[1]}  {r[2]}×{r[3]}" if r else "尚未框選"

    def _pick_region(self):
        self.hide()
        QApplication.processEvents()
        self._picker = RegionSelector()
        self._picker.region_selected.connect(self._on_region_selected)
        self._picker.cancelled.connect(self.show)
        self._picker.show()

    def _on_region_selected(self, x, y, w, h):
        # 考慮高 DPI 縮放：Qt 傳回的是邏輯單位，FFmpeg 需要的是實際像素
        screen = QApplication.primaryScreen()
        ratio = screen.devicePixelRatio()
        
        # 轉換為真實像素座標
        px, py = int(x * ratio), int(y * ratio)
        pw, ph = int(w * ratio), int(h * ratio)
        
        self.cfg["custom_region"] = [px, py, pw, ph]
        self.cfg["region_mode"] = "custom"
        self.lbl_region.setText(f"已選: {px},{py} {pw}×{ph} (px)")
        self.rb_custom.setChecked(True)
        
        # 自動儲存
        save_config(self.cfg)
        
        self.show()
        self.activateWindow()
        self.raise_()

    # ============ 畫質 / 編碼 ============
    def _tab_video(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        c1, cv1 = make_card("畫質與 FPS")
        g1 = QGridLayout()
        g1.setColumnStretch(1, 1)
        
        g1.addWidget(QLabel("解析度"), 0, 0)
        self.cb_res = QComboBox()
        self.cb_res.addItems(["原始", "1080p", "720p", "480p"])
        self.cb_res.setCurrentText(self.cfg.get("resolution", "原始"))
        g1.addWidget(self.cb_res, 0, 1)

        g1.addWidget(QLabel("FPS"), 1, 0)
        self.sp_fps = QSpinBox()
        self.sp_fps.setRange(5, 120)
        self.sp_fps.setValue(self.cfg.get("fps", 30))
        g1.addWidget(self.sp_fps, 1, 1)

        g1.addWidget(QLabel("輸出格式"), 2, 0)
        self.cb_container = QComboBox()
        self.cb_container.addItems(["mp4", "mkv"])
        self.cb_container.setCurrentText(self.cfg.get("container", "mp4"))
        g1.addWidget(self.cb_container, 2, 1)
        
        cv1.addLayout(g1)
        v.addWidget(c1)

        c2, cv2 = make_card("編碼器（硬體加速）")
        g2 = QGridLayout()
        g2.setColumnStretch(1, 1)

        g2.addWidget(QLabel("編碼器"), 0, 0)
        self.cb_encoder = QComboBox()
        self._encoders = detect_encoders(self.cfg.get("ffmpeg_path", "ffmpeg"))
        for label, key in self._encoders:
            self.cb_encoder.addItem(label, key)
        cur = self.cfg.get("encoder", "auto")
        idx = 0
        found = False
        for i, (_, k) in enumerate(self._encoders):
            if k == cur:
                idx = i
                found = True
                break
        if not found:
            for i, (_, k) in enumerate(self._encoders):
                if any(x in k for x in ("nvenc", "qsv", "amf")):
                    idx = i
                    break
        self.cb_encoder.setCurrentIndex(idx)
        g2.addWidget(self.cb_encoder, 0, 1)

        g2.addWidget(QLabel("品質模式"), 1, 0)
        self.cb_qmode = QComboBox()
        self.cb_qmode.addItems(["CRF (固定品質)", "VBR (可變位元率)", "CBR (固定位元率)"])
        qmap = {"CRF": 0, "VBR": 1, "CBR": 2}
        self.cb_qmode.setCurrentIndex(qmap.get(self.cfg.get("quality_mode", "CRF"), 0))
        g2.addWidget(self.cb_qmode, 1, 1)

        g2.addWidget(QLabel("CRF / CQ"), 2, 0)
        h = QHBoxLayout()
        self.sl_crf = QSlider(Qt.Horizontal)
        self.sl_crf.setRange(15, 35)
        self.sl_crf.setValue(self.cfg.get("crf", 23))
        self.lbl_crf = QLabel(str(self.sl_crf.value()))
        self.sl_crf.valueChanged.connect(lambda x: self.lbl_crf.setText(str(x)))
        h.addWidget(self.sl_crf, 1)
        h.addWidget(self.lbl_crf)
        g2.addLayout(h, 2, 1)

        g2.addWidget(QLabel("位元率"), 3, 0)
        self.le_bitrate = QLineEdit(self.cfg.get("bitrate", "5M"))
        self.le_bitrate.setFixedWidth(80)
        g2.addWidget(self.le_bitrate, 3, 1)

        tip = QLabel("⚡ 硬體加速可降低 60–80% CPU 使用率")
        tip.setStyleSheet("color:#7BB6FF; font-size:11px;")
        cv2.addLayout(g2)
        cv2.addWidget(tip)
        v.addWidget(c2)
        v.addStretch()
        return w

    # ============ 音訊 ============
    def _tab_audio(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        card, cv = make_card("音訊來源")

        head = QHBoxLayout()
        self.lbl_audio_status = QLabel("")
        self.lbl_audio_status.setStyleSheet("color:#7BB6FF; font-size:11px;")
        b1 = QPushButton("🔄 重新偵測")
        b1.clicked.connect(self._load_audio_devices)
        b2 = QPushButton("診斷")
        b2.clicked.connect(self._show_audio_diag)
        head.addWidget(self.lbl_audio_status, 1)
        head.addWidget(b2)
        head.addWidget(b1)
        cv.addLayout(head)

        self.cb_sys_audio = QCheckBox("錄製系統聲音 (使用預設回放)")
        self.cb_sys_audio.setChecked(self.cfg.get("audio_system", False))
        
        self.cb_mic_audio = QCheckBox("錄製麥克風")
        self.cb_mic_audio.setChecked(self.cfg.get("audio_mic", False))
        self.cb_mic = QComboBox()
        
        cv.addWidget(self.cb_sys_audio)
        cv.addSpacing(10)
        cv.addWidget(self.cb_mic_audio)
        cv.addWidget(self.cb_mic)

        if sys.platform == "darwin":
            tip = QLabel("提示：macOS 錄製系統聲音通常需要安裝 BlackHole 等虛擬音效卡。")
        else:
            tip = QLabel("提示：系統聲音會自動尋找「立體聲混音」等裝置。")
        tip.setStyleSheet("color:#888; font-size:11px;")
        cv.addWidget(tip)
        v.addWidget(card)
        v.addStretch()
        return w

    def _load_audio_devices(self):
        self._detected_sys_device = None
        self.cb_mic.clear()
        try:
            devs = list_audio_devices(self.cfg.get("ffmpeg_path", "ffmpeg"))
        except Exception:
            devs = []
        if not devs:
            devs = list_audio_via_sounddevice()

        if not devs:
            self.lbl_audio_status.setText("⚠ 未偵測到音訊裝置")
        else:
            self.lbl_audio_status.setText(f"✓ 偵測到 {len(devs)} 個裝置")

        if not devs:
            self.cb_mic.addItem("(無裝置)")
            return
        
        for d in devs:
            self.cb_mic.addItem(d)
        
        # 尋找系統音裝置
        for d in devs:
            if any(k in d.lower() for k in ("stereo mix", "立體聲混音", "loopback", "blackhole")):
                self._detected_sys_device = d
                break
        
        # 麥克風預選
        for i, d in enumerate(devs):
            if any(k in d.lower() for k in ("mic", "麥克風", "microphone")):
                self.cb_mic.setCurrentIndex(i)
                break
        if self.cfg.get("audio_mic_device"):
            idx = self.cb_mic.findText(self.cfg["audio_mic_device"])
            if idx >= 0: self.cb_mic.setCurrentIndex(idx)

    def _show_audio_diag(self):
        text = diagnose_audio_devices(self.cfg.get("ffmpeg_path", "ffmpeg"))
        QMessageBox.information(self, "音訊診斷", text)

    # ============ Webcam ============
    def _tab_webcam(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        c, cv = make_card("Webcam 設定")
        self.cb_webcam = QCheckBox("啟用 Webcam (圓形框)")
        self.cb_webcam.setChecked(self.cfg.get("webcam_enabled", False))
        self.cb_webcam.toggled.connect(self._on_webcam_toggled)
        cv.addWidget(self.cb_webcam)

        g = QGridLayout()
        g.addWidget(QLabel("選擇裝置"), 0, 0)
        self.cb_cam_dev = QComboBox()
        self.cb_cam_dev.addItem("切換分頁後自動偵測...")
        g.addWidget(self.cb_cam_dev, 0, 1)

        g.addWidget(QLabel("圓框大小"), 1, 0)
        h_size = QHBoxLayout()
        self.sl_cam_size = QSlider(Qt.Horizontal)
        self.sl_cam_size.setRange(100, 500)
        self.sl_cam_size.setValue(self.cfg.get("webcam_size", 200))
        self.lbl_cam_size = QLabel(f"{self.sl_cam_size.value()} px")
        self.sl_cam_size.valueChanged.connect(lambda v: self.lbl_cam_size.setText(f"{v} px"))
        h_size.addWidget(self.sl_cam_size, 1)
        h_size.addWidget(self.lbl_cam_size)
        g.addLayout(h_size, 1, 1)
        
        cv.addLayout(g)

        self.btn_preview_cam = QPushButton("預覽 Webcam 位置")
        self.btn_preview_cam.clicked.connect(self._preview_webcam)
        cv.addWidget(self.btn_preview_cam)

        v.addWidget(c)
        v.addStretch()
        return w

    def _refresh_cams(self):
        if not HAS_CV2:
            self.cb_cam_dev.clear()
            self.cb_cam_dev.addItem("未安裝 OpenCV")
            return
        
        # 顯示掃描中狀態
        self.cb_cam_dev.clear()
        self.cb_cam_dev.addItem("攝影機型號掃描中...")
        QApplication.processEvents()

        found_devs = []
        
        # 優先使用 pygrabber 獲取型號名稱
        if HAS_PYGRABBER:
            try:
                graph = FilterGraph()
                devices = graph.get_input_devices()
                for i, name in enumerate(devices):
                    # 雙重確認 OpenCV 是否真的能開啟該裝置
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        found_devs.append((f"{name}", i))
                        cap.release()
            except Exception as e:
                print(f"pygrabber 掃描失敗: {e}")

        # 若 pygrabber 沒找到或失敗，退回原本的簡單偵測
        if not found_devs:
            for i in range(4):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    found_devs.append((f"Camera {i}", i))
                    cap.release()
        
        self.cb_cam_dev.clear()
        if not found_devs:
            self.cb_cam_dev.addItem("未偵測到攝影機")
            return
            
        for label, idx in found_devs:
            self.cb_cam_dev.addItem(label, idx)
        
        cur = self.cfg.get("webcam_index", 0)
        idx = self.cb_cam_dev.findData(cur)
        if idx >= 0: self.cb_cam_dev.setCurrentIndex(idx)

    def _on_webcam_toggled(self, checked):
        if checked:
            self._preview_webcam()
        else:
            if hasattr(self, "_webcam_preview") and self._webcam_preview:
                self._webcam_preview.close()
                self._webcam_preview = None

    def _preview_webcam(self):
        from .webcam import WebcamOverlay
        if hasattr(self, "_webcam_preview") and self._webcam_preview:
            if self._webcam_preview.isVisible():
                return # 已經開著了就不用重複開
            else:
                self._webcam_preview.close()
        
        idx = self.cb_cam_dev.currentData()
        if idx is None: 
            # 如果是自動觸發但沒裝置，就不彈窗，只靜默失敗
            return
        
        # 建立預覽視窗，傳入 self 作為 parent 但設為 Window 屬性以繞過模態鎖定
        self._webcam_preview = WebcamOverlay(idx, self.sl_cam_size.value(), parent=self)
        pos = self.cfg.get("webcam_pos")
        if pos:
            self._webcam_preview.move(pos[0], pos[1])
        
        self._webcam_preview.show()
        
        # 監聽關閉事件，如果使用者手動關掉，也要同步勾選框
        def on_preview_closed():
            if self.cb_webcam.isChecked():
                self.cb_webcam.blockSignals(True)
                self.cb_webcam.setChecked(False)
                self.cb_webcam.blockSignals(False)
        self._webcam_preview.closed.connect(on_preview_closed)

    # ============ 快速鍵 ============
    def _tab_hotkey(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        c1, cv = make_card("錄影快速鍵 (點選輸入框後直接按鍵)")
        self.le_start = HotkeyLineEdit(self.cfg["hotkey_start"])
        self.le_pause = HotkeyLineEdit(self.cfg["hotkey_pause"])
        self.le_stop = HotkeyLineEdit(self.cfg["hotkey_stop"])
        
        for lbl, ed in [("開始", self.le_start), ("暫停", self.le_pause), ("停止", self.le_stop)]:
            h = QHBoxLayout()
            l = QLabel(lbl)
            l.setFixedWidth(40)
            h.addWidget(l)
            h.addWidget(ed, 1)
            cv.addLayout(h)
        v.addWidget(c1)

        c2, cv2 = make_card("介面設定")
        self.cb_mini = QCheckBox("顯示迷你工具列")
        self.cb_mini.setChecked(self.cfg.get("use_mini_toolbar", True))
        self.cb_count = QCheckBox("顯示開錄倒數")
        self.cb_count.setChecked(self.cfg.get("use_countdown", True))
        cv2.addWidget(self.cb_mini)
        cv2.addWidget(self.cb_count)
        v.addWidget(c2)
        v.addStretch()
        return w

    # ============ 標註 ============
    def _tab_annot(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        c, cv = make_card("螢幕標註")
        self.cb_annot = QCheckBox("啟用標註")
        self.cb_annot.setChecked(self.cfg.get("annotation_enabled", True))
        cv.addWidget(self.cb_annot)

        h = QHBoxLayout()
        h.addWidget(QLabel("切換標註快速鍵"))
        self.le_annot_toggle = HotkeyLineEdit(self.cfg["annotation_hotkey_toggle"])
        h.addWidget(self.le_annot_toggle, 1)
        cv.addLayout(h)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("自動消失 (秒)"))
        self.sp_fade = QSpinBox()
        self.sp_fade.setRange(0, 60)
        self.sp_fade.setValue(self.cfg.get("annotation_auto_fade_seconds", 0))
        h2.addWidget(self.sp_fade)
        h2.addStretch()
        cv.addLayout(h2)
        v.addWidget(c)
        v.addStretch()
        return w

    # ============ 輸出 ============
    def _tab_output(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)
        c, cv = make_card("輸出資料夾")
        h = QHBoxLayout()
        self.le_out = QLineEdit(self.cfg["output_dir"])
        b = QPushButton("瀏覽")
        b.clicked.connect(self._choose_dir)
        h.addWidget(self.le_out, 1)
        h.addWidget(b)
        cv.addLayout(h)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("檔名前綴"))
        self.le_prefix = QLineEdit(self.cfg.get("filename_prefix", "錄影"))
        self.le_prefix.setMaximumWidth(120)
        h2.addWidget(self.le_prefix)
        h2.addStretch()
        cv.addLayout(h2)
        v.addWidget(c)
        v.addStretch()
        return w

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "選擇資料夾", self.le_out.text())
        if d: self.le_out.setText(d)

    # ============ 儲存 ============
    def accept_and_save(self):
        c = self.cfg
        c["region_mode"] = "fullscreen" if self.rb_full.isChecked() else "custom"
        c["resolution"] = self.cb_res.currentText()
        c["fps"] = self.sp_fps.value()
        c["container"] = self.cb_container.currentText()
        c["encoder"] = self.cb_encoder.currentData() or "libx264"
        c["quality_mode"] = ["CRF", "VBR", "CBR"][self.cb_qmode.currentIndex()]
        c["crf"] = self.sl_crf.value()
        c["bitrate"] = self.le_bitrate.text()
        c["audio_system"] = self.cb_sys_audio.isChecked()
        c["audio_mic"] = self.cb_mic_audio.isChecked()
        if hasattr(self, "_detected_sys_device") and self._detected_sys_device:
            c["audio_system_device"] = self._detected_sys_device
        c["audio_mic_device"] = self.cb_mic.currentText()
        
        # Webcam 儲存
        c["webcam_enabled"] = self.cb_webcam.isChecked()
        c["webcam_index"] = self.cb_cam_dev.currentData() if self.cb_cam_dev.currentData() is not None else 0
        c["webcam_size"] = self.sl_cam_size.value()
        if hasattr(self, "_webcam_preview") and self._webcam_preview:
            p = self._webcam_preview.pos()
            c["webcam_pos"] = [p.x(), p.y()]
            self._webcam_preview.close()
            self._webcam_preview = None

        c["show_cursor"] = self.cb_cursor.isChecked()
        c["use_mini_toolbar"] = self.cb_mini.isChecked()
        c["use_countdown"] = self.cb_count.isChecked()
        c["hotkey_start"] = self.le_start.text()
        c["hotkey_pause"] = self.le_pause.text()
        c["hotkey_stop"] = self.le_stop.text()
        c["annotation_enabled"] = self.cb_annot.isChecked()
        c["annotation_hotkey_toggle"] = self.le_annot_toggle.text()
        c["annotation_auto_fade_seconds"] = self.sp_fade.value()
        c["output_dir"] = self.le_out.text()
        c["filename_prefix"] = self.le_prefix.text()
        save_config(c)
        self.settings_changed.emit()
        self.accept()
