"""ffmpeg 錄影核心"""
import subprocess
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from .ffmpeg_utils import encoder_args, CREATE_NO_WINDOW


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
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "warning"]

        # ----- 視訊輸入 (gdigrab) -----
        cmd += ["-f", "gdigrab", "-framerate", str(fps)]
        if cfg.get("show_cursor", True):
            cmd += ["-draw_mouse", "1"]
        else:
            cmd += ["-draw_mouse", "0"]

        region = cfg.get("region_mode", "fullscreen")
        if region == "custom" and cfg.get("custom_region"):
            x, y, w, h = cfg["custom_region"]
            # 確保偶數
            w = w - (w % 2)
            h = h - (h % 2)
            cmd += ["-offset_x", str(x), "-offset_y", str(y),
                    "-video_size", f"{w}x{h}", "-i", "desktop"]
        elif region == "window" and cfg.get("window_title"):
            cmd += ["-i", f"title={cfg['window_title']}"]
        else:
            cmd += ["-i", "desktop"]

        # ----- 音訊輸入 -----
        audio_inputs = 0
        if cfg.get("audio_system") and cfg.get("audio_system_device"):
            cmd += ["-f", "dshow", "-i", f"audio={cfg['audio_system_device']}"]
            audio_inputs += 1
        if cfg.get("audio_mic") and cfg.get("audio_mic_device"):
            cmd += ["-f", "dshow", "-i", f"audio={cfg['audio_mic_device']}"]
            audio_inputs += 1

        # ----- 縮放 -----
        res = cfg.get("resolution", "原始")
        vf_filters = []
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
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
        )
        self.start_time = time.time()
        self.paused = False
        self.pause_offset = 0
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
        # 立刻清空，避免重入
        self.proc = None
        try:
            # 送 q 讓 ffmpeg 正常結束 (寫入 moov)；用 communicate 一次處理 stdin/stdout/stderr
            try:
                proc.communicate(input=b"q", timeout=15)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except Exception:
                    proc.kill()
                    try:
                        proc.communicate(timeout=2)
                    except Exception:
                        pass
            except (OSError, ValueError):
                # stdin 可能已被 ffmpeg 關閉，改等待結束
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            # 顯式關閉 pipe 避免 GC 階段拋 OSError 22
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
        return self.output_path

    def elapsed(self):
        if not self.start_time:
            return 0
        if self.paused:
            return self._pause_start - self.start_time - self.pause_offset
        return time.time() - self.start_time - self.pause_offset
