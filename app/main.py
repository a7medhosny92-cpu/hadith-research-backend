"""FastAPI service that turns a topic into a viral vertical video.

Endpoints:
  GET  /                      health + capabilities
  POST /videos                submit a generation job  -> {id}
  GET  /videos/{id}           job status + artifact links
  GET  /videos/{id}/files/... download a produced artifact
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from . import config
from .models import VideoRequest, JobStatus
from .jobs import JobStore
from .pipeline import tts, assembler, image_gen

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Viral Video Backend",
    description="Pipeline offline: argomento → script → voce → frame → video verticale.",
    version="1.0.0",
)

store = JobStore(config.OUTPUT_ROOT, max_workers=config.MAX_WORKERS)


@app.get("/")
def ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {
        "service": "viral-video-backend",
        "status": "ok",
        "capabilities": {
            "tts": tts.available(),
            "ffmpeg": assembler.available(),
            "stable_diffusion": image_gen.available(),
        },
        "note": "Senza ffmpeg/espeak-ng la pipeline produce comunque script, "
                "frame, storyboard e sottotitoli.",
    }


@app.post("/videos", response_model=JobStatus, status_code=202)
def create_video_job(req: VideoRequest) -> JobStatus:
    job = store.submit(req.topic, req.num_points, req.lang, req.seed, req.style,
                       req.template, req.animate, req.broll, req.transition)
    return _status(job)


@app.get("/videos/{job_id}", response_model=JobStatus)
def get_video_job(job_id: str) -> JobStatus:
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job non trovato")
    return _status(job)


@app.get("/videos/{job_id}/files/{name}")
def download(job_id: str, name: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job non trovato")
    # prevent path traversal: only allow plain filenames
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="nome file non valido")
    path = store.workdir(job_id) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="file non trovato")
    return FileResponse(path)


def _status(job) -> JobStatus:
    base = f"/videos/{job.id}/files"
    artifacts = {k: f"{base}/{Path(v).name}" for k, v in store.artifacts(job).items()}
    warnings = job.result.warnings if job.result else []
    return JobStatus(
        id=job.id,
        state=job.state,
        stage=job.stage,
        progress=job.progress,
        topic=job.topic,
        error=job.error,
        warnings=warnings,
        artifacts=artifacts,
    )
