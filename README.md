# 桌面錄影工具 (Desktop Recorder)

一個基於 Python 與 PySide6 開發的極簡、現代化桌面錄影工具。支援硬體加速、即時標註，並具備自動下載 FFmpeg 的功能，讓使用者開箱即用。

![UI Preview](assets/icon.png)

## ✨ 特色功能

- 🚀 **一鍵錄影**：簡單直覺的介面，按下快速鍵即可開始。
- 🎨 **現代化配色**：活潑的漸層藍紫設計，支援高 DPI 縮放。
- 🖌️ **即時標註**：錄影中支援畫筆、螢光筆、箭頭、矩形等標註工具。
- ⚡ **硬體加速**：支援 NVIDIA NVENC, Intel QSV, AMD AMF 等硬體編碼。
- 📦 **自動化 FFmpeg**：程式啟動時若偵測不到 FFmpeg，將自動在背景下載並配置。
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
在專案目錄下執行以下指令安裝必要的 library：
```bash
pip install -r requirements.txt
```

### 4. 執行程式
```bash
python main.py
```

---

## 📦 打包為 EXE 執行檔

如果你想將程式打包成單一的 `.exe` 檔案以便分享給他人，請執行：

```bash
# 安裝打包工具
pip install pyinstaller

# 執行打包指令
pyinstaller --noconfirm --onefile --windowed --icon="assets/icon.png" --add-data "ui/styles.qss;ui" --add-data "assets/icon.png;assets" --name "桌面錄影工具" main.py
```
打包完成後，你可以在 `dist/` 資料夾中找到 `桌面錄影工具.exe`。

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
