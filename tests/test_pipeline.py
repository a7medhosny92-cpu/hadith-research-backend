"""Tests for the offline portions of the pipeline.

Stages that need external binaries (espeak-ng, ffmpeg) are skipped when those
binaries are absent, so the suite passes in any environment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.script_gen import generate_script
from app.pipeline.templates import build_script, TEMPLATES
from app.pipeline.visuals import render_scene, storyboard, WIDTH, HEIGHT
from app.pipeline.subtitles import build_srt, build_ass, build_srt_timed, build_ass_timed
from app.pipeline.orchestrator import create_video
from app.pipeline import tts, assembler, broll, i18n


def test_script_structure_is_hook_points_cta():
    s = generate_script("la produttività", num_points=3, seed=1)
    kinds = [sc.kind for sc in s.scenes]
    assert kinds[0] == "hook"
    assert kinds[-1] == "cta"
    assert kinds.count("point") == 3
    assert all(sc.seconds > 0 for sc in s.scenes)
    assert s.title and s.hashtags


def test_script_is_reproducible_with_seed():
    a = generate_script("spazio", seed=42)
    b = generate_script("spazio", seed=42)
    assert a.narration == b.narration


def test_render_scene_produces_vertical_frame(tmp_path: Path):
    from PIL import Image

    out = render_scene("hook", "Testo di prova abbastanza lungo da andare a capo",
                       "ASPETTA", tmp_path / "f.png", index=0, total=3)
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (WIDTH, HEIGHT)


def test_storyboard_combines_frames(tmp_path: Path):
    frames = [render_scene("point", f"linea {i}", f"#{i}", tmp_path / f"f{i}.png",
                           index=i, total=3) for i in range(3)]
    sheet = storyboard(frames, tmp_path / "sheet.png")
    assert sheet.exists()


def test_build_srt_format(tmp_path: Path):
    srt = build_srt([("ciao", 2.0), ("mondo", 1.5)], tmp_path / "c.srt")
    text = srt.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:02,000" in text
    assert "00:00:02,000 --> 00:00:03,500" in text


def test_pipeline_produces_artifacts(tmp_path: Path):
    result = create_video("test argomento", workdir=tmp_path, num_points=2, seed=3)
    assert len(result.frames) == len(result.script.scenes)
    assert result.storyboard.exists()
    assert result.subtitles.exists()
    assert (tmp_path / "script.json").exists()


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_every_template_builds(template):
    s = build_script("la produttività", template=template, num_points=3, seed=1)
    assert s.template == template
    assert len(s.scenes) >= 3
    assert all(sc.text and sc.palette for sc in s.scenes)
    # indices are contiguous and ordered
    assert [sc.index for sc in s.scenes] == list(range(len(s.scenes)))


def test_quiz_has_question_answer_pairs():
    s = build_script("spazio", template="quiz", num_points=2, seed=1)
    kinds = [sc.kind for sc in s.scenes]
    assert kinds.count("question") == kinds.count("answer") == 2


def test_top5_counts_down():
    s = build_script("caffè", template="top5", num_points=4, seed=1)
    overlays = [sc.overlay for sc in s.scenes if sc.kind == "rank"]
    assert overlays == ["#4", "#3", "#2", "#1"]


def test_build_ass_is_karaoke(tmp_path: Path):
    ass = build_ass([("ciao mondo bello", 3.0)], tmp_path / "c.ass")
    text = ass.read_text(encoding="utf-8")
    assert "[V4+ Styles]" in text
    assert "\\kf" in text          # karaoke fill tags
    assert "Dialogue:" in text


def test_timed_subtitles_use_explicit_offsets(tmp_path: Path):
    # crossfade-style overlapping timeline: scene 2 starts before scene 1 ends
    events = [("uno", 0.0, 2.0), ("due", 1.6, 3.6)]
    srt = build_srt_timed(events, tmp_path / "c.srt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "00:00:01,600 --> 00:00:03,600" in srt
    ass = build_ass_timed(events, tmp_path / "c.ass").read_text(encoding="utf-8")
    assert "0:00:01.60,0:00:03.60" in ass


@pytest.mark.parametrize("lang", i18n.SUPPORTED)
def test_languages_produce_localized_script(lang):
    s = build_script("productivity", template="classic", num_points=3,
                     seed=1, lang=lang)
    assert len(s.scenes) == 5
    # follow label of that language appears as the CTA overlay
    assert s.scenes[-1].overlay == i18n.get(lang)["labels"]["follow"]


def test_all_language_packs_share_the_same_keys():
    ref = set(i18n.get("en").keys())
    for lang in i18n.SUPPORTED:
        assert set(i18n.get(lang).keys()) == ref, lang


def test_animate_produces_ass(tmp_path: Path):
    result = create_video("prova", workdir=tmp_path, num_points=2, seed=3,
                          animate=True)
    assert result.subtitles_ass is not None
    assert result.subtitles_ass.exists()


def test_broll_picks_from_library(tmp_path: Path, monkeypatch):
    lib = tmp_path / "broll"
    lib.mkdir()
    (lib / "produttivita_office.mp4").write_bytes(b"x")
    (lib / "random.mp4").write_bytes(b"x")
    monkeypatch.setattr(broll, "BROLL_DIR", lib)
    broll._library.cache_clear()
    assert broll.available()
    chosen = broll.pick("produttivita", "consigli per la produttivita", seed=1)
    assert chosen.name == "produttivita_office.mp4"  # keyword match wins
    broll._library.cache_clear()


@pytest.mark.skipif(not tts.available(), reason="espeak-ng non installato")
def test_tts_creates_audio(tmp_path: Path):
    wav = tts.synthesize("prova della sintesi vocale", tmp_path / "v.wav", lang="it")
    assert wav.exists()
    assert tts.wav_duration(wav) > 0


@pytest.mark.skipif(not (tts.available() and assembler.available()),
                    reason="ffmpeg/espeak-ng non installati")
def test_full_video_render(tmp_path: Path):
    result = create_video("video completo di prova", workdir=tmp_path,
                          num_points=2, seed=5)
    assert result.video is not None
    assert result.video.exists()
    assert result.video.stat().st_size > 0
