"""Image-based Rice and Maize pest and disease classification."""

from __future__ import annotations

import importlib.util
import io
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class Prediction(BaseModel):
    label_index: int
    canonical_class_id: str
    canonical_class: str
    crop: Literal["Rice", "Maize"]
    category: Literal["disease", "pest", "healthy"]
    confidence: float = Field(ge=0, le=1)


class ClassificationResult(BaseModel):
    predictions: list[Prediction]
    needs_expert_review: bool
    model: str = "improved-002"


class Predictor(Protocol):
    def predict(self, image_path: Any, crop: str, top_k: int) -> list[dict[str, object]]: ...


class CropClassifier:
    """Load the external TorchScript package once, on the first inference request."""

    def __init__(self, package_dir: Path, review_threshold: float = 0.65) -> None:
        self.package_dir = package_dir
        self.review_threshold = review_threshold
        self._predictor: Predictor | None = None
        self._lock = threading.Lock()
        self._inference_slots = threading.BoundedSemaphore(2)

    @property
    def configured(self) -> bool:
        required = ("model.ts", "label_map.json", "portal_inference.py")
        return all((self.package_dir / name).is_file() for name in required)

    def _load(self) -> Predictor:
        if self._predictor is not None:
            return self._predictor
        with self._lock:
            if self._predictor is not None:
                return self._predictor
            helper = self.package_dir / "portal_inference.py"
            if not helper.is_file():
                raise RuntimeError(f"Inference helper not found: {helper}")
            spec = importlib.util.spec_from_file_location("csa_crop_portal_inference", helper)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Could not load inference helper: {helper}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._predictor = module.AgriculturePortalPredictor(self.package_dir)
            return self._predictor

    def classify(self, image: bytes, crop: str, top_k: int) -> ClassificationResult:
        if not self._inference_slots.acquire(blocking=False):
            raise _error(429, "The classifier is busy. Try again shortly.", "classifier-busy")
        try:
            predictions = [Prediction.model_validate(item) for item in self._load().predict(io.BytesIO(image), crop, top_k)]
        finally:
            self._inference_slots.release()
        confidence = predictions[0].confidence if predictions else 0
        return ClassificationResult(
            predictions=predictions,
            needs_expert_review=confidence < self.review_threshold,
        )


ClassifierFactory = Callable[[bytes, str, int], ClassificationResult]


def _error(status: int, message: str, reason: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"message": message, "reason": reason})


def validate_image(content: bytes) -> None:
    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise _error(413, "Image dimensions are too large", "image-too-large")
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as err:
        raise _error(422, "Upload a valid JPEG, PNG or WebP image", "invalid-image") from err


def add_crop_classification_routes(app: FastAPI, service: CropClassifier) -> None:
    @app.get("/api/crop-classification/status")
    def status() -> dict[str, object]:
        return {"configured": service.configured, "crops": ["Rice", "Maize"], "max_upload_bytes": MAX_UPLOAD_BYTES}

    @app.post("/api/crop-classification/predict", response_model=ClassificationResult)
    async def predict(
        crop: Annotated[Literal["Rice", "Maize"], Form()],
        image: Annotated[UploadFile, File()],
        top_k: Annotated[int, Form(ge=1, le=5)] = 3,
    ) -> ClassificationResult:
        if not service.configured:
            raise _error(503, "The crop classifier is not configured", "classifier-unavailable")
        if image.content_type not in ALLOWED_CONTENT_TYPES:
            raise _error(415, "Upload a JPEG, PNG or WebP image", "unsupported-image-type")
        content = await image.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise _error(413, "Image must be 10 MB or smaller", "image-too-large")
        validate_image(content)
        try:
            return await run_in_threadpool(service.classify, content, crop, top_k)
        except HTTPException:
            raise
        except Exception as err:
            raise _error(500, "The classifier could not process this image", "inference-failed") from err
