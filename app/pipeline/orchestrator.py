"""End-to-end orchestration: topic -> finished vertical video.

Ties together script generation, TTS, visuals, subtitles and assembly.
Each stage degrades gracefully: if TTS/FFmpeg are missing the pipeline still
produces the script, frames, storyboard and subtitles.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import tts, assembler, image_gen
from .script_gen import generate_script, Script
from .subtitles import build_srt
from .visuals import render_scene, storyboard


@dataclass
class PipelineResult:
    topic: str
    workdir: Path
    script: Script
    frames: List[Path] = field(default_factory=list)
    storyboard: Optional[Path] = None
    subtitles: Optional[Path] = None
    audio_clips: List[Path] = field(default_factory=list)
    video: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "workdir": str(self.workdir),
            "script": self.script.to_dict(),
            "frames": [str(p) for p in self.frames],
            "storyboard": str(self.storyboard) if self.storyboard else None,
            "subtitles": str(self.subtitles) if self.subtitles else None,
            "audio_clips": [str(p) for p in self.audio_clips],
            "video": str(self.video) if self.video else None,
            "warnings": self.warnings,
        }


ProgressFn = Callable[[str, float], None]


def _noop(stage: str, pct: float) -> None:  # pragma: no cover
    pass


def create_video(
    topic: str,
    workdir: Path,
    num_points: int = 3,
    lang: str = "it",
    music: Optional[Path] = None,
    seed: Optional[int] = None,
    style: str = "slide",
    progress: ProgressFn = _noop,
) -> PipelineResult:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    progress("script", 0.05)
    script = generate_script(topic, num_points=num_points, seed=seed)
    result = PipelineResult(topic=topic, workdir=workdir, script=script)

    # 1) voice-over per scene (sets the real per-scene duration)
    progress("tts", 0.20)
    if tts.available(lang):
        for s in script.scenes:
            wav = workdir / f"voice_{s.index:02d}.wav"
            tts.synthesize(s.text, wav, lang=lang)
            s.seconds = round(tts.wav_duration(wav), 3)
            result.audio_clips.append(wav)
    else:
        result.warnings.append("TTS non disponibile: uso durate stimate, nessun audio.")

    # 2) optional AI backgrounds (Stable Diffusion), then frames
    progress("frames", 0.45)
    use_ai = style == "ai"
    if use_ai and not image_gen.available():
        result.warnings.append(
            "Stile 'ai' richiesto ma Stable Diffusion non disponibile "
            "(serve torch+diffusers e preferibilmente una GPU): uso le slide.")
        use_ai = False

    for s in script.scenes:
        bg = None
        if use_ai:
            bg = image_gen.generate(
                topic, s.text, s.kind,
                out_path=workdir / f"bg_{s.index:02d}.png",
                seed=None if seed is None else seed + s.index)
        frame = render_scene(
            kind=s.kind, text=s.text, overlay=s.overlay,
            out_path=workdir / f"frame_{s.index:02d}.png",
            index=s.index, total=len(script.scenes),
            background=bg,
        )
        result.frames.append(frame)

    # 3) storyboard + subtitles + script.json
    progress("subtitles", 0.65)
    result.storyboard = storyboard(result.frames, workdir / "storyboard.png")
    result.subtitles = build_srt(
        [(s.text, s.seconds) for s in script.scenes], workdir / "captions.srt")
    (workdir / "script.json").write_text(
        json.dumps(script.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) assemble mp4
    progress("assemble", 0.80)
    if assembler.available() and result.audio_clips:
        clips = [
            assembler.Clip(image=result.frames[i], audio=result.audio_clips[i],
                           duration=script.scenes[i].seconds)
            for i in range(len(script.scenes))
        ]
        result.video = assembler.assemble(
            clips, workdir / "video.mp4",
            subtitles=result.subtitles, music=music)
    else:
        if not assembler.available():
            result.warnings.append("FFmpeg non disponibile: nessun .mp4 prodotto.")
        elif not result.audio_clips:
            result.warnings.append("Nessun audio: impossibile montare il .mp4.")

    progress("done", 1.0)
    return result
