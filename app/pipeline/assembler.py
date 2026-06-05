"""Video assembly with FFmpeg.

Each scene becomes a clip whose length matches its narration audio. A clip can
be built from a still frame (optionally with Ken Burns motion) or from a b-roll
video used as a moving background. Clips get short fades for rhythm, are
concatenated, optional background music is mixed in, and captions (static SRT
or animated karaoke ASS) are burned on top.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

FFMPEG = shutil.which("ffmpeg")

WIDTH, HEIGHT, FPS = 1080, 1920, 30
FADE = 0.18  # seconds of fade in/out per clip


class FFmpegUnavailable(RuntimeError):
    pass


def available() -> bool:
    return FFMPEG is not None


@dataclass
class Clip:
    audio: Path
    duration: float
    image: Optional[Path] = None   # still frame
    video: Optional[Path] = None   # b-roll background (takes precedence)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _ken_burns(duration: float, index: int) -> str:
    """A zoom filter chain for a still image, varying the focal point."""
    frames = max(1, int(round(duration * FPS)))
    # gentle zoom-in; vary the focal point per scene for variety
    focal = index % 3
    if focal == 0:      # center
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif focal == 1:    # drift up
        x, y = "iw/2-(iw/zoom/2)", "0"
    else:               # drift down
        x, y = "iw/2-(iw/zoom/2)", "ih-ih/zoom"
    # upscale first so zoom keeps quality
    return (f"scale={int(WIDTH*1.5)}:{int(HEIGHT*1.5)},"
            f"zoompan=z='min(zoom+0.0015,1.18)':d={frames}:x='{x}':y='{y}':"
            f"s={WIDTH}x{HEIGHT}:fps={FPS}")


def _fades(duration: float) -> str:
    out = max(0.0, duration - FADE)
    return f"fade=t=in:st=0:d={FADE},fade=t=out:st={out:.3f}:d={FADE}"


def _render_clip(clip: Clip, out: Path, index: int, motion: bool,
                 fades: bool = True) -> None:
    # In crossfade mode (fades=False) transitions are handled by xfade later,
    # so individual clips must NOT fade to black at their edges.
    afade = ""
    if fades:
        afade = (f"afade=t=in:st=0:d={FADE},"
                 f"afade=t=out:st={max(0.0, clip.duration-FADE):.3f}:d={FADE}")
    if clip.video and Path(clip.video).exists():
        # b-roll background: loop/trim to duration, cover-crop, darken
        vf = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
              f"crop={WIDTH}:{HEIGHT},eq=brightness=-0.18,setsar=1")
        if fades:
            vf += f",{_fades(clip.duration)}"
        cmd = [
            FFMPEG, "-y",
            "-stream_loop", "-1", "-i", str(clip.video),
            "-i", str(clip.audio),
            "-t", f"{clip.duration:.3f}",
            "-vf", vf,
        ]
    else:
        motion_vf = _ken_burns(clip.duration, index) if motion \
            else f"scale={WIDTH}:{HEIGHT},setsar=1"
        vf = motion_vf + (f",{_fades(clip.duration)}" if fades else "")
        cmd = [
            FFMPEG, "-y",
            "-loop", "1", "-framerate", str(FPS), "-t", f"{clip.duration:.3f}",
            "-i", str(clip.image),
            "-i", str(clip.audio),
            "-vf", vf,
        ]
    if afade:
        cmd += ["-af", afade]
    cmd += [
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest", "-t", f"{clip.duration:.3f}",
        str(out),
    ]
    _run(cmd)


def _crossfade(parts: List[Path], durations: List[float], out: Path,
               transition: float) -> None:
    """Chain clips with real xfade (video) + acrossfade (audio) transitions."""
    n = len(parts)
    t = max(0.05, min(transition, min(durations) / 2))
    inputs: List[str] = []
    for p in parts:
        inputs += ["-i", str(p)]

    # video xfade chain
    vfilters, alabels = [], []
    prev_v = "[0:v]"
    prefix = 0.0
    for k in range(1, n):
        prefix += durations[k - 1]
        offset = prefix - k * t
        out_v = f"[vx{k}]"
        vfilters.append(
            f"{prev_v}[{k}:v]xfade=transition=fade:duration={t:.3f}:"
            f"offset={offset:.3f}{out_v}")
        prev_v = out_v
    # audio acrossfade chain
    afilters = []
    prev_a = "[0:a]"
    for k in range(1, n):
        out_a = f"[ax{k}]"
        afilters.append(f"{prev_a}[{k}:a]acrossfade=d={t:.3f}{out_a}")
        prev_a = out_a

    total = sum(durations) - (n - 1) * t
    vfilters.append(f"{prev_v}fade=t=in:st=0:d=0.3,"
                    f"fade=t=out:st={max(0.0, total-0.3):.3f}:d=0.3[vout]")
    filtergraph = ";".join(vfilters + afilters)

    cmd = [FFMPEG, "-y", *inputs,
           "-filter_complex", filtergraph,
           "-map", "[vout]", "-map", prev_a,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
           str(out)]
    _run(cmd)


def assemble(clips: List[Clip], out_path: Path,
             subtitles: Optional[Path] = None,
             subtitles_ass: Optional[Path] = None,
             music: Optional[Path] = None,
             music_volume: float = 0.12,
             motion: bool = True,
             transition: str = "crossfade",
             transition_seconds: float = 0.4) -> Path:
    if not available():
        raise FFmpegUnavailable("ffmpeg not found. Install with: apt-get install ffmpeg")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    crossfade = transition == "crossfade" and len(clips) > 1

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        parts: List[Path] = []
        for i, clip in enumerate(clips):
            part = tmp / f"part_{i:02d}.mp4"
            _render_clip(clip, part, index=i, motion=motion, fades=not crossfade)
            parts.append(part)

        joined = tmp / "joined.mp4"
        if crossfade:
            _crossfade(parts, [c.duration for c in clips], joined,
                       transition=transition_seconds)
        else:
            concat_file = tmp / "concat.txt"
            concat_file.write_text(
                "".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
            _run([
                FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-c", "copy", str(joined),
            ])
        current = joined

        # optional background music mixed under the narration
        if music and Path(music).exists():
            mixed = tmp / "mixed.mp4"
            _run([
                FFMPEG, "-y", "-i", str(current), "-stream_loop", "-1", "-i", str(music),
                "-filter_complex",
                f"[1:a]volume={music_volume}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                str(mixed),
            ])
            current = mixed

        # captions: animated karaoke (ASS) takes precedence over static SRT
        if subtitles_ass and Path(subtitles_ass).exists():
            subbed = tmp / "subbed.mp4"
            _run([
                FFMPEG, "-y", "-i", str(current),
                "-vf", f"ass={subtitles_ass}",
                "-c:a", "copy", str(subbed),
            ])
            current = subbed
        elif subtitles and Path(subtitles).exists():
            subbed = tmp / "subbed.mp4"
            style = ("FontName=DejaVu Sans,Fontsize=14,PrimaryColour=&H00FFFFFF,"
                     "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
                     "Alignment=2,MarginV=120")
            _run([
                FFMPEG, "-y", "-i", str(current),
                "-vf", f"subtitles={subtitles}:force_style='{style}'",
                "-c:a", "copy", str(subbed),
            ])
            current = subbed

        shutil.copy(current, out_path)

    return out_path
