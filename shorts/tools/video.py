"""FFmpeg 헬퍼: 켄번스 모션 클립, 이어붙이기, 최종 합성, 검수용 측정."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

MOTIONS = ["zoom_in", "pan_down", "zoom_out", "pan_up"]


class FFmpegError(RuntimeError):
    pass


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> str:
    res = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                         capture_output=True, text=True, cwd=cwd)
    if res.returncode != 0:
        raise FFmpegError(res.stderr[-1500:])
    return res.stderr


def probe(path: Path) -> dict:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)], capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "duration": float(data.get("format", {}).get("duration", 0)),
        "width": v.get("width"),
        "height": v.get("height"),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def ffprobe_duration(path: Path) -> float:
    return probe(path)["duration"]


def motion_expr(motion: str, frames: int) -> tuple[str, str, str]:
    p = f"(on/{max(frames - 1, 1)})"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if motion == "zoom_out":
        return f"1.18-0.18*{p}", cx, cy
    if motion == "pan_down":
        return "1.15", cx, f"(ih-ih/zoom)*{p}"
    if motion == "pan_up":
        return "1.15", cx, f"(ih-ih/zoom)*(1-{p})"
    return f"1+0.18*{p}", cx, cy  # zoom_in


def render_clip(image: Path, duration: float, out: Path, motion: str, w: int, h: int, fps: int) -> Path:
    frames = max(int(round(duration * fps)), 1)
    z, x, y = motion_expr(motion, frames)
    vf = (
        f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
        "format=yuv420p"
    )
    run_ffmpeg(["-i", str(image), "-vf", vf, "-frames:v", str(frames), "-r", str(fps),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(out)])
    return out


def concat_videos(clips: list[Path], out: Path) -> Path:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{Path(c).resolve()}'\n" for c in clips))
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)])
    return out


def concat_audio(parts: list[tuple[Path, float]], out: Path) -> Path:
    """[(오디오, 해당 구간 전체 길이)]를 무음 패딩해 이어붙인다."""
    args, filters = [], []
    for i, (path, seg_len) in enumerate(parts):
        args += ["-i", str(path)]
        filters.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=mono,apad=whole_dur={seg_len:.3f}[a{i}]")
    filters.append("".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]")
    run_ffmpeg([*args, "-filter_complex", ";".join(filters), "-map", "[out]", str(out)])
    return out


def compose_final(video: Path, voice: Path, ass: Path, out: Path, bgm: Path | None, bgm_volume: float) -> Path:
    args = ["-i", str(video.resolve()), "-i", str(voice.resolve())]
    fc = [f"[0:v]ass={ass.name}[v]", "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[voice]"]
    if bgm:
        args += ["-stream_loop", "-1", "-i", str(bgm.resolve())]
        fc += [f"[2:a]volume={bgm_volume},afade=t=in:d=1[bgm]",
               "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"]
        amap = "[a]"
    else:
        amap = "[voice]"
    run_ffmpeg([*args, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", amap,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                str(out.resolve())], cwd=ass.parent)
    return out


def extract_frame(video: Path, t: float, out: Path, width: int = 540) -> Path:
    run_ffmpeg(["-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                "-vf", f"scale={width}:-2", "-q:v", "3", str(out)])
    return out


def mean_volume(video: Path) -> float | None:
    res = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "volumedetect",
                          "-vn", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", res.stderr)
    return float(m.group(1)) if m else None
