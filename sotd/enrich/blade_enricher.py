from typing import Any, Dict, Optional

from sotd.utils.blade_extraction import extract_blade_use_count_via_normalization

from .enricher import BaseEnricher


class BladeCountEnricher(BaseEnricher):
    """Enricher for extracting blade use count from user comments.

    Extracts the number of times a blade has been used from patterns like:
    - "Astra SP (3)" -> use_count: 3
    - "Feather [5]" -> use_count: 5
    - "Gillette Platinum {2}" -> use_count: 2
    - "Personna x4" -> use_count: 4
    - "7'o clock - yellow (new)" -> use_count: 1
    - "astra green 3rd use" -> use_count: 3
    - "astra green [2\\]" -> use_count: 2
    - "Feather Hi-Stainless (2nd)" -> use_count: 2

    Uses the normalization-difference approach to avoid confusion between model numbers
    and actual use counts by leveraging the already-done normalization work.

    Maximum use count is capped at 899 to prevent interpreting large model numbers
    or other identifiers as legitimate use counts.
    """

    # Maximum reasonable use count for a blade
    MAX_USE_COUNT = 899

    @property
    def target_field(self) -> str:
        """Target blade field for enrichment."""
        return "blade"

    def applies_to(self, record: Dict[str, Any]) -> bool:
        """Check if this enricher applies to the record."""
        return "blade" in record and record["blade"] is not None

    def enrich(
        self,
        field_data: Dict[str, Any],
        original_comment: str,
        record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Enrich blade data with use count information using normalization approach."""
        original = field_data.get("original", "")
        normalized = field_data.get("normalized", "")
        matched = field_data.get("matched", {})
        model = matched.get("model") if matched else None

        if not original or not normalized:
            return {}

        # Extract use count using normalization-difference method
        result = extract_blade_use_count_via_normalization(original, normalized, model)
        use_count = result[0] if result else None
        extraction_remainder = result[1] if result else None

        # Apply maximum use count limit to prevent interpreting large model numbers
        # or other identifiers as legitimate use counts
        if use_count is not None and use_count > self.MAX_USE_COUNT:
            use_count = None
            extraction_remainder = f"Exceeded max use count limit ({self.MAX_USE_COUNT})"

        # A blade with no use count is not enrichment: return {} so the
        # registry writes no `enriched` key and the record is not counted
        # as blade-enriched in the run stats. Previously this returned
        # {"use_count": None, "extraction_remainder": ...}, a non-empty
        # dict that counted nearly every blade record as enriched. (A
        # candidate rejected by the max-count cap is likewise not a
        # finding; nothing downstream reads extraction_remainder.)
        if use_count is None:
            return {}

        # Create enriched data
        enriched_data = {
            "use_count": use_count,
            "extraction_remainder": extraction_remainder,
        }

        return enriched_data
