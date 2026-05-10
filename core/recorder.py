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
        self.final_output_path = None
        self.start_time = None
        self.paused = False
        self.pause_offset = 0
        self._pause_start = None
        self.segments = []

    def _build_command(self, output_path):
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

        # ----- 混音與音訊濾鏡 -----
        # 決定麥克風在哪個串流索引
        mic_idx = -1
        if cfg.get("audio_mic") and cfg.get("audio_mic_device"):
            if cfg.get("audio_system"):
                mic_idx = 2
            else:
                mic_idx = 1
        
        # 麥克風降噪濾鏡：afftdn=nr=12 (降噪12dB), highpass=f=100 (濾除低頻低鳴)
        mic_filter = "afftdn=nr=12,highpass=f=100"
        
        if audio_inputs == 2:
            # 兩條音訊：[1:a]系統, [2:a]麥克風
            cmd += ["-filter_complex",
                    f"[2:a]{mic_filter}[mic_clean];"
                    "[1:a][mic_clean]amix=inputs=2:duration=longest[aout]",
                    "-map", "0:v", "-map", "[aout]"]
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        elif audio_inputs == 1:
            if mic_idx == 1:
                # 只有麥克風
                cmd += ["-filter_complex", f"[1:a]{mic_filter}[aout]",
                        "-map", "0:v", "-map", "[aout]"]
            else:
                # 只有系統音
                cmd += ["-map", "0:v", "-map", "1:a"]
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-map", "0:v", "-an"]

        # ----- 容器 / 輸出 -----
        ext = cfg.get("container", "mp4")
        if ext == "mp4":
            cmd += ["-movflags", "+faststart"]
        
        cmd.append(output_path)
        return cmd

    def _start_segment(self, output_path):
        cmd = self._build_command(output_path)
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
        
        proc = subprocess.Popen(cmd, **popen_kwargs)
        
        # 啟動檢查：確保 FFmpeg 已成功掛載輸入源
        time.sleep(0.6)
        if proc.poll() is not None:
            err = proc.stderr.read()
            raise Exception(f"FFmpeg 啟動失敗：\n{err}")
        
        return proc

    def start(self):
        cfg = self.cfg
        out_dir = Path(cfg.get("output_dir"))
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = cfg.get("filename_prefix", "錄影")
        ext = cfg.get("container", "mp4")
        self.final_output_path = str(out_dir / f"{prefix}_{ts}.{ext}")
        
        first_segment = self.final_output_path
        # 如果使用者之後暫停，第一個分段會被當作 segments[0]
        self.segments = [first_segment]
        
        self.proc = self._start_segment(first_segment)
        self.start_time = time.time()
        self.paused = False
        self.pause_offset = 0
        return self.final_output_path

    def _stop_proc(self, proc):
        if not proc:
            return
        try:
            if proc.stdin:
                try:
                    proc.stdin.write("q\n")
                    proc.stdin.flush()
                except (OSError, BrokenPipeError):
                    pass
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except:
                    proc.kill()
        except Exception as e:
            print(f"[Recorder] 停止程序時發生異常: {e}")
            try:
                proc.kill()
            except:
                pass
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream: stream.close()
                except:
                    pass

    def pause(self):
        """真正停止目前的 ffmpeg 錄製"""
        if self.proc and not self.paused:
            print("[Recorder] 暫停錄影，停止目前的 FFmpeg 程序")
            self._stop_proc(self.proc)
            self.proc = None
            self.paused = True
            self._pause_start = time.time()

    def resume(self):
        """開啟新的分段錄影"""
        if self.paused:
            print("[Recorder] 恢復錄影，啟動新的分段")
            self.pause_offset += time.time() - self._pause_start
            
            # 產生新分段檔名
            base_path = Path(self.final_output_path)
            seg_path = str(base_path.parent / f"{base_path.stem}_seg{len(self.segments)}{base_path.suffix}")
            self.segments.append(seg_path)
            
            self.proc = self._start_segment(seg_path)
            self.paused = False

    def stop(self):
        if not self.proc and not self.paused:
            return None
        
        if self.proc:
            self._stop_proc(self.proc)
            self.proc = None
        
        # 如果有多個分段，需要合併
        if len(self.segments) > 1:
            print(f"[Recorder] 正在合併 {len(self.segments)} 個分段...")
            self._merge_segments()
        
        print(f"[Recorder] 錄影已完整完成：{self.final_output_path}")
        return self.final_output_path

    def _merge_segments(self):
        ffmpeg = self.cfg.get("ffmpeg_path", "ffmpeg")
        # 建立 concat 清單檔案
        list_path = Path(self.final_output_path).parent / "concat_list.txt"
        with open(list_path, "w", encoding="utf-8") as f:
            for seg in self.segments:
                # ffmpeg concat 需要跳脫路徑或使用相對路徑
                abs_path = os.path.abspath(seg).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")
        
        # 最終合併後的暫時路徑 (避免覆蓋到第一個分段)
        temp_final = str(Path(self.final_output_path).parent / f"merged_{Path(self.final_output_path).name}")
        
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c", "copy", temp_final
        ]
        
        try:
            subprocess.run(cmd, creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0, check=True)
            # 合併成功後，刪除所有分段與清單檔案
            for seg in self.segments:
                try: os.remove(seg)
                except: pass
            try: os.remove(list_path)
            except: pass
            
            # 將合併後的檔案重新命名為最終目標
            if os.path.exists(self.final_output_path):
                os.remove(self.final_output_path)
            os.rename(temp_final, self.final_output_path)
        except Exception as e:
            print(f"[Recorder] 合併分段失敗: {e}")

    def elapsed(self):
        if not self.start_time:
            return 0
        if self.paused:
            return self._pause_start - self.start_time - self.pause_offset
        return time.time() - self.start_time - self.pause_offset
