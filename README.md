# 桌面錄影工具 (Desktop Recorder)

一個基於 Python 與 PySide6 開發的極簡、現代化桌面錄影工具。支援硬體加速、即時標註、獨立 Webcam 圓形視窗，並具備自動下載 FFmpeg 的功能，讓使用者開箱即用。

![UI Preview](assets/icon.png)

## ✨ 特色功能

- 🚀 **一鍵錄影**：簡單直覺的介面，按下快速鍵或按鈕即可開始。
- 🎨 **現代化配色**：活潑的夢幻漸層設計，完美支援 Windows 高 DPI 縮放。
- 📷 **獨立 Webcam 圓框**：
  - 支援常駐顯示，不隨錄影停止而關閉。
  - 圓形裁剪設計，可自由拖曳位置、自訂大小。
  - 右鍵選單可隨時手動關閉。
  - 自動偵測攝影機型號名稱（如：Logitech C920）。
- 📐 **常駐錄影邊框**：
  - 自訂區域模式下，平時顯示 **藍色實線** 預覽範圍。
  - 錄影期間自動切換為 **紅色虛線** 動態提示。
- 🖌️ **即時標註**：錄影中支援畫筆、螢光筆、箭頭、矩形等標註工具。
- ⚡ **硬體加速**：支援 NVIDIA NVENC, Intel QSV, AMD AMF 等硬體編碼。
- 📦 **自動化 FFmpeg**：啟動時若找不到 FFmpeg，程式將自動在背景下載並配置。
- ⌨️ **全域快速鍵**：支援自訂 F9/F10/F11 等快速鍵，視窗縮小也能操作。

---

## 🛠️ 開發與執行說明

如果你想從原始碼執行或進行開發，請參考以下步驟：

### 1. 安裝 Python
請至 [Python 官網](https://www.python.org/downloads/) 下載並安裝 Python 3.10 或以上版本。
> **注意**：安裝時請務必勾選 **"Add Python to PATH"**。

### 2. 下載原始碼
使用 Git 複製本專案，或點擊 GitHub 上的 "Download ZIP" 並解壓縮。
```bash
git clone https://github.com/your-username/desktop-recorder.git
cd desktop-recorder
```

### 3. 安裝依賴套件
```bash
pip install -r requirements.txt
```
*主要依賴：PySide6, opencv-python, pygrabber, keyboard, pygetwindow*

### 4. 執行程式
```bash
python main.py
```

---

## 📦 打包為 EXE 執行檔

若要打包成單一執行檔，請執行：

```bash
# 安裝打包工具
pip install pyinstaller

# 執行打包指令
pyinstaller --noconfirm --onefile --windowed --icon="assets/icon.png" --add-data "ui/styles.qss;ui" --add-data "assets/icon.png;assets" --name "桌面錄影工具" main.py
```

---

## ⌨️ 預設快速鍵

- **F9**：開始錄影 / 恢復錄影
- **F10**：暫停錄影
- **F11**：停止錄影
- **Ctrl+Shift+D**：開啟/關閉標註工具列

---

## 📝 授權說明
本軟體採 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.zh_TW) 姓名標示-非商業性 授權。
FFmpeg 則遵循其各自的 LGPL/GPL 授權協議。

---
**Made by 阿剛老師** - [部落格](https://kentxchang.blogspot.tw)
