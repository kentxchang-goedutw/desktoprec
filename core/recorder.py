"""ffmpeg 錄影核心"""
import subprocess
import os
import sys
import signal
import time
from datetime import datetime
from pathlib import Path
from .ffmpeg_utils import (
    encoder_args,
    CREATE_NO_WINDOW,
    get_mac_video_devices,
    mac_audio_input_spec,
    find_mac_system_audio_device,
    supports_wasapi_loopback,
    find_windows_system_audio_device,
)
from .display_utils import normalize_capture_region, monitor_rects


class Recorder:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.output_path = None
        self.start_time = None
        self.paused = False
        self.pause_offset = 0
        self._pause_start = None

    def _build_command(self):
        cfg = self.cfg
        ffmpeg = cfg.get("ffmpeg_path", "ffmpeg")
        fps = cfg.get("fps", 30)
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]

        # ----- 視訊輸入 -----
        vf_filters = []
        if sys.platform == "win32":
            cmd += ["-f", "gdigrab", "-framerate", str(fps)]
            if cfg.get("show_cursor", True):
                cmd += ["-draw_mouse", "1"]
            else:
                cmd += ["-draw_mouse", "0"]

            region = cfg.get("region_mode", "fullscreen")
            capture_region = None
            if region == "monitor":
                monitors = monitor_rects()
                idx = int(cfg.get("monitor_index", 0) or 0)
                if 0 <= idx < len(monitors):
                    capture_region = monitors[idx]
            elif region == "custom" and cfg.get("custom_region"):
                capture_region = cfg["custom_region"]

            if capture_region:
                x, y, w, h = normalize_capture_region(capture_region)
                cmd += ["-video_size", f"{w}x{h}", "-offset_x", str(x), "-offset_y", str(y)]
            cmd += ["-i", "desktop"]
        elif sys.platform == "darwin":
            video_devs = get_mac_video_devices(ffmpeg)
            screen_devs = [(idx, name) for idx, name in video_devs
                           if "capture screen" in name.lower()]
            if not screen_devs:
                screen_devs = video_devs
            monitor_idx = int(cfg.get("monitor_index", 0) or 0)
            if cfg.get("region_mode") == "monitor" and 0 <= monitor_idx < len(screen_devs):
                screen_idx = screen_devs[monitor_idx][0]
            elif screen_devs:
                screen_idx = screen_devs[0][0]
            else:
                screen_idx = "1"
            
            cmd += ["-f", "avfoundation", "-framerate", str(fps)]
            if cfg.get("show_cursor", True):
                cmd += ["-capture_cursor", "1"]
            else:
                cmd += ["-capture_cursor", "0"]
            cmd += ["-i", screen_idx]

            region = cfg.get("region_mode", "fullscreen")
            if region == "custom" and cfg.get("custom_region"):
                x, y, w, h = cfg["custom_region"]
                w = (w // 2) * 2
                h = (h // 2) * 2
                vf_filters.append(f"crop={w}:{h}:{x}:{y}")
        else:
            # Linux (x11grab) 略過不實作
            cmd += ["-i", ":0.0"]

        # ----- 音訊輸入 -----
        audio_inputs = 0
        if sys.platform == "win32":
            if cfg.get("audio_system"):
                device = cfg.get("audio_system_device") or "default"
                if supports_wasapi_loopback(ffmpeg):
                    cmd += ["-f", "wasapi", "-loopback", "1", "-i", device]
                else:
                    if device == "default":
                        device = find_windows_system_audio_device(ffmpeg)
                    if not device:
                        download_url = "https://github.com/rdp/screen-capture-recorder-to-video-windows-free/releases/download/v0.13.3/Setup.Screen.Capturer.Recorder.v0.13.3.exe"
                        raise Exception(
                            "目前找不到可錄製系統聲音的裝置。\n\n"
                            "如要啟用錄製系統音訊，請先下載並安裝此軟體：\n"
                            f"{download_url}\n\n"
                            "安裝後請重新啟動程式即可使用錄製系統聲音功能。"
                        )
                    cmd += ["-f", "dshow", "-i", f"audio={device}"]
                audio_inputs += 1
            if cfg.get("audio_mic") and cfg.get("audio_mic_device"):
                cmd += ["-f", "dshow", "-i", f"audio={cfg['audio_mic_device']}"]
                audio_inputs += 1
        elif sys.platform == "darwin":
            if cfg.get("audio_system"):
                system_device = cfg.get("audio_system_device")
                if not system_device or system_device == "default":
                    system_device = find_mac_system_audio_device(ffmpeg)
                system_spec = mac_audio_input_spec(ffmpeg, system_device)
                if system_spec:
                    cmd += ["-f", "avfoundation", "-i", system_spec]
                    audio_inputs += 1
                else:
                    blackhole_url = "https://github.com/ExistentialAudio/BlackHole"
                    raise Exception(
                        "目前找不到可用於錄製 macOS 系統聲音的裝置。\n\n"
                        "macOS 錄製系統音訊需安裝虛擬音訊裝置，建議使用 BlackHole：\n"
                        f"{blackhole_url}\n\n"
                        "安裝後，請在「設定 > 音訊」中確認是否已偵測到該裝置。"
                    )
            if cfg.get("audio_mic") and cfg.get("audio_mic_device"):
                mic_spec = mac_audio_input_spec(ffmpeg, cfg.get("audio_mic_device"))
                if mic_spec:
                    cmd += ["-f", "avfoundation", "-i", mic_spec]
                    audio_inputs += 1

        # ----- 縮放與濾鏡 -----
        res = cfg.get("resolution", "原始")
        if res == "1080p":
            vf_filters.append("scale=-2:1080")
        elif res == "720p":
            vf_filters.append("scale=-2:720")
        elif res == "480p":
            vf_filters.append("scale=-2:480")
        
        if vf_filters:
            cmd += ["-vf", ",".join(vf_filters)]

        # ----- 視訊編碼 -----
        encoder = cfg.get("encoder", "libx264")
        if encoder == "auto":
            if sys.platform == "darwin":
                encoder = "h264_videotoolbox"
            else:
                encoder = "libx264"
        
        cmd += encoder_args(encoder, cfg.get("quality_mode", "CRF"),
                            cfg.get("crf", 23), cfg.get("bitrate", "5M"))
        cmd += ["-r", str(fps), "-g", str(fps * 2)]

        # ----- 混音 (兩條音訊時混為一軌) -----
        if audio_inputs == 2:
            cmd += ["-filter_complex",
                    "[1:a][2:a]amix=inputs=2:duration=longest[aout]",
                    "-map", "0:v", "-map", "[aout]"]
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        elif audio_inputs == 1:
            cmd += ["-map", "0:v", "-map", "1:a"]
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-map", "0:v", "-an"]

        # ----- 容器 / 輸出 -----
        ext = cfg.get("container", "mp4")
        if ext == "mp4":
            cmd += ["-movflags", "+faststart"]
        out_dir = Path(cfg.get("output_dir"))
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = cfg.get("filename_prefix", "錄影")
        self.output_path = str(out_dir / f"{prefix}_{ts}.{ext}")
        cmd.append(self.output_path)
        return cmd

    def start(self):
        cmd = self._build_command()
        print(f"[Recorder] 執行命令: {' '.join(cmd)}")
        popen_kwargs = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
        }
        if CREATE_NO_WINDOW:
            popen_kwargs["creationflags"] = CREATE_NO_WINDOW
        self.proc = subprocess.Popen(cmd, **popen_kwargs)
        self.start_time = time.time()
        self.paused = False
        self.pause_offset = 0
        
        # 啟動檢查：確保 FFmpeg 已成功掛載輸入源
        time.sleep(0.6)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read()
            raise Exception(f"FFmpeg 啟動失敗：\n{err}")
            
        return self.output_path

    def pause(self):
        """ffmpeg 不支援真暫停。改用旗標 + 在 UI 顯示，輸出時段不分割。
        簡化版：實際停止接著重啟（會分檔）。此處只記錄狀態，不真實暫停 ffmpeg。"""
        if self.proc and not self.paused:
            self.paused = True
            self._pause_start = time.time()

    def resume(self):
        if self.proc and self.paused:
            self.pause_offset += time.time() - self._pause_start
            self.paused = False

    def stop(self):
        if not self.proc:
            return None
        proc = self.proc
        self.proc = None
        
        print(f"[Recorder] 正在停止錄影並寫入檔案尾部資訊...")
        try:
            # 傳送 'q' 讓 FFmpeg 正常結束並 Flush 緩衝區
            if proc.stdin:
                try:
                    proc.stdin.write("q\n")
                    proc.stdin.flush()
                except (OSError, BrokenPipeError):
                    pass
            
            # 等待程序完成檔案寫入 (最長等待 10 秒)
            try:
                _, stderr = proc.communicate(timeout=10)
                if stderr:
                    print(f"[Recorder] FFmpeg 結束日誌: {stderr}")
            except subprocess.TimeoutExpired:
                print("[Recorder] FFmpeg 結束逾時，強制終止")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except:
                    proc.kill()
        except Exception as e:
            print(f"[Recorder] 停止時發生異常: {e}")
            try:
                proc.kill()
            except:
                pass
        finally:
            # 顯式關閉所有串流
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream: stream.close()
                except:
                    pass
        
        print(f"[Recorder] 錄影已完整寫入：{self.output_path}")
        return self.output_path

    def elapsed(self):
        if not self.start_time:
            return 0
        if self.paused:
            return self._pause_start - self.start_time - self.pause_offset
        return time.time() - self.start_time - self.pause_offset
