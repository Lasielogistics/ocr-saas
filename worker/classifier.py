"""Document classification for OCR."""
import re
from typing import Optional

from shared.models import DocumentType


class DocumentClassifier:
    """Classifies documents based on OCR text content."""

    # Document type keywords
    KEYWORDS = {
        DocumentType.POD: [
            "proof of delivery", "received by", "signed by", "delivered to",
            "delivery receipt", "pod", "proof of delivery",
        ],
        DocumentType.INVOICE: [
            "invoice", "bill to", "amount due", "inv#", "invoice #",
            "total due", "payment terms", "billable to",
        ],
        DocumentType.RECEIPT: [
            "receipt", "paid", "cash", "received payment",
            "thank you for your payment",
        ],
        DocumentType.RATE_CONFIRMATION: [
            "rate confirmation", "quote", "pricing", "rate quote",
            "pricing confirmation", "confirmed rate",
        ],
        DocumentType.FUEL_RECEIPT: [
            "fuel", "diesel", "gallons", "fuel receipt", "gasoline",
            "lp gas", "propane", "fuel card",
        ],
        DocumentType.SCALE_TICKET: [
            "scale ticket", "weight", "gross weight", "tare weight",
            "net weight", "weigh ticket", "scale house",
        ],
        DocumentType.EIR: [
            "equipment interchange", "eir", "container inspection",
            "interchange receipt", "equipment receipt",
        ],
        DocumentType.GATE_TICKET: [
            "gate ticket", "gate pass", "yard", "gate in", "gate out",
        ],
        DocumentType.LOAD_CONFIRMATION: [
            "load confirmation", "load #", "pickup", "load number",
            "load confirmation", "dispatch",
        ],
        DocumentType.TERMINAL_PAPERWORK: [
            "terminal", "port", "apm", "eagle", "wgm", "everport",
            "terminal information",
        ],
        DocumentType.APPOINTMENT_CONFIRMATION: [
            "appointment", "confirmed", "schedule", "time slot",
            "appointment #", "appointment confirmation",
        ],
        DocumentType.CONTAINER_PICKUP: [
            "container pickup", "pickup", "container #", "container number",
            "empty return", "pulling", "unit #",
        ],
        DocumentType.CONTAINER_DROPOFF: [
            "dropoff", "drop off", "delivery", "return",
            "container return",
        ],
        DocumentType.CHASSIS_PAPERWORK: [
            "chassis", "chassis #", "chassis number",
        ],
        DocumentType.YARD_TICKET: [
            "yard ticket", "yard", "yard location",
        ],
        DocumentType.REFERENCE_SHEET: [
            "reference", "customer", "shipper", "consignee",
            "contact", "phone", "email",
        ],
    }

    # Patterns for specific document identification
    PATTERNS = {
        DocumentType.POD: [
            r"proof\s+of\s+delivery",
            r"signed\s+by\s+[\w\s]+",
            r"delivered\s+to\s+[\w\s]+",
        ],
        DocumentType.INVOICE: [
            r"invoice\s*#?\s*\d+",
            r"inv\s*\d+",
            r"amount\s+due\s*\$",
        ],
        DocumentType.EIR: [
            r"equipment\s+interchange",
            r"eir\s*\d+",
        ],
        DocumentType.CONTAINER_PICKUP: [
            r"[A-Z]{4}\s*\d{7}",  # Standard container number
        ],
    }

    def classify(self, text: str, confidence: float = 0.0) -> str:
        """
        Classify document type based on text content.

        Args:
            text: OCR text content
            doc_type: Optional hint for document type

        Returns:
            Document type string
        """
        if not text:
            return DocumentType.UNKNOWN.value

        text_lower = text.lower()

        # Score each document type
        scores = {}

        for doc_type, keywords in self.KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1
            scores[doc_type] = score

        # Check patterns
        for doc_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    scores[doc_type] = scores.get(doc_type, 0) + 2

        # Find best match
        if not scores or max(scores.values()) == 0:
            return DocumentType.UNKNOWN.value

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # If score is too low, return unknown
        if best_score < 1:
            return DocumentType.UNKNOWN.value

        return best_type.value

    def classify_with_confidence(self, text: str) -> tuple[str, float]:
        """
        Classify document and return confidence score.

        Returns:
            tuple of (document_type, confidence)
        """
        if not text:
            return DocumentType.UNKNOWN.value, 0.0

        text_lower = text.lower()
        scores = {}

        for doc_type, keywords in self.KEYWORDS.items():
            score = sum(1 for k in keywords if k in text_lower)
            scores[doc_type] = score

        if not scores or max(scores.values()) == 0:
            return DocumentType.UNKNOWN.value, 0.0

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # Normalize confidence to 0-1
        max_possible_score = len(self.KEYWORDS[best_type])
        confidence = min(best_score / max_possible_score, 1.0)

        if confidence < 0.1:
            return DocumentType.UNKNOWN.value, confidence

        return best_type.value, confidence
