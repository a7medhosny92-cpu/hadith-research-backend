"""AI image backgrounds via local Stable Diffusion (optional, GPU-friendly).

This is a *pluggable* backend: if `diffusers`/`torch` and a model are available
it generates a 1080x1920 background per scene; otherwise `available()` returns
False and the pipeline falls back to gradient slides. No paid API is used.

Enable with env vars:
  SD_MODEL  = HuggingFace id or local path (default: stabilityai/sd-turbo)
  SD_DEVICE = cuda | cpu | auto  (default: auto)
  SD_STEPS  = inference steps (default: 4, good for *-turbo models)

The pipeline (768x1344, upscaled to 1080x1920) keeps a portrait aspect ratio
suitable for vertical video.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Portrait generation size (multiple of 8, ~9:16), upscaled later.
GEN_W, GEN_H = 768, 1344

SD_MODEL = os.getenv("SD_MODEL", "stabilityai/sd-turbo")
SD_STEPS = int(os.getenv("SD_STEPS", "4"))


def _torch():
    try:
        import torch  # noqa
        return torch
    except Exception:
        return None


def _device() -> str:
    pref = os.getenv("SD_DEVICE", "auto").lower()
    torch = _torch()
    if torch is None:
        return "none"
    if pref in ("cuda", "cpu"):
        return pref
    return "cuda" if torch.cuda.is_available() else "cpu"


def available() -> bool:
    """True only if diffusers + torch import cleanly and a device exists.

    Note: CPU inference works but is slow; prefer a CUDA machine.
    """
    if os.getenv("SD_DISABLE") == "1":
        return False
    if _torch() is None:
        return False
    try:
        import diffusers  # noqa: F401
    except Exception:
        return False
    return _device() != "none"


@lru_cache(maxsize=1)
def _pipeline():
    import torch
    from diffusers import AutoPipelineForText2Image

    device = _device()
    dtype = torch.float16 if device == "cuda" else torch.float32
    pipe = AutoPipelineForText2Image.from_pretrained(SD_MODEL, torch_dtype=dtype)
    pipe = pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    return pipe


def _prompt_for(topic: str, scene_text: str, kind: str) -> str:
    mood = {
        "hook": "dramatic, eye-catching, high contrast",
        "point": "clean, modern, vibrant",
        "cta": "energetic, bold, inviting",
    }.get(kind, "cinematic")
    return (f"cinematic vertical photo about {topic}, {mood}, "
            f"professional lighting, depth of field, highly detailed, 4k, "
            f"social media background, no text")


def generate(topic: str, scene_text: str, kind: str, out_path: Path,
             seed: Optional[int] = None) -> Optional[Path]:
    """Generate a background image; returns None if SD is unavailable."""
    if not available():
        return None
    import torch

    pipe = _pipeline()
    generator = None
    if seed is not None:
        generator = torch.Generator(device=_device()).manual_seed(seed)

    prompt = _prompt_for(topic, scene_text, kind)
    kwargs = dict(prompt=prompt, width=GEN_W, height=GEN_H,
                  num_inference_steps=SD_STEPS, generator=generator)
    # turbo / lcm models run without classifier-free guidance
    if "turbo" in SD_MODEL or "lcm" in SD_MODEL.lower():
        kwargs["guidance_scale"] = 0.0

    image = pipe(**kwargs).images[0]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, "PNG")
    return out_path
