"""OCR backends for local image text extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class OcrResult:
    text: str
    backend: str
    source: str
    confidence: float


class OcrBackend(Protocol):
    name: str

    def extract_text(self, image_path: str, fallback_text: str = "") -> OcrResult: ...


class MetadataOcrBackend:
    """Fallback backend that uses the metadata ocr_text field."""

    name = "metadata_ocr_text"

    def extract_text(self, image_path: str, fallback_text: str = "") -> OcrResult:
        return OcrResult(
            text=fallback_text.strip(),
            backend=self.name,
            source="metadata",
            confidence=1.0 if fallback_text.strip() else 0.0,
        )


class TesseractOcrBackend:
    """pytesseract backend, with metadata fallback when OCR is unavailable or blank."""

    name = "pytesseract"

    def __init__(self, languages: str = "eng+chi_sim") -> None:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("pytesseract and Pillow are required for the pytesseract backend") from exc

        self._pytesseract = pytesseract
        self._image = Image
        self.languages = languages
        self._fallback = MetadataOcrBackend()

    def extract_text(self, image_path: str, fallback_text: str = "") -> OcrResult:
        try:
            with self._image.open(image_path) as image:
                text = self._pytesseract.image_to_string(image, lang=self.languages).strip()
        except Exception:
            text = ""

        if text:
            return OcrResult(text=text, backend=self.name, source="image", confidence=0.8)
        return self._fallback.extract_text(image_path=image_path, fallback_text=fallback_text)


def build_ocr_backend(kind: str, languages: str = "eng+chi_sim") -> OcrBackend:
    if kind == "metadata":
        return MetadataOcrBackend()
    if kind == "tesseract":
        return TesseractOcrBackend(languages=languages)
    if kind == "auto":
        try:
            return TesseractOcrBackend(languages=languages)
        except RuntimeError:
            return MetadataOcrBackend()
    raise ValueError(f"unsupported OCR backend: {kind}")


def path_exists(path: str) -> bool:
    return Path(path).exists()
