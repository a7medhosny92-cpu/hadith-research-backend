"""Interactive study window for the Arabic tutor.

A FastAPI app that exposes the offline engine (phonology, tajwīd, ṣarf, iʿrāb,
curriculum, vocabulary) to a single-page web UI. The LLM "brain" is not wired
yet (offline-first); a `/api/health` flag advertises that so the UI can show it.

Run:  uvicorn app.arabic.web:app --reload   →  open http://localhost:8000
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import data, phonology, tajweed, morphology, iraab, exercises

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Tutor di Arabo Classico/Coranico", version="0.1.0")


# --- request models ---------------------------------------------------------

class TextIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class SentenceIn(BaseModel):
    sentence: str = Field(..., min_length=1, max_length=2000)


class ConjugateIn(BaseModel):
    root: str = Field(..., min_length=3, max_length=3, description="3 radicali, es. كتب")
    form: int = Field(1, ge=1, le=10)


# --- pages ------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "engine": "offline",
        "capabilities": {
            "phonology": True, "tajweed": True, "sarf": True, "iraab": True,
            "llm_tutor": False,   # hybrid LLM brain not wired yet (offline-first)
        },
    }


# --- letters / phonology ----------------------------------------------------

@app.get("/api/letters")
def letters() -> dict:
    items = [asdict(phonology.get(l["letter"])) for l in data.letters()["letters"]]
    return {"letters": items}


@app.get("/api/letter/{letter}")
def letter(letter: str) -> dict:
    L = phonology.get(letter)
    if not L:
        raise HTTPException(404, "lettera sconosciuta")
    return asdict(L)


# --- tajwīd -----------------------------------------------------------------

@app.post("/api/tajweed")
def analyze_tajweed(body: TextIn) -> dict:
    return {"text": body.text, "findings": tajweed.analyze_dicts(body.text)}


# --- ṣarf -------------------------------------------------------------------

@app.post("/api/conjugate")
def conjugate(body: ConjugateIn) -> dict:
    try:
        c = morphology.conjugate_auto(list(body.root), body.form)
    except morphology.UnsupportedVerb as e:
        raise HTTPException(422, str(e))
    out = c.to_dict()
    out["pronouns"] = [{"key": k, "label": v} for k, v in morphology.PRONOUNS]
    return out


# --- iʿrāb ------------------------------------------------------------------

@app.post("/api/iraab")
def analyze_iraab(body: SentenceIn) -> dict:
    return iraab.analyze(body.sentence).to_dict()


# --- curriculum / vocabulary ------------------------------------------------

@app.get("/api/levels")
def levels() -> dict:
    return data.levels()


# --- exercises / quiz -------------------------------------------------------

class CheckIn(BaseModel):
    id: str
    choice: int = Field(..., ge=0, le=10)


@app.get("/api/exercise/types")
def exercise_types() -> dict:
    return {"types": [{"key": t, "label": exercises.TYPE_LABELS[t]}
                      for t in exercises.TYPES]}


@app.get("/api/exercise")
def exercise(type: str = "random") -> dict:
    try:
        return exercises.generate(type).public()
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/check")
def check_answer(body: CheckIn) -> dict:
    try:
        return exercises.check(body.id, body.choice)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/vocabulary")
def vocabulary() -> dict:
    return data.vocabulary()
