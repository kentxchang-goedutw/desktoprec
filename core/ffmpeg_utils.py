"""ffmpeg 偵測：硬體編碼器、音訊裝置"""
import subprocess
import re
import shutil
import os
import sys
import zipfile
import urllib.request
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

def find_ffmpeg():
    """尋找 ffmpeg 執行檔"""
    app_data = Path.home() / ".desktop_recorder" / "bin"
    ext = ".exe" if sys.platform == "win32" else ""
    local = app_data / f"ffmpeg{ext}"
    if local.exists():
        return str(local)

    p = shutil.which("ffmpeg")
    if p:
        return p
        
    # 嘗試原本的本地 ffmpeg/ 資料夾
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    legacy_local = os.path.join(here, "ffmpeg", f"ffmpeg{ext}")
    if os.path.exists(legacy_local):
        return legacy_local
    return None

def ensure_ffmpeg(progress_callback=None, force_download=False):
    """確保 ffmpeg 存在，若不存在則下載 (目前僅支援 Windows 自動下載)"""
    path = find_ffmpeg()
    if path and not force_download:
        return path

    if sys.platform != "win32":
        if progress_callback:
            progress_callback("請先安裝 ffmpeg (例如使用 brew install ffmpeg)")
        return None

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
        run_kwargs = {"capture_output": True, "timeout": timeout}
        if CREATE_NO_WINDOW:
            run_kwargs["creationflags"] = CREATE_NO_WINDOW
        r = subprocess.run([ffmpeg_path] + args, **run_kwargs)
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
                "h264_amf", "hevc_amf", "libx264", "libx265", "libvpx-vp9", "h264_videotoolbox", "hevc_videotoolbox"]:
        available[enc] = enc in out

    # 進一步測試 NVENC/QSV/AMF 是否真能初始化
    encoders = []
    if available.get("h264_nvenc"):
        encoders.append(("NVIDIA NVENC (H.264) ⚡", "h264_nvenc"))
    if available.get("hevc_nvenc"):
        encoders.append(("NVIDIA NVENC (H.265) ⚡", "hevc_nvenc"))
    if available.get("h264_videotoolbox"):
        encoders.append(("Apple VideoToolbox (H.264) ⚡", "h264_videotoolbox"))
    if available.get("hevc_videotoolbox"):
        encoders.append(("Apple VideoToolbox (H.265) ⚡", "hevc_videotoolbox"))
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


def list_audio_devices(ffmpeg_path="ffmpeg"):
    """列出音訊裝置 (支援 dshow 與 avfoundation)"""
    if sys.platform == "win32":
        return _list_dshow_audio(ffmpeg_path)
    elif sys.platform == "darwin":
        return _list_avfoundation_audio(ffmpeg_path)
    return []

def _list_dshow_audio(ffmpeg_path="ffmpeg"):
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


def supports_wasapi_loopback(ffmpeg_path="ffmpeg"):
    """Return True when this FFmpeg build supports WASAPI loopback capture."""
    if sys.platform != "win32":
        return False
    out = run_ffmpeg(["-hide_banner", "-h", "demuxer=wasapi"], ffmpeg_path)
    low = out.lower()
    return "demuxer wasapi" in low and "loopback" in low


def find_windows_system_audio_device(ffmpeg_path="ffmpeg"):
    """Find a DirectShow device that can capture Windows system output."""
    keywords = (
        "stereo mix", "立體聲混音", "what u hear", "wave out mix",
        "virtual-audio-capturer", "loopback", "speaker",
    )
    for device in _list_dshow_audio(ffmpeg_path):
        if any(keyword in device.lower() for keyword in keywords):
            return device
    return None


def can_capture_windows_system_audio(ffmpeg_path="ffmpeg"):
    return (
        supports_wasapi_loopback(ffmpeg_path)
        or bool(find_windows_system_audio_device(ffmpeg_path))
    )

def _list_avfoundation_audio(ffmpeg_path="ffmpeg"):
    """列出 macOS avfoundation 音訊裝置"""
    out = run_ffmpeg(["-hide_banner", "-list_devices", "true",
                     "-f", "avfoundation", "-i", '""'], ffmpeg_path)
    devices = []
    in_audio_section = False
    for line in out.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio_section = True
            continue
        if "AVFoundation video devices:" in line:
            in_audio_section = False
            continue
        
        if in_audio_section:
            # 格式: [AVFoundation input device @ 0x...] [0] Built-in Microphone
            m = re.search(r'\[(\d+)\]\s+(.*)', line)
            if m:
                idx = m.group(1).strip()
                name = m.group(2).strip()
                if name:
                    devices.append(f"{idx}: {name}")
    return devices


def mac_audio_input_spec(ffmpeg_path="ffmpeg", device=""):
    """Return an avfoundation audio input spec for a saved macOS device."""
    if not device or device == "default":
        return None
    m = re.match(r'\s*(\d+)\s*:', str(device))
    if m:
        return f":{m.group(1)}"

    target = str(device).strip().lower()
    for item in _list_avfoundation_audio(ffmpeg_path):
        m = re.match(r'\s*(\d+)\s*:\s*(.*)', item)
        if m and m.group(2).strip().lower() == target:
            return f":{m.group(1)}"
    return None


def find_mac_system_audio_device(ffmpeg_path="ffmpeg"):
    """Find a likely macOS loopback device for system audio capture."""
    keywords = (
        "blackhole", "soundflower", "loopback", "background music",
        "backgroundmusic", "eqmac", "system audio",
    )
    for item in _list_avfoundation_audio(ffmpeg_path):
        if any(k in item.lower() for k in keywords):
            return item
    return None

def get_mac_video_devices(ffmpeg_path="ffmpeg"):
    """列出 macOS avfoundation 視訊/螢幕裝置，回傳 (index, name) 列表"""
    out = run_ffmpeg(["-hide_banner", "-list_devices", "true",
                     "-f", "avfoundation", "-i", '""'], ffmpeg_path)
    devices = []
    in_video_section = False
    for line in out.splitlines():
        if "AVFoundation video devices:" in line:
            in_video_section = True
            continue
        if "AVFoundation audio devices:" in line:
            in_video_section = False
            continue
        
        if in_video_section:
            m = re.search(r'\[(\d+)\]\s+(.*)', line)
            if m:
                idx = m.group(1)
                name = m.group(2).strip()
                devices.append((idx, name))
    return devices

def list_audio_via_sounddevice():
    """備援：用 sounddevice 列出輸入裝置"""
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


def diagnose_audio_devices(ffmpeg_path="ffmpeg"):
    """回傳完整 ffmpeg 輸出，便於診斷"""
    if sys.platform == "win32":
        return run_ffmpeg(["-hide_banner", "-list_devices", "true",
                          "-f", "dshow", "-i", "dummy"], ffmpeg_path)
    elif sys.platform == "darwin":
        return run_ffmpeg(["-hide_banner", "-list_devices", "true",
                          "-f", "avfoundation", "-i", '""'], ffmpeg_path)
    return "Unsupported platform"


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
    elif "videotoolbox" in encoder:
        if quality_mode == "CRF":
            # VideoToolbox 不支援 CRF，改用實質上的位元率控制
            args += ["-b:v", bitrate]
        else:
            args += ["-b:v", bitrate]
        args += ["-pix_fmt", "nv12"]
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
