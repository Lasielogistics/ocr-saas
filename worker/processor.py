"""Core OCR processing pipeline."""
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

from preprocessing import ImagePreprocessor
from classifier import DocumentClassifier
from extractor import FieldExtractor

logger = logging.getLogger(__name__)


class OCRProcessor:
    """Main OCR processing orchestrator."""

    def __init__(self):
        self.preprocessor = ImagePreprocessor()
        self.classifier = DocumentClassifier()
        self.extractor = FieldExtractor()

    def process(self, job_id: str, file_path: str) -> dict:
        """
        Process a document through the OCR pipeline.

        Args:
            job_id: Unique job identifier
            file_path: Path to the document file

        Returns:
            dict with processing results
        """
        from pdf2image import convert_from_path

        file_path = Path(file_path)
        ext = file_path.suffix.lower()

        logger.info(f"Processing {file_path} (ext: {ext})")

        # Determine if PDF or image
        if ext == ".pdf":
            # Convert PDF to images
            images = convert_from_path(str(file_path), dpi=200)
            page_count = len(images)
            logger.info(f"PDF converted to {page_count} images")
        else:
            # Load image directly
            images = [Image.open(str(file_path))]
            page_count = 1

        # Process each page
        all_texts = []
        all_confidences = []
        all_fields = []

        for page_num, image in enumerate(images):
            logger.info(f"Processing page {page_num + 1}/{page_count}")

            # Preprocess image
            preprocessed = self.preprocessor.preprocess(image)

            # Run Surya OCR
            text, confidence = self._run_surya_ocr(preprocessed)
            all_texts.append(text)
            all_confidences.append(confidence)

            # Classify document (only on first page for efficiency)
            if page_num == 0:
                doc_type = self.classifier.classify(text, confidence)
            else:
                doc_type = "unknown"

            # Extract fields
            fields = self.extractor.extract(text, doc_type, page_num)
            all_fields.extend(fields)

            logger.info(f"Page {page_num + 1}: type={doc_type}, confidence={confidence:.2f}")

        # Aggregate results
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        combined_text = "\n\n--- Page Break ---\n\n".join(all_texts)

        # Determine overall document type (from first page classification)
        overall_type = self.classifier.classify(combined_text, avg_confidence)

        return {
            "document_type": overall_type,
            "ocr_text": combined_text,
            "page_count": page_count,
            "confidence_score": avg_confidence,
            "extracted_fields": all_fields,
        }

    def _run_surya_ocr(self, image: Image.Image) -> tuple[str, float]:
        """
        Run Surya OCR on an image.

        Returns:
            tuple of (extracted_text, average_confidence)
        """
        try:
            from surya.ocr import run_ocr
            from surya.model.detection.segformer import load_model as load_det_model, load_config as load_det_config
            from surya.model.recognition.model import load_model as load_rec_model
            from surya.model.recognition.config import load_config as load_rec_config

            # For efficiency, we load models once (they're cached)
            # In production, you'd want to initialize these at module level
            langs = ["en"]

            results = run_ocr([image], langs=langs)

            if not results:
                return "", 0.0

            result = results[0]
            text_lines = result.text_lines

            # Combine all text
            full_text = "\n".join([line.text for line in text_lines])

            # Calculate average confidence
            if text_lines:
                avg_conf = sum([line.confidence for line in text_lines]) / len(text_lines)
            else:
                avg_conf = 0.0

            return full_text, avg_conf

        except ImportError as e:
            logger.warning(f"Surya OCR not available: {e}. Using fallback.")
            return self._fallback_ocr(image)

    def _fallback_ocr(self, image: Image.Image) -> tuple[str, float]:
        """Fallback OCR using Tesseract directly."""
        import pytesseract

        text = pytesseract.image_to_string(image)
        # Tesseract doesn't provide confidence in the same way
        # We use a reasonable default
        return text, 0.85


class OCRProcessorLite:
    """Lightweight processor for testing without Surya OCR."""

    def process(self, job_id: str, file_path: str) -> dict:
        """Process using only Tesseract."""
        from pdf2image import convert_from_path
        import pytesseract
        from PIL import Image

        file_path = Path(file_path)
        ext = file_path.suffix.lower()

        if ext == ".pdf":
            images = convert_from_path(str(file_path), dpi=200)
            page_count = len(images)
        else:
            images = [Image.open(str(file_path))]
            page_count = 1

        all_texts = []
        all_confidences = []

        for page_num, image in enumerate(images):
            preprocessed = self.preprocessor.preprocess(image)
            text = pytesseract.image_to_string(preprocessed)
            all_texts.append(text)
            all_confidences.append(0.85)  # Tesseract default confidence

        combined_text = "\n\n--- Page Break ---\n\n".join(all_texts)
        avg_confidence = sum(all_confidences) / len(all_confidences)
        doc_type = self.classifier.classify(combined_text, avg_confidence)
        fields = self.extractor.extract(combined_text, doc_type, 0)

        return {
            "document_type": doc_type,
            "ocr_text": combined_text,
            "page_count": page_count,
            "confidence_score": avg_confidence,
            "extracted_fields": fields,
        }
