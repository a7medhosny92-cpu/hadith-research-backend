"""In-memory job store with background execution.

Kept deliberately simple (a thread pool + dict) so the service runs with no
external broker. Swap in Celery/RQ + Redis later if you need durability.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .pipeline.orchestrator import create_video, PipelineResult


@dataclass
class Job:
    id: str
    topic: str
    num_points: int
    lang: str
    seed: Optional[int]
    style: str = "slide"
    template: str = "classic"
    animate: bool = True
    broll: bool = False
    transition: str = "crossfade"
    state: str = "queued"
    stage: str = ""
    progress: float = 0.0
    error: Optional[str] = None
    result: Optional[PipelineResult] = None


class JobStore:
    def __init__(self, output_root: Path, max_workers: int = 2):
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, topic: str, num_points: int, lang: str,
               seed: Optional[int], style: str = "slide",
               template: str = "classic", animate: bool = True,
               broll: bool = False, transition: str = "crossfade") -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, topic=topic, num_points=num_points, lang=lang,
                  seed=seed, style=style, template=template, animate=animate,
                  broll=broll, transition=transition)
        with self._lock:
            self._jobs[job_id] = job
        self._pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def workdir(self, job_id: str) -> Path:
        return self.output_root / job_id

    def _run(self, job: Job) -> None:
        job.state = "running"

        def progress(stage: str, pct: float) -> None:
            job.stage = stage
            job.progress = pct

        try:
            job.result = create_video(
                topic=job.topic,
                workdir=self.workdir(job.id),
                num_points=job.num_points,
                lang=job.lang,
                seed=job.seed,
                style=job.style,
                template=job.template,
                animate=job.animate,
                use_broll=job.broll,
                transition=job.transition,
                progress=progress,
            )
            job.state = "done"
        except Exception as exc:  # noqa: BLE001 - surface any failure to the API
            job.state = "error"
            job.error = f"{type(exc).__name__}: {exc}"

    def artifacts(self, job: Job) -> dict:
        if not job.result:
            return {}
        r = job.result
        arts: dict = {}
        if r.video:
            arts["video"] = "video.mp4"
        if r.storyboard:
            arts["storyboard"] = "storyboard.png"
        if r.subtitles:
            arts["subtitles"] = "captions.srt"
        arts["script"] = "script.json"
        for i, _ in enumerate(r.frames):
            arts[f"frame_{i:02d}"] = f"frame_{i:02d}.png"
        return arts
