"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class VideoRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=120,
                       description="Argomento del video, es. 'la produttività'")
    num_points: int = Field(3, ge=1, le=5, description="Numero di punti chiave")
    lang: str = Field("it", description="Lingua (it, en, es full; altre via TTS)")
    style: str = Field("slide", pattern="^(slide|ai)$",
                       description="Stile visivo: 'slide' (gradienti) o 'ai' (Stable Diffusion)")
    template: str = Field("classic", pattern="^(classic|quiz|top5|storytelling)$",
                          description="Template del video")
    animate: bool = Field(True, description="Movimento Ken Burns + testo animato karaoke")
    broll: bool = Field(False, description="Usa clip b-roll da assets/broll come sfondo")
    transition: str = Field("crossfade", pattern="^(crossfade|cut)$",
                            description="Transizione tra le scene")
    seed: Optional[int] = Field(None, description="Seed per output riproducibile")


class JobStatus(BaseModel):
    id: str
    state: str                 # queued | running | done | error
    stage: str = ""
    progress: float = 0.0
    topic: str = ""
    error: Optional[str] = None
    warnings: List[str] = []
    artifacts: dict = {}       # name -> relative download path
