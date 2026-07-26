from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.core.config import get_settings

settings = get_settings()


@dataclass(slots=True)
class VideoProbe:
    duration_seconds: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str


class VideoTranscodeError(RuntimeError):
    """Raised when FFmpeg or FFprobe cannot produce usable media output."""


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise VideoTranscodeError("未找到 FFmpeg/FFprobe，请先安装并加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise VideoTranscodeError("视频转码超时，请缩短视频或降低分辨率") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-2000:]
        raise VideoTranscodeError(f"FFmpeg 处理失败：{detail}") from exc


def probe_video(path: Path) -> VideoProbe:
    result = _run(
        [
            settings.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        timeout=60,
    )
    payload = json.loads(result.stdout or "{}")
    duration = float((payload.get("format") or {}).get("duration") or 0.0)
    width = height = 0
    fps = 0.0
    video_codec = audio_codec = ""
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") == "video" and not video_codec:
            video_codec = str(stream.get("codec_name") or "")
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            value = str(stream.get("avg_frame_rate") or "0/1")
            try:
                num, den = value.split("/", 1)
                fps = float(num) / max(float(den), 1.0)
            except (ValueError, ZeroDivisionError):
                fps = 0.0
        elif stream.get("codec_type") == "audio" and not audio_codec:
            audio_codec = str(stream.get("codec_name") or "")
    return VideoProbe(duration, width, height, fps, video_codec, audio_codec)


def transcode_browser_video(source: Path, destination: Path) -> VideoProbe:
    """Create a browser/Android-compatible H.264 + AAC MP4 with fast-start metadata."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".working.mp4")
    temporary.unlink(missing_ok=True)
    command = [
        settings.ffmpeg_path,
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        settings.ffmpeg_preset,
        "-crf",
        str(settings.ffmpeg_crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-max_muxing_queue_size",
        "2048",
        str(temporary),
    ]
    _run(command, timeout=settings.ffmpeg_timeout_seconds)
    if not temporary.exists() or temporary.stat().st_size == 0:
        raise VideoTranscodeError("转码结束但未生成有效播放文件")
    shutil.move(str(temporary), str(destination))
    return probe_video(destination)


def transcode_silent_video(source: Path, destination: Path) -> VideoProbe:
    """Transcode an OpenCV-rendered temporary video to H.264 MP4."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".working.mp4")
    temporary.unlink(missing_ok=True)
    _run(
        [
            settings.ffmpeg_path,
            "-y",
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-preset",
            settings.ffmpeg_preset,
            "-crf",
            str(settings.ffmpeg_crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(temporary),
        ],
        timeout=settings.ffmpeg_timeout_seconds,
    )
    shutil.move(str(temporary), str(destination))
    return probe_video(destination)
