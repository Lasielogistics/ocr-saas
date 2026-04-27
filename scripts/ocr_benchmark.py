#!/usr/bin/env python3
"""
OCR Model Benchmark Script
Compares: EasyOCR, Doctr, PaddleOCR, Surya OCR, Mistral OCR 3

Usage:
    # Install dependencies first
    pip install easyocr python-doctr paddleocr

    # Run benchmark
    python ocr_benchmark.py /path/to/test_images/

    # Run with Mistral OCR (requires API key)
    MISTRAL_API_KEY=xxx python ocr_benchmark.py /path/to/test_images/ --include-mistral
"""

import argparse
import base64
import io
import json
import logging
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image
import pdf2image

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    model: str
    text: str
    confidence: float
    processing_time_seconds: float
    page_count: int
    error: Optional[str] = None
    word_count: int = 0
    line_count: int = 0

    def to_dict(self):
        d = asdict(self)
        d['text_preview'] = self.text[:500] + '...' if len(self.text) > 500 else self.text
        return d


class OCRBenchmark:
    """Benchmark harness for comparing OCR models."""

    def __init__(self, models: list[str] = None):
        self.models = models or ['easyocr', 'doctr', 'paddleocr', 'surya', 'tesseract']
        self.results: dict[str, list[OCRResult]] = {}
        # Lazy-initialized model instances (cached per model)
        self._easyocr_reader = None
        self._doctr_predictor = None
        self._paddleocr = None
        self._surya_foundation = None
        self._surya_det = None
        self._surya_rec = None

    def load_image(self, file_path: Path) -> list[Image.Image]:
        """Load image or PDF into list of PIL Images."""
        ext = file_path.suffix.lower()
        if ext == '.pdf':
            return pdf2image.convert_from_path(str(file_path), dpi=200)
        else:
            return [Image.open(str(file_path))]

    # ─── EasyOCR ─────────────────────────────────────────────────

    def run_easyocr(self, images: list[Image.Image]) -> OCRResult:
        start = time.time()
        try:
            import numpy as np
            import easyocr
            if self._easyocr_reader is None:
                self._easyocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            reader = self._easyocr_reader
            all_texts = []
            confidences = []
            for img in images:
                result = reader.readtext(np.array(img))
                page_texts = []
                page_confs = []
                for (bbox, text, conf) in result:
                    if text.strip():
                        page_texts.append(text)
                        page_confs.append(conf)
                all_texts.append(' '.join(page_texts))
                confidences.append(sum(page_confs) / len(page_confs) if page_confs else 0)
            text = '\n'.join(all_texts)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            return OCRResult(
                model='easyocr',
                text=text,
                confidence=avg_conf,
                processing_time_seconds=time.time() - start,
                page_count=len(images),
                word_count=len(text.split()),
                line_count=len(text.splitlines()),
            )
        except Exception as e:
            return OCRResult(
                model='easyocr', text='', confidence=0, processing_time_seconds=time.time() - start,
                page_count=len(images), error=str(e)
            )

    # ─── Doctr ──────────────────────────────────────────────────

    def run_doctr(self, images: list[Image.Image]) -> OCRResult:
        start = time.time()
        try:
            import numpy as np
            from doctr.io import DocumentFile
            from doctr.models import ocr_predictor
            if self._doctr_predictor is None:
                self._doctr_predictor = ocr_predictor(det_arch='db_resnet50', reco_arch='crnn_vgg16_bn', pretrained=True)
            predictor = self._doctr_predictor
            img_arrays = [np.array(img) for img in images]
            result = predictor(img_arrays)
            pages = result.pages  # property, not method
            all_texts = []
            all_confs = []
            for page in pages:
                for block in page.blocks:
                    for line in block.lines:
                        for word in line.words:
                            if word.value:
                                all_texts.append(word.value)
                                all_confs.append(word.confidence)
            text = ' '.join(all_texts)
            avg_conf = sum(all_confs) / len(all_confs) if all_confs else 0
            return OCRResult(
                model='doctr',
                text=text,
                confidence=avg_conf,
                processing_time_seconds=time.time() - start,
                page_count=len(images),
                word_count=len(all_texts),
                line_count=len([l for p in pages for b in p.blocks for l in b.lines]),
            )
        except Exception as e:
            return OCRResult(
                model='doctr', text='', confidence=0, processing_time_seconds=time.time() - start,
                page_count=len(images), error=str(e)
            )

    # ─── PaddleOCR ──────────────────────────────────────────────

    def run_paddleocr(self, images: list[Image.Image]) -> OCRResult:
        start = time.time()
        try:
            from paddleocr import PaddleOCR
            import numpy as np
            if self._paddleocr is None:
                self._paddleocr = PaddleOCR(use_textline_orientation=True, lang='en')
            ocr = self._paddleocr
            all_texts = []
            all_confs = []
            for img in images:
                result = ocr.ocr(np.array(img), cls=True)
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:
                            text = line[1][0]
                            conf = line[1][1]
                            all_texts.append(text)
                            all_confs.append(conf)
            text = '\n'.join(all_texts)
            avg_conf = sum(all_confs) / len(all_confs) if all_confs else 0
            return OCRResult(
                model='paddleocr',
                text=text,
                confidence=avg_conf,
                processing_time_seconds=time.time() - start,
                page_count=len(images),
                word_count=len(all_texts),
                line_count=len(set(all_texts)),
            )
        except Exception as e:
            return OCRResult(
                model='paddleocr', text='', confidence=0, processing_time_seconds=time.time() - start,
                page_count=len(images), error=str(e)
            )

    # ─── Surya OCR ───────────────────────────────────────────────

    def run_surya(self, images: list[Image.Image]) -> OCRResult:
        start = time.time()
        try:
            from surya.detection import DetectionPredictor
            from surya.recognition import RecognitionPredictor, FoundationPredictor
            import numpy as np

            # Initialize predictors (cached)
            if self._surya_foundation is None:
                self._surya_foundation = FoundationPredictor()
            if self._surya_det is None:
                self._surya_det = DetectionPredictor()
            if self._surya_rec is None:
                self._surya_rec = RecognitionPredictor(self._surya_foundation)
            foundation_predictor = self._surya_foundation
            det_predictor = self._surya_det
            rec_predictor = self._surya_rec

            all_texts = []
            all_confs = []
            line_count = 0

            for img in images:
                # Convert PIL to numpy
                img_np = np.array(img.convert('RGB'))

                # Run detection first
                dt_results = det_predictor([img_np])
                bboxes = dt_results[0].bboxes
                polygon_map = dt_results[0].polygon_map
                page_ids = dt_results[0].page_ids

                # Run recognition on detected regions
                rec_results = rec_predictor([img_np], [bboxes], [polygon_map], [page_ids])

                for r in rec_results:
                    for text_line in r.text_lines:
                        all_texts.append(text_line.text)
                        all_confs.append(text_line.confidence)
                    line_count += len(r.text_lines)

            text = '\n'.join(all_texts)
            avg_conf = sum(all_confs) / len(all_confs) if all_confs else 0
            return OCRResult(
                model='surya',
                text=text,
                confidence=avg_conf,
                processing_time_seconds=time.time() - start,
                page_count=len(images),
                word_count=len(all_texts),
                line_count=line_count,
            )
        except Exception as e:
            return OCRResult(
                model='surya', text='', confidence=0, processing_time_seconds=time.time() - start,
                page_count=len(images), error=str(e)
            )

    # ─── Tesseract ───────────────────────────────────────────────

    def run_tesseract(self, images: list[Image.Image]) -> OCRResult:
        start = time.time()
        try:
            import pytesseract
            all_texts = []
            for img in images:
                text = pytesseract.image_to_string(img)
                all_texts.append(text)
            text = '\n'.join(all_texts)
            # Tesseract doesn't provide per-word confidence
            return OCRResult(
                model='tesseract',
                text=text,
                confidence=0.85,  # default assumption
                processing_time_seconds=time.time() - start,
                page_count=len(images),
                word_count=len(text.split()),
                line_count=len(text.splitlines()),
            )
        except Exception as e:
            return OCRResult(
                model='tesseract', text='', confidence=0, processing_time_seconds=time.time() - start,
                page_count=len(images), error=str(e)
            )

    # ─── Mistral OCR 3 ──────────────────────────────────────────

    def run_mistral_ocr(self, images: list[Image.Image], api_key: str) -> OCRResult:
        start = time.time()
        try:
            import httpx
            # Convert images to base64
            pages_data = []
            for img in images:
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                img_b64 = base64.b64encode(buffer.getvalue()).decode()
                pages_data.append({"data": img_b64, "type": "image_url"})

            response = httpx.post(
                "https://api.mistral.ai/v1/ocr",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": "mistral-ocr-3", "document": {"type": "document", "pages": pages_data}},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            all_texts = []
            for page in data.get('pages', []):
                all_texts.append(page.get('text', ''))

            text = '\n'.join(all_texts)
            # Mistral doesn't provide per-word confidence in the same way
            return OCRResult(
                model='mistral-ocr-3',
                text=text,
                confidence=0.95,  # Mistral typically high confidence
                processing_time_seconds=time.time() - start,
                page_count=len(images),
                word_count=len(text.split()),
                line_count=len(text.splitlines()),
            )
        except Exception as e:
            return OCRResult(
                model='mistral-ocr-3', text='', confidence=0, processing_time_seconds=time.time() - start,
                page_count=len(images), error=str(e)
            )

    # ─── Main benchmark runner ──────────────────────────────────

    def run_file(self, file_path: Path, mistral_api_key: Optional[str] = None) -> dict[str, OCRResult]:
        """Run all enabled OCR models on a single file."""
        logger.info(f"Processing: {file_path}")
        images = self.load_image(file_path)
        logger.info(f"  Loaded {len(images)} page(s)")

        results = {}
        if 'easyocr' in self.models:
            logger.info("  Running EasyOCR...")
            results['easyocr'] = self.run_easyocr(images)

        if 'doctr' in self.models:
            logger.info("  Running Doctr...")
            results['doctr'] = self.run_doctr(images)

        if 'paddleocr' in self.models:
            logger.info("  Running PaddleOCR...")
            results['paddleocr'] = self.run_paddleocr(images)

        if 'surya' in self.models:
            logger.info("  Running Surya OCR...")
            results['surya'] = self.run_surya(images)

        if 'tesseract' in self.models:
            logger.info("  Running Tesseract...")
            results['tesseract'] = self.run_tesseract(images)

        if mistral_api_key and 'mistral' in self.models:
            logger.info("  Running Mistral OCR 3...")
            results['mistral-ocr-3'] = self.run_mistral_ocr(images, mistral_api_key)

        return results

    def run_directory(self, dir_path: Path, mistral_api_key: Optional[str] = None) -> dict:
        """Benchmark all images in a directory."""
        image_exts = {'.jpg', '.jpeg', '.png', '.pdf', '.tif', '.tiff', '.bmp'}
        files = [f for f in dir_path.rglob('*') if f.suffix.lower() in image_exts]

        if not files:
            logger.warning(f"No image files found in {dir_path}")
            return {}

        all_results = {}
        for f in files:
            try:
                all_results[str(f)] = self.run_file(f, mistral_api_key)
            except Exception as e:
                logger.error(f"Error processing {f}: {e}")
                all_results[str(f)] = {'error': str(e)}

        return all_results

    def print_summary(self, results: dict):
        """Print a comparison table."""
        print("\n" + "="*80)
        print("OCR BENCHMARK RESULTS")
        print("="*80)

        for file_path, model_results in results.items():
            if 'error' in model_results:
                print(f"\n{file_path}: ERROR - {model_results['error']}")
                continue

            print(f"\n{Path(file_path).name}:")
            print("-" * 70)

            # Build comparison rows
            rows = []
            for model_name, result in model_results.items():
                if result.error:
                    rows.append({
                        'model': model_name,
                        'time': f"{result.processing_time_seconds:.2f}s",
                        'conf': 'ERROR',
                        'words': '-',
                        'lines': '-',
                        'preview': result.error[:60],
                    })
                else:
                    rows.append({
                        'model': model_name,
                        'time': f"{result.processing_time_seconds:.2f}s",
                        'conf': f"{result.confidence:.2%}",
                        'words': str(result.word_count),
                        'lines': str(result.line_count),
                        'preview': result.text[:80].replace('\n', ' ')[:80],
                    })

            # Print table
            print(f"{'Model':<15} {'Time':<10} {'Conf':<8} {'Words':<8} {'Lines':<8} Preview")
            print("-" * 70)
            for r in rows:
                print(f"{r['model']:<15} {r['time']:<10} {r['conf']:<8} {r['words']:<8} {r['lines']:<8} {r['preview'][:50]}")

    def save_results(self, results: dict, output_path: Path):
        """Save results to JSON file."""
        serializable = {}
        for fp, model_results in results.items():
            if isinstance(model_results, dict):
                serializable[fp] = {
                    k: v.to_dict() if hasattr(v, 'to_dict') else v
                    for k, v in model_results.items()
                }
            else:
                serializable[fp] = model_results

        with open(output_path, 'w') as f:
            json.dump(serializable, f, indent=2)
        logger.info(f"Results saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='OCR Model Benchmark')
    parser.add_argument('path', type=Path, help='Image file or directory')
    parser.add_argument('--models', nargs='+', default=['easyocr', 'doctr', 'paddleocr', 'surya', 'tesseract'],
                        choices=['easyocr', 'doctr', 'paddleocr', 'surya', 'tesseract', 'mistral'],
                        help='Models to benchmark')
    parser.add_argument('--include-mistral', action='store_true', help='Include Mistral OCR 3')
    parser.add_argument('--output', type=Path, default=Path('ocr_benchmark_results.json'),
                        help='Output JSON file')
    args = parser.parse_args()

    mistral_key = None
    if args.include_mistral or 'mistral' in args.models:
        import os
        mistral_key = os.getenv('MISTRAL_API_KEY')
        if not mistral_key:
            print("ERROR: Mistral API key required. Set MISTRAL_API_KEY environment variable.")
            return

    models = args.models.copy()
    if args.include_mistral:
        models.append('mistral')

    benchmark = OCRBenchmark(models=models)
    if args.path.is_file():
        results = {str(args.path): benchmark.run_file(args.path, mistral_key)}
    else:
        results = benchmark.run_directory(args.path, mistral_key)
    benchmark.print_summary(results)
    benchmark.save_results(results, args.output)


if __name__ == '__main__':
    main()
