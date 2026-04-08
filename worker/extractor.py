"""Field extraction from OCR text."""
import re
from datetime import datetime
from typing import Optional

from shared.models import ExtractedField, DocumentType


class FieldExtractor:
    """Extracts structured fields from OCR text."""

    # Container number pattern: 4 letters + 7 digits
    CONTAINER_PATTERN = r'\b([A-Z]{4}[0-9]{7})\b'

    # Date patterns
    DATE_PATTERNS = [
        r'(\d{1,2}/\d{1,2}/\d{2,4})',  # MM/DD/YYYY or M/D/YY
        r'(\d{1,2}-\d{1,2}-\d{2,4})',  # MM-DD-YYYY
        r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
        r'(\w+ \d{1,2},? \d{4})',  # January 15, 2024
    ]

    # Amount patterns
    AMOUNT_PATTERNS = [
        r'\$\s*[\d,]+\.?\d*',  # $1,234.56
        r'USD\s*[\d,]+\.?\d*',
        r'[\d,]+\.?\d*\s*(?:USD|dollars?)',
    ]

    # Reference patterns
    REFERENCE_PATTERNS = [
        r'(?:reference|ref|#)[:\s]*([A-Z0-9\-]+)',
        r'(?:po|po#)[:\s]*([A-Z0-9\-]+)',
        r'(?:bol|bill of lading)[:\s]*([A-Z0-9\-]+)',
    ]

    def extract(self, text: str, document_type: str, page_num: int = 0) -> list[dict]:
        """
        Extract fields from OCR text.

        Args:
            text: OCR text content
            document_type: Classified document type
            page_num: Page number for multi-page docs

        Returns:
            List of extracted field dictionaries
        """
        fields = []

        # Always try to extract container numbers
        containers = self._extract_containers(text, page_num)
        fields.extend(containers)

        # Always try to extract dates
        dates = self._extract_dates(text, page_num)
        fields.extend(dates)

        # Extract amounts
        amounts = self._extract_amounts(text, page_num)
        fields.extend(amounts)

        # Extract references
        refs = self._extract_references(text, page_num)
        fields.extend(refs)

        # Type-specific extraction
        doc_type = DocumentType(document_type) if document_type != "unknown" else None

        if doc_type == DocumentType.INVOICE:
            fields.extend(self._extract_invoice_fields(text, page_num))
        elif doc_type == DocumentType.POD:
            fields.extend(self._extract_pod_fields(text, page_num))
        elif doc_type == DocumentType.FUEL_RECEIPT:
            fields.extend(self._extract_fuel_fields(text, page_num))
        elif doc_type == DocumentType.SCALE_TICKET:
            fields.extend(self._extract_scale_fields(text, page_num))

        return fields

    def _extract_containers(self, text: str, page_num: int) -> list[dict]:
        """Extract container numbers."""
        containers = []
        seen = set()

        for match in re.finditer(self.CONTAINER_PATTERN, text):
            container = match.group(1)
            if container not in seen:
                seen.add(container)
                containers.append({
                    "name": "container_number",
                    "value": container,
                    "confidence": 0.95,
                    "page": page_num,
                })

        return containers

    def _extract_dates(self, text: str, page_num: int) -> list[dict]:
        """Extract dates."""
        dates = []

        for pattern in self.DATE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                date_str = match.group(1)
                # Validate it's a reasonable date
                if self._is_valid_date(date_str):
                    dates.append({
                        "name": "date",
                        "value": date_str,
                        "confidence": 0.85,
                        "page": page_num,
                    })
                break  # Only take first match of each pattern

        return dates

    def _extract_amounts(self, text: str, page_num: int) -> list[dict]:
        """Extract monetary amounts."""
        amounts = []
        seen = set()

        for pattern in self.AMOUNT_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                amount = match.group(0)
                if amount not in seen:
                    seen.add(amount)
                    amounts.append({
                        "name": "amount",
                        "value": amount,
                        "confidence": 0.9,
                        "page": page_num,
                    })

        return amounts

    def _extract_references(self, text: str, page_num: int) -> list[dict]:
        """Extract reference numbers."""
        refs = []

        for pattern in self.REFERENCE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                ref = match.group(1)
                if len(ref) >= 3:  # Skip very short matches
                    refs.append({
                        "name": "reference_number",
                        "value": ref,
                        "confidence": 0.8,
                        "page": page_num,
                    })

        return refs

    def _extract_invoice_fields(self, text: str, page_num: int) -> list[dict]:
        """Extract invoice-specific fields."""
        fields = []

        # Invoice number
        inv_match = re.search(r'(?:invoice|inv)[:\s#]*([A-Z0-9\-]+)', text, re.IGNORECASE)
        if inv_match:
            fields.append({
                "name": "invoice_number",
                "value": inv_match.group(1),
                "confidence": 0.9,
                "page": page_num,
            })

        # Customer name (look for "Bill To" pattern)
        bill_to_match = re.search(r'bill\s+to[:\s]*([^\n]+)', text, re.IGNORECASE)
        if bill_to_match:
            fields.append({
                "name": "customer_name",
                "value": bill_to_match.group(1).strip(),
                "confidence": 0.8,
                "page": page_num,
            })

        return fields

    def _extract_pod_fields(self, text: str, page_num: int) -> list[dict]:
        """Extract POD-specific fields."""
        fields = []

        # Recipient name
        delivered_match = re.search(r'delivered\s+to[:\s]*([^\n]+)', text, re.IGNORECASE)
        if delivered_match:
            fields.append({
                "name": "recipient_name",
                "value": delivered_match.group(1).strip(),
                "confidence": 0.8,
                "page": page_num,
            })

        # Driver name
        driver_match = re.search(r'driver[:\s]*([^\n]+)', text, re.IGNORECASE)
        if driver_match:
            fields.append({
                "name": "driver_name",
                "value": driver_match.group(1).strip(),
                "confidence": 0.8,
                "page": page_num,
            })

        return fields

    def _extract_fuel_fields(self, text: str, page_num: int) -> list[dict]:
        """Extract fuel receipt-specific fields."""
        fields = []

        # Gallons
        gal_match = re.search(r'([\d.]+)\s*(?:gallon|gal)', text, re.IGNORECASE)
        if gal_match:
            fields.append({
                "name": "gallons",
                "value": gal_match.group(1),
                "confidence": 0.9,
                "page": page_num,
            })

        # Price per gallon
        ppg_match = re.search(r'(?:price\s+per|ppg)[:\s$]*([\d.]+)', text, re.IGNORECASE)
        if ppg_match:
            fields.append({
                "name": "price_per_gallon",
                "value": ppg_match.group(1),
                "confidence": 0.9,
                "page": page_num,
            })

        # Location
        loc_match = re.search(r'(?:location|station|site)[:\s]*([^\n]+)', text, re.IGNORECASE)
        if loc_match:
            fields.append({
                "name": "fuel_location",
                "value": loc_match.group(1).strip(),
                "confidence": 0.7,
                "page": page_num,
            })

        return fields

    def _extract_scale_fields(self, text: str, page_num: int) -> list[dict]:
        """Extract scale ticket-specific fields."""
        fields = []

        # Gross weight
        gross_match = re.search(r'gross\s+weight[:\s]*([\d,]+)', text, re.IGNORECASE)
        if gross_match:
            fields.append({
                "name": "gross_weight",
                "value": gross_match.group(1) + " lbs",
                "confidence": 0.9,
                "page": page_num,
            })

        # Tare weight
        tare_match = re.search(r'tare\s+weight[:\s]*([\d,]+)', text, re.IGNORECASE)
        if tare_match:
            fields.append({
                "name": "tare_weight",
                "value": tare_match.group(1) + " lbs",
                "confidence": 0.9,
                "page": page_num,
            })

        # Net weight
        net_match = re.search(r'net\s+weight[:\s]*([\d,]+)', text, re.IGNORECASE)
        if net_match:
            fields.append({
                "name": "net_weight",
                "value": net_match.group(1) + " lbs",
                "confidence": 0.9,
                "page": page_num,
            })

        return fields

    def _is_valid_date(self, date_str: str) -> bool:
        """Check if a date string is valid."""
        date_formats = [
            "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y",
            "%m-%d-%Y", "%m-%d-%y",
            "%Y-%m-%d",
            "%B %d, %Y", "%B %d %Y",
        ]

        for fmt in date_formats:
            try:
                datetime.strptime(date_str.replace(",", ""), fmt)
                return True
            except ValueError:
                continue

        return False
