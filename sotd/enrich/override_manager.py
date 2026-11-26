#!/usr/bin/env python3
"""Override manager for enrich phase field corrections."""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)


class EnrichmentOverrideManager:
    """Manages loading and application of enrichment field overrides for enrich phase."""

    # Valid field names that can be overridden
    VALID_FIELDS = {"razor", "blade", "brush", "soap"}

    # Enrichment keys by field type and their expected types
    # Format: {field: {enrichment_key: type}}
    # Only keys an enricher actually reads belong here. BrushEnricher reads
    # fiber/knot_size_mm and StraightRazorEnricher reads grind/width/point/
    # steel; the other enrichers (GameChanger, Blackbird, Christopher
    # Bradley, SuperSpeed, RazorFormat, BladeCount, SoapSample) take no
    # override manager, so gap/plate/plate_type/plate_level/
    # super_speed_variant/format/use_count/sample_brand/sample_scent were
    # validated but silently never applied. Blade and soap keep empty
    # mappings until an enricher is wired to read an override for them;
    # adding a key here without that wiring reintroduces the same trap.
    ENRICHMENT_KEYS = {
        "brush": {
            "fiber": str,
            "knot_size_mm": float,
        },
        "razor": {
            "grind": str,
            "width": str,
            "point": str,
            "steel": str,
        },
        "blade": {},
        "soap": {},
    }

    def __init__(self, override_file_path: Path):
        """Initialize EnrichmentOverrideManager with path to override file.

        Args:
            override_file_path: Path to the YAML override file
        """
        self.override_file_path = override_file_path
        # Structure: {month: {comment_id: {field: {enrichment_key: override_spec}}}}
        self.overrides: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}

    def load_overrides(self) -> None:
        """Load overrides from YAML file with validation.

        Raises:
            ValueError: If override file has validation errors
            yaml.YAMLError: If YAML syntax is invalid
        """
        if not self.override_file_path.exists():
            # Override file is optional - pipeline continues normally
            logger.debug("Enrichment override file not found: %s", self.override_file_path)
            return

        try:
            with self.override_file_path.open("r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML syntax in enrichment override file: {e}")

        if content is None:
            # Empty file is valid
            logger.debug("Enrichment override file is empty: %s", self.override_file_path)
            return

        if not isinstance(content, dict):
            raise ValueError("Enrichment override file must contain a dictionary at root level")

        # Validate and load overrides
        total_overrides = 0
        for month, month_data in content.items():
            # Validate month format (YYYY-MM)
            if not self._validate_month_format(month):
                raise ValueError(
                    f"Invalid month format '{month}' in enrichment override file. "
                    f"Expected format: YYYY-MM (e.g., 2026-01)"
                )

            if not isinstance(month_data, dict):
                raise ValueError(f"Month '{month}' must contain a dictionary of comment overrides")

            month_overrides = {}
            for comment_id, field_data in month_data.items():
                if not isinstance(field_data, dict):
                    raise ValueError(
                        f"Comment '{comment_id}' in month '{month}' must contain field overrides"
                    )

                comment_overrides = {}
                for field, enrichment_data in field_data.items():
                    # Validate field name
                    if field not in self.VALID_FIELDS:
                        raise ValueError(
                            f"Invalid field '{field}' in comment '{comment_id}' month '{month}'. "
                            f"Valid fields: {', '.join(sorted(self.VALID_FIELDS))}"
                        )

                    if not isinstance(enrichment_data, dict):
                        raise ValueError(
                            f"Field '{field}' in comment '{comment_id}' month '{month}' "
                            f"must contain a dictionary of enrichment key overrides"
                        )

                    field_enrichment_overrides = {}
                    for enrichment_key, override_spec in enrichment_data.items():
                        # Validate enrichment key
                        valid_keys = self.ENRICHMENT_KEYS.get(field, {})
                        if enrichment_key not in valid_keys:
                            raise ValueError(
                                f"Invalid enrichment key '{enrichment_key}' for field '{field}' "
                                f"in comment '{comment_id}' month '{month}'. "
                                f"Valid keys for {field}: {', '.join(sorted(valid_keys.keys()))}"
                            )

                        # Validate override specification
                        validated_spec = self._validate_override_spec(
                            override_spec, field, enrichment_key, comment_id, month
                        )
                        field_enrichment_overrides[enrichment_key] = validated_spec
                        total_overrides += 1

                    if field_enrichment_overrides:
                        comment_overrides[field] = field_enrichment_overrides

                if comment_overrides:
                    month_overrides[comment_id] = comment_overrides

            if month_overrides:
                self.overrides[month] = month_overrides

        if total_overrides > 0:
            logger.info(
                "Loaded %d enrichment overrides from %s",
                total_overrides,
                self.override_file_path,
            )

    def _validate_month_format(self, month: str) -> bool:
        """Validate month format is YYYY-MM.

        Args:
            month: Month string to validate

        Returns:
            True if valid format, False otherwise
        """
        pattern = r"^\d{4}-\d{2}$"
        if not re.match(pattern, month):
            return False

        # Validate month is in valid range (01-12)
        try:
            year, month_num = month.split("-")
            month_int = int(month_num)
            if month_int < 1 or month_int > 12:
                return False
        except ValueError:
            return False

        return True

    def _validate_override_spec(
        self,
        override_spec: Any,
        field: str,
        enrichment_key: str,
        comment_id: str,
        month: str,
    ) -> Dict[str, Any]:
        """Validate and normalize override specification.

        Args:
            override_spec: The override specification (can be explicit value or dict with use_catalog)
            field: Field name (razor, blade, brush, soap)
            enrichment_key: Enrichment key (fiber, knot_size_mm, etc.)
            comment_id: Comment ID for error messages
            month: Month for error messages

        Returns:
            Normalized override specification dict

        Raises:
            ValueError: If override specification is invalid
        """
        expected_type = self.ENRICHMENT_KEYS[field][enrichment_key]

        # Case 1: Explicit value (string, float, or int)
        if not isinstance(override_spec, dict):
            # Validate type matches expected type
            if not isinstance(override_spec, expected_type):
                # Allow string to be converted to float/int if needed
                if expected_type is float and isinstance(override_spec, (int, str)):
                    try:
                        override_spec = float(override_spec)
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"Override value for {field}.{enrichment_key} in comment "
                            f"'{comment_id}' month '{month}' must be {expected_type.__name__}, "
                            f"got: {type(override_spec).__name__}"
                        )
                elif expected_type is int and isinstance(override_spec, (float, str)):
                    try:
                        override_spec = int(float(override_spec))
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"Override value for {field}.{enrichment_key} in comment "
                            f"'{comment_id}' month '{month}' must be {expected_type.__name__}, "
                            f"got: {type(override_spec).__name__}"
                        )
                elif not isinstance(override_spec, expected_type):
                    raise ValueError(
                        f"Override value for {field}.{enrichment_key} in comment "
                        f"'{comment_id}' month '{month}' must be {expected_type.__name__}, "
                        f"got: {type(override_spec).__name__}"
                    )

            # Validate string values are not empty
            if expected_type is str and isinstance(override_spec, str):
                if not override_spec.strip():
                    raise ValueError(
                        f"Override value for {field}.{enrichment_key} in comment "
                        f"'{comment_id}' month '{month}' cannot be empty or whitespace-only"
                    )

            return {"explicit_value": override_spec}

        # Case 2: Dict with use_catalog flag
        if "use_catalog" in override_spec:
            use_catalog = override_spec["use_catalog"]
            if not isinstance(use_catalog, bool):
                raise ValueError(
                    f"use_catalog flag for {field}.{enrichment_key} in comment "
                    f"'{comment_id}' month '{month}' must be a boolean, "
                    f"got: {type(use_catalog).__name__}"
                )

            if use_catalog:
                return {"use_catalog": True}
            else:
                # use_catalog: false is same as no override
                return {}

        # Case 3: Invalid dict structure
        raise ValueError(
            f"Invalid override specification for {field}.{enrichment_key} in comment "
            f"'{comment_id}' month '{month}'. "
            f"Must be either an explicit value ({expected_type.__name__}) or "
            f"a dict with 'use_catalog: true'"
        )

    def get_override(
        self, month: str, comment_id: str, field: str, enrichment_key: str
    ) -> Optional[Union[str, float, int]]:
        """Get override value or flag for specific enrichment field.

        Priority:
        1. Explicit value (if specified) - returns the value
        2. use_catalog flag (if true) - returns "use_catalog" string
        3. No override - returns None

        Args:
            month: Month in YYYY-MM format
            comment_id: Reddit comment ID
            field: Field name (razor, blade, brush, soap)
            enrichment_key: Enrichment key (fiber, knot_size_mm, etc.)

        Returns:
            - Explicit value if specified (str, float, or int)
            - "use_catalog" string if use_catalog flag is set
            - None if no override exists
        """
        month_overrides = self.overrides.get(month, {})
        comment_overrides = month_overrides.get(comment_id, {})
        field_overrides = comment_overrides.get(field, {})
        override_spec = field_overrides.get(enrichment_key)

        if not override_spec:
            return None

        # Priority: explicit value > use_catalog flag
        if "explicit_value" in override_spec:
            return override_spec["explicit_value"]
        elif override_spec.get("use_catalog"):
            return "use_catalog"

        return None

    def has_override(self, month: str, comment_id: str, field: str, enrichment_key: str) -> bool:
        """Check if override exists for specific enrichment field.

        Args:
            month: Month in YYYY-MM format
            comment_id: Reddit comment ID
            field: Field name (razor, blade, brush, soap)
            enrichment_key: Enrichment key (fiber, knot_size_mm, etc.)

        Returns:
            True if override exists, False otherwise
        """
        return self.get_override(month, comment_id, field, enrichment_key) is not None

    def validate_overrides(self, data: List[Dict[str, Any]], month: str) -> None:
        """Validate that all override comment IDs exist in the data.

        Args:
            data: List of comment records to validate against
            month: Month in YYYY-MM format

        Raises:
            ValueError: If any override references non-existent comment IDs
        """
        # Build set of existing comment IDs
        existing_ids = {record.get("id") for record in data if record.get("id")}

        # Check all override comment IDs exist for this month
        month_overrides = self.overrides.get(month, {})
        missing_ids = []
        for comment_id in month_overrides.keys():
            if comment_id not in existing_ids:
                missing_ids.append(comment_id)

        if missing_ids:
            logger.warning(
                "Enrichment override file references non-existent comment IDs for month %s: %s. "
                "This usually means the override file is for a different dataset or the data has changed.",
                month,
                ", ".join(missing_ids),
            )

    def has_overrides(self) -> bool:
        """Check if any overrides are loaded.

        Returns:
            True if overrides exist, False otherwise
        """
        return bool(self.overrides)

    def get_override_summary(self) -> Dict[str, Any]:
        """Get summary statistics about loaded overrides.

        Returns:
            Dictionary with override statistics
        """
        total_overrides = 0
        month_counts = {}
        field_counts = {}
        key_counts = {}

        for month, month_overrides in self.overrides.items():
            month_count = 0
            for comment_id, field_data in month_overrides.items():
                for field, enrichment_data in field_data.items():
                    month_count += len(enrichment_data)
                    total_overrides += len(enrichment_data)

                    field_counts[field] = field_counts.get(field, 0) + len(enrichment_data)

                    for enrichment_key in enrichment_data:
                        key = f"{field}.{enrichment_key}"
                        key_counts[key] = key_counts.get(key, 0) + 1

            month_counts[month] = month_count

        return {
            "total_overrides": total_overrides,
            "months_with_overrides": len(month_counts),
            "month_counts": month_counts,
            "field_counts": field_counts,
            "key_counts": key_counts,
        }
