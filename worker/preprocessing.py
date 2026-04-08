"""Image preprocessing for OCR."""
import cv2
import numpy as np
from PIL import Image


class ImagePreprocessor:
    """Preprocesses images to improve OCR accuracy."""

    MAX_DIMENSION = 3000  # Max dimension in pixels

    def preprocess(self, image: Image.Image) -> Image.Image:
        """
        Apply preprocessing pipeline to an image.

        Steps:
        1. Auto-deskew
        2. Resize if too large
        3. Contrast enhancement (CLAHE)
        4. Denoise for low-quality photos
        """
        # Convert PIL to OpenCV format
        img = self._pil_to_cv(image)

        # Auto-deskew
        img = self._deskew(img)

        # Resize if too large
        img = self._resize(img)

        # Contrast enhancement
        img = self._apply_clahe(img)

        # Denoise
        img = self._denoise(img)

        # Convert back to PIL
        return self._cv_to_pil(img)

    def _pil_to_cv(self, pil_image: Image.Image) -> np.ndarray:
        """Convert PIL Image to OpenCV format."""
        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    def _cv_to_pil(self, cv_image: np.ndarray) -> Image.Image:
        """Convert OpenCV image to PIL format."""
        return Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB))

    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """Detect and correct skew angle."""
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Threshold to get clean text area
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Find contours
        coords = np.column_stack(np.where(binary > 0))

        if len(coords) == 0:
            return img

        # Calculate angle
        angle = cv2.minAreaRect(coords)[-1]

        # Adjust angle
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # Only correct if angle is significant (> 0.5 degrees)
        if abs(angle) < 0.5:
            return img

        # Rotate
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        return img

    def _resize(self, img: np.ndarray) -> np.ndarray:
        """Resize image if too large."""
        h, w = img.shape[:2]
        max_dim = max(h, w)

        if max_dim > self.MAX_DIMENSION:
            scale = self.MAX_DIMENSION / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        return img

    def _apply_clahe(self, img: np.ndarray) -> np.ndarray:
        """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)."""
        # Convert to LAB color space
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

        # Split channels
        l, a, b = cv2.split(lab)

        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)

        # Merge channels
        lab = cv2.merge([l, a, b])

        # Convert back to BGR
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """Apply denoising for low-quality photos."""
        # FastNlMeansDenoisingColored is good for photos
        # Small h parameter (3-10) preserves text quality while reducing noise
        return cv2.fastNlMeansDenoisingColored(img, None, h=3, hForColorComponents=10, templateWindowSize=7)
