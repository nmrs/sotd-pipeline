import logging
from typing import Any, Dict, List

from .enricher import BaseEnricher

logger = logging.getLogger(__name__)


class EnricherRegistry:
    """Registry for managing enricher instances and coordinating enrichment operations."""

    def __init__(self):
        self._enrichers: List[BaseEnricher] = []
        self._enrichers_by_field: Dict[str, List[BaseEnricher]] = {}

    def register(self, enricher: BaseEnricher) -> None:
        """Register an enricher instance.

        Args:
            enricher: The enricher instance to register
        """
        if not isinstance(enricher, BaseEnricher):
            raise ValueError(f"Enricher must inherit from BaseEnricher, got {type(enricher)}")

        self._enrichers.append(enricher)
        target_field = enricher.target_field

        if target_field not in self._enrichers_by_field:
            self._enrichers_by_field[target_field] = []

        self._enrichers_by_field[target_field].append(enricher)
        logger.debug(f"Registered enricher {enricher.get_enricher_name()} for field {target_field}")

    def get_enrichers_for_field(self, field: str) -> List[BaseEnricher]:
        """Get all enrichers that target the specified field.

        Args:
            field: The field name to get enrichers for

        Returns:
            List of enrichers that target this field
        """
        return self._enrichers_by_field.get(field, [])

    def get_all_enrichers(self) -> List[BaseEnricher]:
        """Get all registered enrichers.

        Returns:
            List of all registered enrichers
        """
        return self._enrichers.copy()

    def enrich_record(self, record: Dict[str, Any], original_comment: str) -> Dict[str, Any]:
        """Enrich a single record with all applicable enrichers.

        Args:
            record: A comment record with matched product data
            original_comment: The original user comment text (unused for enrichment)

        Returns:
            The enriched record with additional specifications written directly to product fields
        """
        enriched_record = record.copy()

        # Process each field that has enrichers
        for field, enrichers in self._enrichers_by_field.items():
            field_data = enriched_record.get(field)
            if not field_data:
                continue

            # Use the corresponding *_extracted field for enrichment, else fall back to
            # product['original']
            extracted_field_name = f"{field}_extracted"
            extracted_value = record.get(extracted_field_name, "")
            if not extracted_value and isinstance(field_data, dict):
                extracted_value = field_data.get("original", "")

            field_enriched_data = {}
            # Provenance must not be overwritten by the last writer: collect
            # every contributing enricher (and each one's extraction source)
            # instead of letting .update() keep only the final stamp.
            # (GameChanger + RazorFormat both fire on a Game Changer record,
            # yet the saved record named only RazorFormatEnricher; the soap
            # enrichers stamp no provenance at all.)
            enriched_by: List[str] = []
            extraction_sources: List[str] = []

            for enricher in enrichers:
                try:
                    if enricher.applies_to(record):
                        enrichment_result = enricher.enrich(field_data, extracted_value, record)
                        if enrichment_result:
                            by = enrichment_result.get("_enriched_by")
                            if not by:
                                # Some enrichers stamp no provenance; the
                                # registry knows the contributor.
                                by = enricher.get_enricher_name()
                            if by not in enriched_by:
                                enriched_by.append(by)
                            source = enrichment_result.get("_extraction_source")
                            if source and source not in extraction_sources:
                                extraction_sources.append(source)
                            for key, value in enrichment_result.items():
                                if key not in ("_enriched_by", "_extraction_source"):
                                    field_enriched_data[key] = value
                            logger.debug(f"Applied {enricher.get_enricher_name()} to {field}")
                except Exception as e:
                    logger.error(
                        f"Error applying enricher {enricher.get_enricher_name()} to {field}: {e}"
                    )
                    # Continue with other enrichers even if one fails

            if enriched_by:
                # One contributor keeps the historical plain-string shape;
                # several contributors are recorded as a list, so no
                # provenance is silently dropped.
                field_enriched_data["_enriched_by"] = (
                    enriched_by[0] if len(enriched_by) == 1 else enriched_by
                )
            if extraction_sources:
                field_enriched_data["_extraction_source"] = (
                    extraction_sources[0] if len(extraction_sources) == 1 else extraction_sources
                )

            # Write enriched data directly to product field
            if field_enriched_data:
                # Ensure field_data is a dict with proper structure
                if not isinstance(field_data, dict):
                    field_data = {"original": field_data}

                # Filter out match-phase-specific fields that shouldn't carry over to enriched phase
                # These fields are only needed during matching and scoring, not for downstream
                # analysis
                filtered_field_data = self._filter_match_phase_fields(field_data)

                # Add enriched data to the product field
                filtered_field_data["enriched"] = field_enriched_data

                # Update the record with the filtered and enriched field data
                enriched_record[field] = filtered_field_data
            else:
                # Even if no enrichment occurs, filter out match-phase-specific fields
                # to ensure clean data structure in enriched phase
                if isinstance(field_data, dict):
                    filtered_field_data = self._filter_match_phase_fields(field_data)
                    enriched_record[field] = filtered_field_data

        return enriched_record

    def _filter_match_phase_fields(self, field_data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter out match-phase-specific fields that shouldn't carry over to enriched
        phase.

        Args:
            field_data: The field data from the match phase

        Returns:
            Filtered field data with match-phase-specific fields removed
        """
        # Fields that are only needed during matching and scoring
        match_phase_fields = {
            "all_strategies",  # Strategy evaluation results
            "_matched_by_strategy",  # Strategy identification
            "_pattern_used",  # Pattern used for matching
        }

        filtered_data = {}
        for key, value in field_data.items():
            if key not in match_phase_fields:
                filtered_data[key] = value

        return filtered_data

    def enrich_records(
        self, records: List[Dict[str, Any]], original_comments: List[str]
    ) -> List[Dict[str, Any]]:
        """Enrich multiple records with all applicable enrichers.

        Args:
            records: List of comment records with matched product data
            original_comments: List of original user comment texts

        Returns:
            List of enriched records
        """
        if len(records) != len(original_comments):
            raise ValueError("Records and original_comments must have the same length")

        enriched_records = []

        for i, (record, original_comment) in enumerate(zip(records, original_comments)):
            try:
                enriched_record = self.enrich_record(record, original_comment)
                enriched_records.append(enriched_record)
            except Exception as e:
                logger.error(f"Error enriching record {i}: {e}")
                # Include the original record if enrichment fails
                enriched_records.append(record)

        return enriched_records


# Global registry instance
enricher_registry = EnricherRegistry()
