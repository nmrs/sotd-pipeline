import re
from typing import Any, Dict, Optional

from .enricher import BaseEnricher


class RazorFormatEnricher(BaseEnricher):
    """Enricher for determining final razor format from matched razor and blade data.

    Moves all format determination logic from aggregate phase to enrich phase.
    Handles all format cases: Shavette, Half DE, Cartridge/Disposable, and fallback logic.
    """

    @property
    def target_field(self) -> str:
        """Target razor field for enrichment."""
        return "razor"

    def applies_to(self, record: Dict[str, Any]) -> bool:
        """Determine if this enricher applies to the given record.

        Applies to all records that have a matched razor product.

        Args:
            record: A comment record with matched product data

        Returns:
            True if record has a razor field, False otherwise
        """
        if "razor" not in record or record["razor"] is None:
            return False

        razor_data = record["razor"]
        if not isinstance(razor_data, dict):
            return False

        # Check if razor has matched data
        razor_matched = razor_data.get("matched")
        if not razor_matched:
            return False

        return True

    def enrich(
        self,
        field_data: Dict[str, Any],
        original_comment: str,
        record: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Determine the final razor format using complete logic from aggregate phase.

        Args:
            field_data: The matched razor data from the match phase
            original_comment: The original user comment text (unused for format determination)
            record: The full comment record. Blade data is read from this record's
                "blade" field (not from shared state), so enrich() is stateless
                across records.

        Returns:
            Dictionary with format field in enriched section, or None if no format determined.
            Includes _enriched_by and _extraction_source metadata fields.
        """
        # Get razor format from matched data
        razor_matched = field_data.get("matched", {})
        razor_format = razor_matched.get("format", "").strip() if razor_matched else ""

        # Get blade format from the record passed to this call, not shared state.
        blade_format = ""
        if record:
            blade_data = record.get("blade", {})
            if isinstance(blade_data, dict):
                blade_matched = blade_data.get("matched", {})
                if blade_matched:
                    blade_format = blade_matched.get("format", "").strip()

        # Constants from aggregate phase logic
        DE = "DE"
        HALF_DE = "Half DE"
        SHAVETTE = "Shavette"
        CARTRIDGE_DISPOSABLE = "Cartridge/Disposable"

        # CRITICAL: Cartridge/Disposable razors should always remain Cartridge/Disposable
        # regardless of blade type - this is the user's choice of razor format
        if razor_format == CARTRIDGE_DISPOSABLE:
            return self._create_single_source_enriched_data(
                {"format": CARTRIDGE_DISPOSABLE}, "catalog_data"
            )

        # Check if razor format matches "shavette (.*)" pattern (already specific)
        if razor_format and re.match(r"shavette (.*)", razor_format, re.IGNORECASE):
            return self._create_single_source_enriched_data(
                {"format": razor_format}, "catalog_data"
            )

        # Handle generic shavette format combinations (case-insensitive)
        if razor_format.upper() == SHAVETTE.upper():
            if not blade_format:
                blade_format = "Unspecified"
            # Assume random DE shavettes use half DE (from aggregate phase logic)
            elif blade_format == DE:
                blade_format = HALF_DE
            return self._create_single_source_enriched_data(
                {"format": f"{SHAVETTE} ({blade_format})"}, "blade_format_inference"
            )

        # Fix: Always return the full razor_format if it starts with 'Half DE'
        if razor_format and razor_format.startswith(HALF_DE):
            return self._create_single_source_enriched_data(
                {"format": razor_format}, "catalog_data"
            )

        # Handle Half DE detection (only when razor format is not already determined)
        if blade_format == DE:
            return self._create_single_source_enriched_data({"format": DE}, "blade_format")
        elif blade_format:
            return self._create_single_source_enriched_data(
                {"format": blade_format}, "blade_format"
            )
        elif razor_format:
            return self._create_single_source_enriched_data(
                {"format": razor_format}, "catalog_data"
            )

        # Default to DE (from aggregate phase logic)
        return self._create_single_source_enriched_data({"format": DE}, "default")
