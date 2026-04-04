import io
import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, ImageOps

logger = logging.getLogger("handwriting-tool.ocr")


class OCRService:
    def __init__(self, model_dir: Path, custom_model_dir: Path, primary_model_name: str, fallback_model_name: str):
        self.model_dir = Path(model_dir)
        self.custom_model_dir = Path(custom_model_dir)
        self.primary_model_name = primary_model_name
        self.fallback_model_name = fallback_model_name
        self.device = "cpu"
        self._processor = None
        self._model = None
        self._active_model_name: Optional[str] = None
        self._surya_available: Optional[bool] = None

    def status(self) -> Dict[str, Any]:
        return {
            "loaded": self._model is not None,
            "active_model": self._active_model_name,
            "surya_available": self._check_surya_available(),
            "device": self.device,
        }

    def _check_surya_available(self) -> bool:
        if self._surya_available is not None:
            return self._surya_available
        try:
            import surya  # noqa: F401
            self._surya_available = True
        except Exception:
            self._surya_available = False
        return self._surya_available

    def _load_trocr(self):
        if self._model is not None and self._processor is not None:
            return

        try:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel

            model_source = str(self.custom_model_dir) if self.custom_model_dir.exists() else self.primary_model_name
            logger.info("Loading TrOCR model from %s", model_source)
            self._processor = TrOCRProcessor.from_pretrained(model_source)
            self._model = VisionEncoderDecoderModel.from_pretrained(model_source)
            self._model.to(self.device)
            self._model.eval()
            self._active_model_name = model_source
            logger.info("Loaded TrOCR model: %s", model_source)
        except Exception as primary_error:
            logger.warning("Primary TrOCR load failed: %s", primary_error)
            try:
                from transformers import TrOCRProcessor, VisionEncoderDecoderModel

                logger.info("Trying fallback TrOCR model: %s", self.fallback_model_name)
                self._processor = TrOCRProcessor.from_pretrained(self.fallback_model_name)
                self._model = VisionEncoderDecoderModel.from_pretrained(self.fallback_model_name)
                self._model.to(self.device)
                self._model.eval()
                self._active_model_name = self.fallback_model_name
            except Exception as fallback_error:
                logger.warning("Fallback TrOCR load failed: %s", fallback_error)
                self._processor = None
                self._model = None
                self._active_model_name = None

    def _prepare_image(self, image_bytes: bytes) -> Image.Image:
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise ValueError(f"Could not decode image: {exc}") from exc

        image = ImageOps.exif_transpose(image)
        image = ImageOps.autocontrast(image)
        max_side = max(image.size)
        if max_side > 1800:
            scale = 1800 / max_side
            image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
        return image

    def transcribe(self, image_bytes: bytes, filename: str = "upload") -> Dict[str, Any]:
        image = self._prepare_image(image_bytes)
        self._load_trocr()

        if self._model is not None and self._processor is not None:
            try:
                import torch

                pixel_values = self._processor(images=image, return_tensors="pt").pixel_values.to(self.device)
                with torch.no_grad():
                    generated_ids = self._model.generate(
                        pixel_values,
                        max_new_tokens=256,
                        num_beams=4,
                        early_stopping=True,
                    )
                text = self._processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
                return {
                    "text": text,
                    "model": self._active_model_name,
                    "confidence": None,
                    "filename": filename,
                }
            except Exception as exc:
                logger.warning("TrOCR inference failed, trying Surya fallback: %s", exc)
                if self._check_surya_available():
                    return self._run_surya(image=image, filename=filename)
                raise RuntimeError(f"OCR failed and Surya fallback is unavailable: {exc}") from exc

        if self._check_surya_available():
            return self._run_surya(image=image, filename=filename)

        raise RuntimeError(
            "No OCR backend available. Install transformers+torch for TrOCR or install surya-ocr for fallback."
        )

    def _run_surya(self, image: Image.Image, filename: str) -> Dict[str, Any]:
        try:
            from surya.model.detection.model import load_model as load_det_model
            from surya.model.detection.processor import load_processor as load_det_processor
            from surya.model.recognition.model import load_model as load_rec_model
            from surya.model.recognition.processor import load_processor as load_rec_processor
            from surya.ocr import run_ocr

            det_processor = load_det_processor()
            det_model = load_det_model()
            rec_model = load_rec_model()
            rec_processor = load_rec_processor()
            result = run_ocr([image], [["en"]], det_model, det_processor, rec_model, rec_processor)
            pages = []
            for page in result:
                if hasattr(page, "text_lines"):
                    pages.extend([line.text for line in page.text_lines])
            text = "\n".join(line.strip() for line in pages if line and line.strip())
            return {
                "text": text,
                "model": "surya-ocr",
                "confidence": None,
                "filename": filename,
            }
        except Exception as exc:
            raise RuntimeError(f"Surya OCR fallback failed: {exc}") from exc

    def prepare_training_stub(self, archive_bytes: bytes, filename: str) -> Dict[str, Any]:
        staging_dir = self.model_dir / "training_uploads"
        staging_dir.mkdir(parents=True, exist_ok=True)
        unpack_dir = staging_dir / Path(filename).stem
        if unpack_dir.exists():
            for path in sorted(unpack_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
        unpack_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if not names:
                raise ValueError("Zip archive is empty")
            zf.extractall(unpack_dir)

        image_count = 0
        label_count = 0
        for path in unpack_dir.rglob("*"):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                image_count += 1
            if path.suffix.lower() == ".txt":
                label_count += 1

        metadata = {
            "archive": filename,
            "unpacked_to": str(unpack_dir),
            "image_files": image_count,
            "label_files": label_count,
            "ready_for_finetune": image_count > 0 and label_count > 0,
            "next_step": "Run python finetune.py to fine-tune and save to ./models/custom_trocr/",
        }
        (unpack_dir / "training_manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata
