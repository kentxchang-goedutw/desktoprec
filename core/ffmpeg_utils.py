"""ffmpeg 偵測：硬體編碼器、音訊裝置"""
import subprocess
import re
import shutil
import os
import zipfile
import urllib.request
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

def find_ffmpeg():
    """尋找 ffmpeg 執行檔"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    
    # 嘗試預設本地路徑
    app_data = Path.home() / ".desktop_recorder" / "bin"
    local = app_data / "ffmpeg.exe"
    if local.exists():
        return str(local)
        
    # 嘗試原本的本地 ffmpeg/ 資料夾
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    legacy_local = os.path.join(here, "ffmpeg", "ffmpeg.exe")
    if os.path.exists(legacy_local):
        return legacy_local
    return None

def ensure_ffmpeg(progress_callback=None):
    """確保 ffmpeg 存在，若不存在則下載"""
    path = find_ffmpeg()
    if path:
        return path

    dest_dir = Path.home() / ".desktop_recorder" / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / "ffmpeg.zip"
    
    if progress_callback:
        progress_callback("正在下載 ffmpeg (約 100MB)，請稍候...")

    try:
        # 下載
        urllib.request.urlretrieve(FFMPEG_URL, zip_path)
        
        if progress_callback:
            progress_callback("正在解壓縮...")
            
        # 解壓
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # 尋找 zip 內的 ffmpeg.exe (通常在 bin/ 下)
            for file in zip_ref.namelist():
                if file.endswith("ffmpeg.exe"):
                    filename = os.path.basename(file)
                    source = zip_ref.open(file)
                    target = open(dest_dir / filename, "wb")
                    with source, target:
                        shutil.copyfileobj(source, target)
                    break
        
        # 清理 zip
        os.remove(zip_path)
        return str(dest_dir / "ffmpeg.exe")
    except Exception as e:
        if progress_callback:
            progress_callback(f"下載失敗: {e}")
        return None


def run_ffmpeg(args, ffmpeg_path="ffmpeg", timeout=10):
    """以 bytes 取得輸出後依序嘗試多種編碼解碼，避免中文裝置名稱被吞掉"""
    try:
        r = subprocess.run(
            [ffmpeg_path] + args,
            capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        raw = (r.stdout or b"") + b"\n" + (r.stderr or b"")
        for enc in ("utf-8", "mbcs", "cp950", "cp936", "cp932", "latin-1"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


def detect_encoders(ffmpeg_path="ffmpeg"):
    """偵測可用編碼器"""
    available = {
        "libx264": True,
        "libx265": True,
    }
    out = run_ffmpeg(["-hide_banner", "-encoders"], ffmpeg_path)
    for enc in ["h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv",
                "h264_amf", "hevc_amf", "libx264", "libx265", "libvpx-vp9"]:
        available[enc] = enc in out

    # 進一步測試 NVENC/QSV/AMF 是否真能初始化
    encoders = []
    if available.get("h264_nvenc"):
        encoders.append(("NVIDIA NVENC (H.264) ⚡", "h264_nvenc"))
    if available.get("hevc_nvenc"):
        encoders.append(("NVIDIA NVENC (H.265) ⚡", "hevc_nvenc"))
    if available.get("h264_qsv"):
        encoders.append(("Intel QSV (H.264) ⚡", "h264_qsv"))
    if available.get("hevc_qsv"):
        encoders.append(("Intel QSV (H.265) ⚡", "hevc_qsv"))
    if available.get("h264_amf"):
        encoders.append(("AMD AMF (H.264) ⚡", "h264_amf"))
    if available.get("hevc_amf"):
        encoders.append(("AMD AMF (H.265) ⚡", "hevc_amf"))
    if available.get("libx264"):
        encoders.append(("CPU x264 (H.264)", "libx264"))
    if available.get("libx265"):
        encoders.append(("CPU x265 (H.265)", "libx265"))
    if available.get("libvpx-vp9"):
        encoders.append(("VP9 (僅 mkv)", "libvpx-vp9"))
    return encoders


def list_dshow_audio(ffmpeg_path="ffmpeg"):
    """列出 dshow 音訊裝置（同時支援新舊版 ffmpeg 輸出格式）"""
    out = run_ffmpeg(["-hide_banner", "-list_devices", "true",
                     "-f", "dshow", "-i", "dummy"], ffmpeg_path)
    devices = []
    in_audio_section = False
    for line in out.splitlines():
        low = line.lower()
        # 偵測區段切換
        if "directshow audio devices" in low:
            in_audio_section = True
            continue
        if "directshow video devices" in low:
            in_audio_section = False
            continue
        if "alternative name" in low:
            continue

        # 取出引號內的裝置名
        m = re.search(r'"([^"]+)"', line)
        if not m:
            continue
        name = m.group(1).strip()
        if not name or name.startswith("@device_"):
            continue

        # 新版 ffmpeg 會在同一行加 (audio) / (video) 標記
        if "(audio)" in low:
            if name not in devices:
                devices.append(name)
        elif "(video)" in low:
            continue
        elif in_audio_section:
            if name not in devices:
                devices.append(name)
    return devices


def list_audio_via_sounddevice():
    """備援：用 sounddevice 列出輸入裝置（可能與 dshow 名稱不完全一致，但可幫助診斷）"""
    try:
        import sounddevice as sd
        devs = []
        for d in sd.query_devices():
            if d.get("max_input_channels", 0) > 0:
                name = d.get("name", "").strip()
                if name and name not in devs:
                    devs.append(name)
        return devs
    except Exception:
        return []


def diagnose_dshow(ffmpeg_path="ffmpeg"):
    """回傳完整 ffmpeg 輸出，便於診斷"""
    return run_ffmpeg(["-hide_banner", "-list_devices", "true",
                      "-f", "dshow", "-i", "dummy"], ffmpeg_path)


def encoder_args(encoder, quality_mode, crf, bitrate):
    """根據編碼器產生 ffmpeg 參數"""
    args = ["-c:v", encoder]
    if encoder in ("libx264", "libx265"):
        args += ["-preset", "medium"]
        if quality_mode == "CRF":
            args += ["-crf", str(crf)]
        elif quality_mode == "VBR":
            args += ["-b:v", bitrate]
        else:
            args += ["-b:v", bitrate, "-minrate", bitrate, "-maxrate", bitrate]
        args += ["-pix_fmt", "yuv420p"]
    elif "nvenc" in encoder:
        args += ["-preset", "p4", "-tune", "hq"]
        if quality_mode == "CRF":
            args += ["-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
        elif quality_mode == "VBR":
            args += ["-rc", "vbr", "-b:v", bitrate]
        else:
            args += ["-rc", "cbr", "-b:v", bitrate]
        args += ["-pix_fmt", "yuv420p"]
    elif "qsv" in encoder:
        args += ["-preset", "medium"]
        if quality_mode == "CRF":
            args += ["-global_quality", str(crf)]
        else:
            args += ["-b:v", bitrate]
        args += ["-pix_fmt", "nv12"]
    elif "amf" in encoder:
        args += ["-quality", "balanced"]
        if quality_mode == "CRF":
            args += ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf + 2)]
        elif quality_mode == "VBR":
            args += ["-rc", "vbr_peak", "-b:v", bitrate]
        else:
            args += ["-rc", "cbr", "-b:v", bitrate]
        args += ["-pix_fmt", "yuv420p"]
    elif encoder == "libvpx-vp9":
        args += ["-b:v", bitrate, "-crf", str(crf)]
    return args
