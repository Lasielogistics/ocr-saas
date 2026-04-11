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
        DocumentType.CONTAINER_EIR_IN: [
            "equipment interchange", "eir", "container inspection",
            "interchange receipt", "equipment receipt", "in gate",
        ],
        DocumentType.CONTAINER_EIR_OUT: [
            "out gate", "exit gate", "gate out",
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
        DocumentType.CHASSIS_EIR_IN: [
            "chassis", "chassis #", "chassis number", "in gate",
        ],
        DocumentType.CHASSIS_EIR_OUT: [
            "chassis", "chassis #", "out gate", "exit gate",
        ],
        DocumentType.LOAD_CONFIRMATION: [
            "load confirmation", "load #", "pickup", "load number",
            "load confirmation", "dispatch",
        ],
        DocumentType.UNKNOWN: [],
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
        DocumentType.CONTAINER_EIR_IN: [
            r"equipment\s+interchange",
            r"eir\s*\d+",
        ],
        DocumentType.CONTAINER_EIR_OUT: [
            r"out\s+gate",
        ],
        DocumentType.CHASSIS_EIR_IN: [],
        DocumentType.CHASSIS_EIR_OUT: [],
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

        # Special handling for EIR types - check in/out keywords
        eir_score = scores.get(DocumentType.CONTAINER_EIR_IN, 0) + scores.get(DocumentType.CHASSIS_EIR_IN, 0)
        if eir_score > 0:
            if "in gate" in text_lower or "in_gat" in text_lower:
                return DocumentType.CONTAINER_EIR_IN.value
            elif "out gate" in text_lower or "out_gat" in text_lower:
                return DocumentType.CONTAINER_EIR_OUT.value

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

        # Check patterns
        for doc_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    scores[doc_type] = scores.get(doc_type, 0) + 2

        # Special handling for EIR types
        eir_score = scores.get(DocumentType.CONTAINER_EIR_IN, 0) + scores.get(DocumentType.CHASSIS_EIR_IN, 0)
        if eir_score > 0:
            if "in gate" in text_lower or "in_gat" in text_lower:
                return DocumentType.CONTAINER_EIR_IN.value, 0.8
            elif "out gate" in text_lower or "out_gat" in text_lower:
                return DocumentType.CONTAINER_EIR_OUT.value, 0.8

        if not scores or max(scores.values()) == 0:
            return DocumentType.UNKNOWN.value, 0.0

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # Normalize confidence to 0-1
        max_possible_score = len(self.KEYWORDS[best_type])
        if max_possible_score == 0:
            confidence = 0.0
        else:
            confidence = min(best_score / max_possible_score, 1.0)

        if confidence < 0.1:
            return DocumentType.UNKNOWN.value, confidence

        return best_type.value, confidence
