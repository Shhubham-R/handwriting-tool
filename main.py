import io
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ocr import OCRService
from synthesis import HandwritingSynthesizer, load_styles_catalog
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MODELS_DIR = BASE_DIR / "models"
STYLES_DIR = BASE_DIR / "styles"
CUSTOM_TROCR_DIR = MODELS_DIR / "custom_trocr"

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("handwriting-tool")

ocr_service: Optional[OCRService] = None
synth_service: Optional[HandwritingSynthesizer] = None


class GenerateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    style: str = Field(default="default", min_length=1, max_length=100)


class SaveStyleRequest(BaseModel):
    style_name: str = Field(..., min_length=1, max_length=100)
    sample_text: str = Field(default="", max_length=5000)
    slant_degrees: float = 0.0
    stroke_width: float = 2.2
    letter_spacing: float = 0.0
    word_spacing: float = 16.0
    baseline_jitter: float = 2.0
    pressure_variance: float = 0.3
    size_scale: float = 1.0
    seed_bias: float = 0.5


class StyleFromImageRequest(BaseModel):
    style_name: str = Field(..., min_length=1, max_length=100)
    sample_text: str = Field(default="", max_length=5000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_service, synth_service
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    STYLES_DIR.mkdir(parents=True, exist_ok=True)

    ocr_service = OCRService(
        model_dir=MODELS_DIR,
        custom_model_dir=CUSTOM_TROCR_DIR,
        primary_model_name="microsoft/trocr-large-handwritten",
        fallback_model_name="microsoft/trocr-base-handwritten",
    )
    synth_service = HandwritingSynthesizer(styles_dir=STYLES_DIR)
    logger.info("Services initialized")
    yield


app = FastAPI(title="Handwriting Tool", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    if ocr_service is None or synth_service is None:
        return {"status": "starting"}
    return {
        "status": "ok",
        "ocr": ocr_service.status(),
        "styles": load_styles_catalog(STYLES_DIR),
    }


@app.get("/styles")
def list_styles():
    return {"styles": load_styles_catalog(STYLES_DIR)}


@app.get("/style-previews")
def style_previews():
    if synth_service is None:
        raise HTTPException(status_code=503, detail="Synthesis service not ready")
    sample = "The quick brown fox jumps over 123"
    previews = []
    for style in load_styles_catalog(STYLES_DIR):
        try:
            rendered = synth_service.generate(text=sample, style_name=style["name"])
            previews.append({
                "name": style["name"],
                "sample_text": style.get("sample_text", ""),
                "svg": rendered["svg"],
            })
        except Exception as exc:
            previews.append({
                "name": style["name"],
                "sample_text": style.get("sample_text", ""),
                "error": str(exc),
            })
    return {"previews": previews}


@app.post("/styles")
def save_style(payload: SaveStyleRequest):
    if synth_service is None:
        raise HTTPException(status_code=503, detail="Synthesis service not ready")
    style = synth_service.save_style(payload.model_dump())
    return {"saved": True, "style": style}


@app.post("/styles/from-image")
async def create_style_from_image(style_name: str = Form(...), sample_text: str = Form(""), file: UploadFile = File(...)):
    if synth_service is None:
        raise HTTPException(status_code=503, detail="Synthesis service not ready")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")
    try:
        raw = await file.read()
        image = Image.open(io.BytesIO(raw)).convert("L")
        style = synth_service.create_style_from_sample_image(style_name=style_name, image=image, sample_text=sample_text)
        return {"saved": True, "style": style}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not build style from image: {exc}") from exc


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")
    if ocr_service is None:
        raise HTTPException(status_code=503, detail="OCR service not ready")

    try:
        image_bytes = await file.read()
        result = ocr_service.transcribe(image_bytes=image_bytes, filename=file.filename or "upload")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unhandled OCR error")
        raise HTTPException(status_code=500, detail=f"Unexpected OCR error: {exc}") from exc


@app.post("/generate")
def generate(payload: GenerateRequest):
    if synth_service is None:
        raise HTTPException(status_code=503, detail="Synthesis service not ready")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    try:
        result = synth_service.generate(text=text, style_name=payload.style)
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}") from exc


@app.post("/train")
async def train(file: UploadFile = File(...)):
    if ocr_service is None:
        raise HTTPException(status_code=503, detail="OCR service not ready")
    filename = file.filename or "dataset.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Training upload must be a .zip file")

    try:
        archive_bytes = await file.read()
        result = ocr_service.prepare_training_stub(archive_bytes=archive_bytes, filename=filename)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Training preparation failed")
        raise HTTPException(status_code=500, detail=f"Training preparation failed: {exc}") from exc


@app.get("/download/styles/{style_name}")
def download_style(style_name: str):
    path = STYLES_DIR / f"{style_name}.npz"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Style not found")
    return FileResponse(path)


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
