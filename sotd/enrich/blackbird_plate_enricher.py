import re
from typing import Any, Dict, Optional

from .enricher import BaseEnricher


class BlackbirdPlateEnricher(BaseEnricher):
    """Enricher for extracting Blackland Blackbird plate type (Standard, Lite, OC)."""

    @property
    def target_field(self) -> str:
        return "razor"

    def applies_to(self, record: Dict[str, Any]) -> bool:
        if "razor" not in record or record["razor"] is None:
            return False
        razor = record["razor"]
        if not isinstance(razor, dict):
            return False
        matched_data = razor.get("matched", {})
        if not matched_data:
            return False
        brand = matched_data.get("brand", "")
        model = matched_data.get("model", "")
        return brand == "Blackland" and "Blackbird" in model

    def enrich(
        self,
        field_data: Dict[str, Any],
        original_comment: str,
        record: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        # Use the full comment text for plate extraction since plate info is in the comment
        # The original_comment parameter contains the full user comment text
        plate = self._extract_plate(original_comment)
        if plate:
            # Prepare extracted data
            extracted_data = {
                "plate": plate,
            }

            # Use BaseEnricher's single source method for consistency
            return self._create_single_source_enriched_data(extracted_data, "user_comment")
        return None

    def _extract_plate(self, text: str) -> Optional[str]:
        # Order: OC (open comb), Lite, Standard
        if re.search(r"\b(open\s*comb|oc)\b", text, re.IGNORECASE):
            return "OC"
        if re.search(r"\blite\b", text, re.IGNORECASE):
            return "Lite"
        if re.search(r"\bstandard\b", text, re.IGNORECASE):
            return "Standard"
        # No plate mentioned: return None rather than inventing the
        # Standard default. An unobserved plate is not an enrichment;
        # downstream counts must only see plates the poster named.
        return None
