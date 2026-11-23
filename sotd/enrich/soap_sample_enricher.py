from typing import Any, Dict, Optional

from sotd.utils.soap_extraction import extract_soap_sample_via_normalization

from .enricher import BaseEnricher


class SoapSampleEnricher(BaseEnricher):
    """Enricher for extracting soap sample information from user comments.

    Extracts sample/smush information from patterns like:
    - "Summer Break Soaps - Steady (sample)" -> sample_type: "sample"
    - "Summer Break Soaps - Steady - soap (sample -- thanks!!)" -> sample_type: "sample"
    - "Summer Break Soaps - Steady (sample 3 of 10)" -> sample_type: "sample",
      sample_number: 3, total_samples: 10
    - "a smush from u/Someone" -> sample_type: "sample"
    - "Mystery Smush Croap" -> sample_type: "sample"

    Uses the normalization-difference approach to avoid confusion between product names
    and sample indicators by leveraging the already-done normalization work.
    Smush/samp collapse to sample_type "sample" (report copy says "samples or smushes").
    """

    @property
    def target_field(self) -> str:
        """Target soap field for enrichment."""
        return "soap"

    def applies_to(self, record: Dict[str, Any]) -> bool:
        """Check if this enricher applies to the record."""
        return "soap" in record and record["soap"] is not None

    def enrich(
        self,
        field_data: Dict[str, Any],
        original_comment: str,
        record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Enrich soap data with sample information using normalization approach."""
        original = field_data.get("original", "")
        normalized = field_data.get("normalized", "")

        if not original or not normalized:
            return {}

        # Extract sample information using normalization-difference method
        result = extract_soap_sample_via_normalization(original, normalized)
        sample_type = result[0] if result else None
        sample_number = result[1] if result else None
        total_samples = result[2] if result else None
        extraction_remainder = result[3] if result else None

        # Extract bulk-overrides rewrite mystery/Blind Date soaps to "Unknown Mystery",
        # which matches catalog Unknown / Smush. That text has no "(sample)" marker, so
        # force sample_type here for sample aggregators.
        if sample_type is None:
            matched = field_data.get("matched") or {}
            if isinstance(matched, dict):
                brand = (matched.get("brand") or "").strip().lower()
                scent = (matched.get("scent") or "").strip().lower()
                if brand == "unknown" and scent == "smush":
                    sample_type = "sample"

        # A soap with no sample marker is not enrichment: return {} so the
        # registry writes no `enriched` key and the record is not counted
        # as soap-enriched in the run stats. Previously this returned an
        # all-None dict, which counted nearly every soap record as enriched.
        if sample_type is None:
            return {}

        # Create enriched data
        enriched_data = {
            "sample_type": sample_type,
            "sample_number": sample_number,
            "total_samples": total_samples,
            "extraction_remainder": extraction_remainder,
        }

        return enriched_data
