"""End-to-end orchestration: topic -> finished vertical video.

Ties together template/script generation, TTS, visuals (still or AI/b-roll),
subtitles (static or animated karaoke) and assembly (Ken Burns motion + fades).
Each stage degrades gracefully: if TTS/FFmpeg are missing the pipeline still
produces the script, frames, storyboard and subtitles.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import tts, assembler, image_gen, broll, i18n
from .script_gen import Script
from .templates import build_script
from .subtitles import build_srt_timed, build_ass_timed
from .visuals import render_scene, storyboard


@dataclass
class PipelineResult:
    topic: str
    workdir: Path
    script: Script
    frames: List[Path] = field(default_factory=list)
    storyboard: Optional[Path] = None
    subtitles: Optional[Path] = None
    subtitles_ass: Optional[Path] = None
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
            "subtitles_ass": str(self.subtitles_ass) if self.subtitles_ass else None,
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
    voice: Optional[str] = None,
    music: Optional[Path] = None,
    seed: Optional[int] = None,
    style: str = "slide",
    template: str = "classic",
    animate: bool = True,
    use_broll: bool = False,
    transition: str = "crossfade",
    transition_seconds: float = 0.4,
    progress: ProgressFn = _noop,
) -> PipelineResult:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    progress("script", 0.05)
    script = build_script(topic, template=template, num_points=num_points,
                          seed=seed, lang=lang)
    result = PipelineResult(topic=topic, workdir=workdir, script=script)

    # 1) voice-over per scene (sets the real per-scene duration)
    progress("tts", 0.20)
    if tts.available(lang, voice):
        for s in script.scenes:
            wav = workdir / f"voice_{s.index:02d}.wav"
            tts.synthesize(s.text, wav, lang=lang, voice=voice)
            s.seconds = round(tts.wav_duration(wav), 3)
            result.audio_clips.append(wav)
    else:
        result.warnings.append("TTS non disponibile: uso durate stimate, nessun audio.")

    # 2) optional AI backgrounds + b-roll, then frames
    progress("frames", 0.45)
    use_ai = style == "ai"
    if use_ai and not image_gen.available():
        result.warnings.append(
            "Stile 'ai' richiesto ma Stable Diffusion non disponibile "
            "(serve torch+diffusers e preferibilmente una GPU): uso le slide.")
        use_ai = False
    if use_broll and not broll.available():
        result.warnings.append(
            "B-roll richiesto ma nessuna clip in assets/broll: uso le immagini.")
        use_broll = False

    # Animated karaoke is rendered by libass (ASS subtitle track) and the still
    # frame stays caption-free. But libass lays out \k karaoke left-to-right and
    # ignores bidi, so RTL languages (Arabic) would come out word-reversed —
    # for those we bake the correctly-shaped caption into the frame instead and
    # keep motion + crossfade.
    rtl = i18n.is_rtl(lang)
    karaoke = animate and not rtl
    bake_caption = not karaoke
    if animate and rtl:
        result.warnings.append(
            "Lingua RTL: uso didascalie statiche corrette invece del karaoke "
            "(libass non supporta l'ordine RTL nel karaoke).")

    broll_clips: List[Optional[Path]] = []
    for s in script.scenes:
        bg = None
        if use_ai:
            bg = image_gen.generate(
                topic, s.text, s.kind,
                out_path=workdir / f"bg_{s.index:02d}.png",
                seed=None if seed is None else seed + s.index)
        clip = broll.pick(topic, s.text, seed=None if seed is None else seed + s.index) \
            if use_broll else None
        broll_clips.append(clip)
        frame = render_scene(
            kind=s.kind, text=s.text, overlay=s.overlay,
            out_path=workdir / f"frame_{s.index:02d}.png",
            index=s.index, total=len(script.scenes),
            background=bg, palette=s.palette, with_caption=bake_caption,
        )
        result.frames.append(frame)

    # 3) storyboard + subtitles + script.json
    # Captions must follow the final timeline. With a real crossfade the clips
    # overlap, so each scene starts `transition` earlier than the previous end.
    progress("subtitles", 0.65)
    result.storyboard = storyboard(result.frames, workdir / "storyboard.png")
    n = len(script.scenes)
    use_xfade = transition == "crossfade" and n > 1
    durations = [s.seconds for s in script.scenes]
    overlap = min(transition_seconds, (min(durations) / 2) if durations else 0) \
        if use_xfade else 0.0

    starts, t = [], 0.0
    for i in range(n):
        starts.append(t)
        t += durations[i] - (overlap if i < n - 1 else 0)
    events = [
        (script.scenes[i].text, starts[i],
         starts[i + 1] if i + 1 < n else starts[i] + durations[i])
        for i in range(n)
    ]
    result.subtitles = build_srt_timed(events, workdir / "captions.srt")
    if karaoke:
        result.subtitles_ass = build_ass_timed(events, workdir / "captions.ass")
    (workdir / "script.json").write_text(
        json.dumps(script.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) assemble mp4
    progress("assemble", 0.80)
    if assembler.available() and result.audio_clips:
        clips = [
            assembler.Clip(
                audio=result.audio_clips[i],
                duration=script.scenes[i].seconds,
                image=result.frames[i],
                video=broll_clips[i],
            )
            for i in range(len(script.scenes))
        ]
        # Captions: when animating we burn the ASS karaoke track; when static the
        # caption is already baked into the frame, so we don't also burn the SRT
        # (that would double up). The .srt is still written as a sidecar file.
        result.video = assembler.assemble(
            clips, workdir / "video.mp4",
            subtitles_ass=result.subtitles_ass,
            music=music, motion=animate,
            transition=transition, transition_seconds=transition_seconds)
    else:
        if not assembler.available():
            result.warnings.append("FFmpeg non disponibile: nessun .mp4 prodotto.")
        elif not result.audio_clips:
            result.warnings.append("Nessun audio: impossibile montare il .mp4.")

    progress("done", 1.0)
    return result
