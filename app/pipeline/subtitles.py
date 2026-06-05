"""Subtitle generation: SRT (static) and ASS (animated karaoke) from timed scenes."""

from __future__ import annotations

from pathlib import Path
from typing import List

# ASS canvas must match the video so positioning/scale line up.
ASS_W, ASS_H = 1080, 1920


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _back_to_back(lines: List[tuple[str, float]]) -> List[tuple[str, float, float]]:
    events, t = [], 0.0
    for text, dur in lines:
        events.append((text, t, t + dur))
        t += dur
    return events


def build_srt(lines: List[tuple[str, float]], out_path: Path) -> Path:
    """`lines` is a list of (text, duration_seconds), shown back-to-back."""
    return build_srt_timed(_back_to_back(lines), out_path)


def build_srt_timed(events: List[tuple[str, float, float]], out_path: Path) -> Path:
    """`events` is a list of (text, start_seconds, end_seconds)."""
    out = []
    for i, (text, start, end) in enumerate(events, start=1):
        out.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out), encoding="utf-8")
    return out_path


def _ass_ts(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _karaoke_text(text: str, duration: float) -> str:
    """Wrap each word in a \\kf tag so it fills in sync with the narration."""
    words = text.split()
    if not words:
        return text
    total_cs = max(1, int(round(duration * 100)))
    weights = [max(1, len(w)) for w in words]
    wsum = sum(weights)
    # distribute centiseconds across words proportionally to length
    durs = [max(1, int(total_cs * w / wsum)) for w in weights]
    # fix rounding so the sum matches the scene duration exactly
    durs[-1] += total_cs - sum(durs)
    return "".join(f"{{\\kf{d}}}{w} " for d, w in zip(durs, words)).strip()


def build_ass(lines: List[tuple[str, float]], out_path: Path,
              font: str = "DejaVu Sans", fontsize: int = 64) -> Path:
    """Animated karaoke captions. `lines` is a list of (text, duration_seconds)."""
    return build_ass_timed(_back_to_back(lines), out_path, font=font, fontsize=fontsize)


def build_ass_timed(events: List[tuple[str, float, float]], out_path: Path,
                    font: str = "DejaVu Sans", fontsize: int = 64) -> Path:
    """Animated karaoke captions from explicit (text, start, end) events.

    The karaoke fill is spread across each caption's visible window so the words
    finish filling exactly when the caption ends (important with crossfades,
    where captions are shorter than the raw narration to avoid overlap).
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {ASS_W}
PlayResY: {ASS_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},{fontsize},&H00FFFFFF,&H00FF7CEC,&H00101010,&H7F000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues = []
    for text, start, end in events:
        kar = _karaoke_text(text, max(0.1, end - start))
        dialogues.append(
            f"Dialogue: 0,{_ass_ts(start)},{_ass_ts(end)},Karaoke,,0,0,0,,{kar}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n".join(dialogues) + "\n", encoding="utf-8")
    return out_path
