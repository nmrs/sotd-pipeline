import re
from typing import Any, Dict, Optional

from .enricher import BaseEnricher


class ChristopherBradleyEnricher(BaseEnricher):
    """Enricher for extracting Karve Christopher Bradley plate specifications.

    Extracts plate level (AA-G) and plate type (SB/OC) from the razor field.
    """

    VALID_PLATE_LEVELS = ["AA", "A", "B", "C", "D", "E", "F", "G"]

    @property
    def target_field(self) -> str:
        return "razor"

    def applies_to(self, record: Dict[str, Any]) -> bool:
        """Determine if this enricher applies to the given record.

        Applies to records with Karve Christopher Bradley razors.
        The catalog should ensure model is always "Christopher Bradley" for Karve brand.
        """
        if "razor" not in record or record["razor"] is None:
            return False

        razor = record["razor"]
        if not isinstance(razor, dict):
            return False

        matched_data = razor.get("matched", {})
        if matched_data:
            brand = matched_data.get("brand", "")
            model = matched_data.get("model", "")
            return brand == "Karve" and model == "Christopher Bradley"
        return False

    def enrich(
        self,
        field_data: Dict[str, Any],
        original_comment: str,
        record: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Extract Christopher Bradley specifications from the user-supplied razor_extracted field.

        Args:
            field_data: The matched razor data (unused in this enricher)
            original_comment: The user-supplied razor_extracted field (not the full comment)

        Returns:
            Dictionary with plate and material if found, or None if no specifications detected.
            Includes _enriched_by and _extraction_source metadata fields.
        """
        razor_string = original_comment
        if not razor_string:
            return None
        plate_level = self._extract_plate_level(razor_string)
        if not plate_level:
            return None
        plate_type = self._extract_plate_type(razor_string)

        # Prepare extracted data. plate_type is only recorded when the
        # string names it: a level on its own (e.g. "C plate") does not
        # imply SB, so no type is invented for it.
        extracted_data = {
            "plate_level": plate_level,
        }
        if plate_type:
            extracted_data["plate_type"] = plate_type

        # Use BaseEnricher's single source method for consistency
        return self._create_single_source_enriched_data(extracted_data, "user_comment")

    def _extract_plate_level(self, text: str) -> Optional[str]:
        """Extract plate level from text using regex patterns.

        Args:
            text: The text to search for plate level patterns

        Returns:
            The extracted plate level as a string (e.g., "A", "B", "C"), or None if not found
        """
        # Match AA, A, B, C, D, E, F, G (case-insensitive, word boundary)
        pattern = r"\b(AA|A|B|C|D|E|F|G)\b"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            level = match.group(1).upper()
            if level in self.VALID_PLATE_LEVELS:
                return level
        return None

    def _extract_plate_type(self, text: str) -> Optional[str]:
        """Extract plate type from text using regex patterns.

        Args:
            text: The text to search for plate type patterns

        Returns:
            The extracted plate type as a string ("OC" for open comb, "SB"
            for solid bar), or None if the text names no plate type. SB is
            not assumed: a bare plate level carries no type information.
        """
        # Match OC (open comb) or SB (solid bar); no default
        if re.search(r"\bOC\b|open comb", text, re.IGNORECASE):
            return "OC"
        if re.search(r"\bSB\b|solid bar", text, re.IGNORECASE):
            return "SB"
        return None

    def _extract_material(self, text: str) -> Optional[str]:
        """Extract material specification from text using regex patterns.

        Args:
            text: The text to search for material patterns

        Returns:
            The extracted material as a string, or None if not found
        """
        # Check for titanium first (more specific)
        titanium_patterns = [
            r"\btitanium\b",
            r"\bti\b",
        ]
        for pattern in titanium_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "titanium"
        # Check for stainless steel - be more specific to avoid false positives
        stainless_single_word_pattern = r"\bstainless(?=\b|\s|$|[.,;:!])"
        stainless_patterns = [r"\bstainless\s+steel\b", r"\bss\b", stainless_single_word_pattern]
        for pattern in stainless_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "stainless steel"
        return None
